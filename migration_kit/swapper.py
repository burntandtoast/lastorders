# Copyright (c) 2026 Burnt and Toast Studios Ltd. Proprietary; see LICENSE-COMMERCIAL.
"""`swap`: turn a mapping file into a reviewable unified diff."""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .scanner import mark_output as _mark
from .packs import PackSet, load_packs
from .scanner import MARKUP, _block_map, _is_comment, classify, iter_files, iter_model_tokens, iter_prefix_checks, iter_rows, list_bounds
from .swapsafe import (FILE_HOLD_NOTES, HOLD_NOTES, ID_FIELDS, MANUAL_HOLDS, STRUCT_LANGS, Cont, Lit, element,
                       equality_check, extend_equality, file_hold, list_like, parse_structure, token_hold,
                       yaml_structure)


@dataclass
class Mapping:
    replacements: dict[str, str]
    fine_tuned: dict[str, str] = field(default_factory=dict)
    include_docs: bool = False
    source: str = ""
    # Retiring ids that are deliberately never swapped (e.g. o1-pro): id -> details.
    flag_only: dict[str, dict] = field(default_factory=dict)


def mapping_from_packs(packs: PackSet, migrations: list[str] | None = None) -> Mapping:
    """Default mapping: every auto-mappable model in each pack's headline migration(s)."""
    reps: dict[str, str] = {}
    flag: dict[str, dict] = {}
    for p in packs:
        reps.update(p.default_mapping(migrations))
        flag.update(p.flag_only(migrations))
    srcs = ", ".join(f"{p.provider} pack v{p.version}" for p in packs)
    return Mapping(reps, {}, False, f"generated from {srcs}", flag)


def load_mapping(path: str | Path) -> Mapping:
    data = yaml.safe_load(Path(path).read_text()) or {}
    reps = {str(k): str(v) for k, v in (data.get("mappings") or {}).items()}
    for k in reps:
        if k.startswith("ft:"):  # OpenAI-style fine-tune ids; other providers' fine-tunes are caught in plan()
            raise ValueError(f"Fine-tuned id {k!r} belongs under 'fine_tuned:', not 'mappings:'")
    ft = {str(k): str(v) for k, v in (data.get("fine_tuned") or {}).items()}
    return Mapping(reps, ft, bool(data.get("include_docs", False)), str(data.get("source", "")))


@dataclass
class Change:
    file: str
    line: int
    old: str
    new: str
    # replace: `old` renamed to `new` in place. added: `new` added to an exact-match
    # allow-list next to `old` (which stays), so the swapped values still pass the check.
    action: str = "replace"


def format_preview(rows: list[tuple[str, str, str]]) -> str:
    """Per-file summary of model-id replacements. No line numbers, code, or patch text.

    ``rows`` is ``(file, old_id, new_id)`` in encounter order. The same pair is listed
    once per file; the count is the number of replacements.
    """
    order: list[str] = []
    counts: dict[str, int] = {}
    pairs: dict[str, list[tuple[str, str]]] = {}
    for file, old, new in rows:
        file, old, new = _flat(file), _flat(old), _flat(new)
        if file not in counts:
            order.append(file)
            counts[file] = 0
            pairs[file] = []
        counts[file] += 1
        if (old, new) not in pairs[file]:
            pairs[file].append((old, new))
    if not order:
        return "No model IDs would change."
    lines = []
    for file in order:
        n = counts[file]
        word = "change" if n == 1 else "changes"
        mapping = ", ".join(f"{old} -> {new}" for old, new in pairs[file])
        lines.append(f"{file}: {n} {word} ({mapping})")
    return "\n".join(lines)


def _flat(value: str) -> str:
    return " ".join(str(value).split())


@dataclass
class SwapResult:
    changes: list[Change]
    skipped_fine_tunes: list[tuple[str, int, str]]
    diff: str
    new_contents: dict[str, str]
    skipped_name_checks: list[tuple[str, int, str]] = field(default_factory=list)
    # Retiring ids left alone because renaming them isn't safe: (file, line, model, reason).
    skipped_unsafe: list[tuple[str, int, str, str]] = field(default_factory=list)
    # Checks left unchanged although swap renames the id they test elsewhere in the repo:
    # after the swap they no longer match. {"file", "line", "model", "related", "reason"}.
    must_update_together: list[dict] = field(default_factory=list)
    # Distinct ids in one list, set, object/dict or <select> that would map to the same new id.
    # Never applied (the renames are skipped). {"file", "line", "container", "target", "old", "applied"}.
    collapsed: list[dict] = field(default_factory=list)
    # Renames skipped because they would create a duplicate object/dict/JSON/YAML key, or a
    # duplicate id among the items of one list. {"file", "line", "model", "target", ...}.
    skipped_duplicate_key: list[dict] = field(default_factory=list)
    skipped_duplicate_id: list[dict] = field(default_factory=list)
    # Files swap never rewrites: {"file", "count", "models", "note"}.
    skipped_migration: list[dict] = field(default_factory=list)
    skipped_catalog: list[dict] = field(default_factory=list)
    # Exact-match allow-lists that get one new id for several renamed ids (applied once).
    allow_list_merges: list[dict] = field(default_factory=list)
    # Old ids that still have a kept definition somewhere (a skipped duplicate key/id or dropdown
    # option, a migration or catalogue file, a deployment / tokeniser / fixture / unquoted-key hold).
    # Swap renames no other reference to them; each reference it left is in must_update_together
    # (kind "kept_definition"). {"model", "target", "kept": [{"file", "line", "reason"}], "references": [...]}.
    kept_definitions: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "files_changed": len(self.new_contents),
            "replacements": len(self.changes),
            "must_update_together": self.must_update_together,
            "collapsed_targets": self.collapsed,
            "skipped_duplicate_key": self.skipped_duplicate_key,
            "skipped_duplicate_id": self.skipped_duplicate_id,
            "skipped_migration": self.skipped_migration,
            "skipped_catalog": self.skipped_catalog,
            "skipped_fine_tunes": [{"file": f, "line": l, "model": m} for f, l, m in self.skipped_fine_tunes],
            "skipped_name_checks": [{"file": f, "line": l, "model": m} for f, l, m in self.skipped_name_checks],
            "skipped_not_swappable": [{"file": f, "line": l, "model": m, "reason": r}
                                      for f, l, m, r in self.skipped_unsafe],
            "allow_list_merges": self.allow_list_merges,
            "kept_definitions": self.kept_definitions,
            "changes": [c.__dict__ for c in self.changes],
        }

    def manual(self) -> list[dict]:
        """Skipped renames someone has to decide by hand: {"file", "line", "model", "kind", "message"}."""
        out = []
        for d in self.skipped_duplicate_key:
            out.append({**_pick(d), "kind": "duplicate-key", "message": d["reason"]})
        for d in self.skipped_duplicate_id:
            out.append({**_pick(d), "kind": "duplicate-id", "message": d["reason"]})
        for f, l, m, r in self.skipped_unsafe:
            if r in MANUAL_HOLDS:
                out.append({"file": f, "line": l, "model": m, "kind": r.replace("_", "-"), "message": HOLD_NOTES[r]})
        for w in self.must_update_together:
            if w.get("kind") == "kept_definition":
                out.append({**_pick(w), "kind": "kept-definition", "message": w["reason"]})
        return out

    def warnings(self) -> list[str]:
        """Human-readable lines for the swap output (empty when there is nothing to check)."""
        out = []
        for w in self.must_update_together:
            if w.get("kind") != "kept_definition":
                out.append(f"MUST UPDATE TOGETHER {w['file']}:{w['line']} {w['model']}: {w['reason']}")
        for g in self.kept_definitions:
            if not g["references"]:
                continue
            kept = ", ".join(f"{k['file']}:{k['line']} ({k['reason']})" for k in g["kept"][:5])
            more = f" and {len(g['kept']) - 5} more" if len(g["kept"]) > 5 else ""
            out.append(f"KEPT {g['model']} (not renamed to {g['target']} anywhere): still defined at {kept}{more}; "
                       f"{len(g['references'])} other reference(s) left on {g['model']}:")
            for ref in g["references"]:
                out.append(f"  MUST UPDATE TOGETHER {ref['file']}:{ref['line']} {g['model']}")
        for c in self.collapsed:
            out.append(f"COLLAPSED {c['file']}:{c['line']} ({c['container']}): {', '.join(c['old'])} would all become "
                       f"{c['target']}; not applied (it would create duplicate entries or keys)")
        for d in self.skipped_duplicate_key:
            out.append(f"SKIPPED DUPLICATE KEY {d['file']}:{d['line']} {d['model']} -> {d['target']}: {d['reason']}")
        for d in self.skipped_duplicate_id:
            out.append(f"SKIPPED DUPLICATE ID {d['file']}:{d['line']} {d['model']} -> {d['target']}: {d['reason']}")
        for f, l, m, r in self.skipped_unsafe:
            if r in MANUAL_HOLDS:
                out.append(f"MANUAL {f}:{l} {m}: {HOLD_NOTES[r]}")
        return out


def _pick(d: dict) -> dict:
    return {"file": d["file"], "line": d["line"], "model": d["model"]}


_REASONS = {
    "name_check": ("prefix/substring check left unchanged (renaming it changes its logic); swap renames {related} "
                   "elsewhere, so this check no longer matches after the swap. Update it by hand."),
    "multiline": ("exact-match allow-list that doesn't fit on one line or holds more than quoted ids; swap renames "
                  "{related} elsewhere, so add the new id to this list by hand."),
    "notebook": ("exact-match allow-list in a notebook cell; swap renames {related} elsewhere, so add the new id "
                 "to this list by hand."),
    "equality": ("exact `==` comparison that swap can't extend safely on this line; swap renames {related} "
                 "elsewhere, so this comparison no longer matches the new id. Add the new id to it by hand."),
    "regex": ("regex pattern left unchanged next to code that swap renames ({related}); update the pattern by hand "
              "so it still matches the new id."),
    "fixture": ("recorded fixture left unchanged, but swap renames {related} elsewhere in this test file; re-record "
                "it or keep the assertions that read it on the old id."),
}
_DUP_KEY = ("renaming {old} to {new} here would give this object two `{key}` keys ({how}); in JS/TS that is a "
            "compile error (TS1117) and in JSON/Python/YAML the last one silently wins. Not renamed: decide by hand "
            "which entry the new id should get. Swap leaves every other reference to {old} unchanged too (listed "
            "under must_update_together), so rename them together when you decide.")
_DUP_ID = ("renaming {old} to {new} here would give two items of this list the same {field} `{value}` ({how}). "
           "Not renamed (nor the rest of this entry): decide by hand which entry the new id should get. Swap leaves "
           "every other reference to {old} unchanged too (listed under must_update_together), so rename them "
           "together when you decide.")
_KEPT = ("{model} is still defined or offered at {kept} (left unchanged: {why}), so swap does not rename this "
         "reference to {target}: renaming it would point at an id that isn't defined there. Update it together with "
         "the kept definition(s).")
# Holds that keep a definition / value of an old id in place.
KEPT_HOLDS = {"deployment_name", "tokeniser", "fixture", "object_key"}
_KEPT_WHY = {"duplicate_key": "duplicate key", "duplicate_id": "duplicate id", "migration": "migration file",
             "catalog": "price list / catalogue", "deployment_name": "Azure deployment name",
             "tokeniser": "tokeniser argument", "fixture": "recorded fixture", "object_key": "unquoted object key"}


@dataclass
class _Row:
    index: int
    line: int
    text: str
    lang: str = ""
    reps: list = field(default_factory=list)        # (s, e, old, new, kind)
    allow: list = field(default_factory=list)       # (s, e, old)
    eq: list = field(default_factory=list)          # (s, e, old, form)


def plan(root: str | Path, mapping: Mapping, packs: PackSet | None = None) -> SwapResult:
    root = Path(root).resolve()
    packs = packs or load_packs()
    skipped: list[tuple[str, int, str]] = []
    unsafe: list[tuple[str, int, str, str]] = []
    table = {**mapping.replacements, **mapping.fine_tuned}
    files: list[tuple[str, str, list[str], dict[int, _Row], list]] = []
    checks: list[tuple[str, int, str]] = []          # prefix / substring name checks, in order
    family: list[tuple[str, int, str]] = []          # name checks on ids outside the mapping
    held_files: dict[str, dict] = {}                 # migration / catalogue files: rel -> info
    # Pass 1: what each row would rename, and the checks that depend on it.
    for path, lang in iter_files(root, include_docs=mapping.include_docs):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(root).as_posix()
        rows, _ = iter_rows(text, path, lang)
        fhold = file_hold(rel, text)
        blocks = _block_map(rows)
        texts = [r.text for r in rows]
        todo: dict[int, _Row] = {}
        for pos, row in enumerate(rows):
            if row.mode is None:
                continue
            i, text_line = row.index + 1, row.text
            if fhold:
                for s, e, model, _ in iter_model_tokens(text_line, packs, row.lang, row.prev, row.mode):
                    if model in table and (row.mode is not MARKUP or mapping.include_docs):
                        info = held_files.setdefault(rel, {"reason": fhold, "count": 0, "models": set(), "lines": {}})
                        info["count"] += 1
                        info["models"].add(model)
                        # a kept definition is code, not a comment or docstring in the held file
                        kind, _ = classify(text_line, s, e, row.lang, row.prev, row.mode, rel)
                        if (row.mode is True and kind not in ("doc", "comment") and blocks.get(row.index) is None
                                and not _is_comment(text_line, row.lang)):
                            info["lines"].setdefault(model, i)
                continue
            if row.mode is True and not _is_comment(text_line, row.lang):
                family.extend((rel, i, model) for _, _, model, _ in iter_prefix_checks(text_line, packs))
            for s, e, model, pack in iter_model_tokens(text_line, packs, row.lang, row.prev, row.mode):
                if pack.fine_tune_base(model) is not None and model not in mapping.fine_tuned:
                    skipped.append((rel, i, model))
                    continue
                if model not in table:
                    # `startsWith("o3")` still matters when o3-mini is renamed elsewhere.
                    if classify(text_line, s, e, row.lang, row.prev, row.mode, rel)[1] == "name_check":
                        family.append((rel, i, model))
                    continue
                kind, block = classify(text_line, s, e, row.lang, row.prev, row.mode, rel)
                r = todo.setdefault(row.index, _Row(row.index, i, text_line, row.lang))
                if block == "allow_list":
                    r.allow.append((s, e, model))
                    continue
                if block == "name_check":
                    # `startsWith("o1")` is a family check; renaming it changes the logic.
                    checks.append((rel, i, model))
                    continue
                if block:
                    unsafe.append((rel, i, model, block))
                    continue
                if kind == "doc" and lang in ("html", "ipynb") and not mapping.include_docs:
                    continue                  # an HTML code sample or a notebook markdown cell: docs
                hold = token_hold(text_line, s, e, "markup" if row.mode == MARKUP else row.lang, rel, row.prev,
                                  kind, blocks.get(row.index), texts[pos + 1:pos + 13])
                if hold and not (mapping.include_docs and hold in ("comment", "docstring", "help_text")):
                    unsafe.append((rel, i, model, hold))
                    continue
                form = (equality_check(text_line, s, e)
                        if kind not in ("doc", "comment") and row.mode is not MARKUP else None)
                if form:
                    r.eq.append((s, e, model, form))
                    continue
                r.reps.append((s, e, model, table[model], kind))
        if todo:
            files.append((rel, lang, text.splitlines(keepends=True), todo, rows))
    # Structure: never write a duplicate key or a duplicate id in one list.
    dup_key: list[dict] = []
    dup_id: list[dict] = []
    collapsed: list[dict] = []
    must_kept: list[dict] = []
    for rel, lang, old_lines, todo, rows in files:
        if any(r.reps for r in todo.values()):
            _dedupe(rel, lang, rows, todo, dup_key, dup_id, collapsed)
    # Kept definitions: an old id that stays somewhere it is defined or offered is not renamed anywhere else.
    kept: dict[str, list[dict]] = {}
    for d in dup_key + dup_id:
        kept.setdefault(d["model"], []).append({"file": d["file"], "line": d["line"],
                                                "reason": "duplicate_key" if d in dup_key else "duplicate_id"})
    for rel, info in held_files.items():
        for model, line in info["lines"].items():
            kept.setdefault(model, []).append({"file": rel, "line": line, "reason": info["reason"]})
    for rel, i, model, why in unsafe:
        if why in KEPT_HOLDS and model in table:
            kept.setdefault(model, []).append({"file": rel, "line": i, "reason": why})
    blocked: dict[str, list[tuple[str, int]]] = {}
    for rel, lang, old_lines, todo, rows in files:
        for idx, r in todo.items():
            keep = []
            for rp in r.reps:
                if rp[2] in kept:
                    refs = blocked.setdefault(rp[2], [])
                    if (rel, r.line) not in refs:
                        refs.append((rel, r.line))
                else:
                    keep.append(rp)
            r.reps = keep
    kept_groups: list[dict] = []
    for model in sorted(kept):
        defs = sorted({(k["file"], k["line"], k["reason"]) for k in kept[model]})
        defs = [{"file": f, "line": l, "reason": w} for f, l, w in defs]
        # _dedupe already took the skipped tokens out of reps, so every blocked rep is another reference
        # (it can share a line with a kept definition: `{"old": {...}, "x": "old"}`).
        refs = sorted(blocked.get(model, []))
        kept_groups.append({"model": model, "target": table[model], "kept": defs,
                            "references": [{"file": f, "line": l} for f, l in refs]})
        shown = ", ".join(f"{k['file']}:{k['line']}" for k in defs[:3]) + (
            f" and {len(defs) - 3} more" if len(defs) > 3 else "")
        why = ", ".join(sorted({_KEPT_WHY[k["reason"]] for k in defs}))
        for f, l in refs:
            must_kept.append({"file": f, "line": l, "model": model, "related": [model], "kind": "kept_definition",
                              "kept_at": [f"{k['file']}:{k['line']}" for k in defs],
                              "reason": _KEPT.format(model=model, kept=shown, why=why, target=table[model])})
    renamed: set[str] = {m for _, _, _, todo, _ in files for r in todo.values()
                         for _, _, m, _, kind in r.reps if kind not in ("doc", "comment")}
    # Pass 2: apply, adding new ids to allow-lists (and `==` checks) whose ids are renamed elsewhere.
    changes: list[Change] = []
    name_checks: list[tuple[str, int, str]] = []
    must: list[dict] = list(must_kept)
    merges: list[dict] = []
    diffs: list[str] = []
    new_contents: dict[str, str] = {}
    name_checks.extend(checks)
    for rel, i, model in checks + family:
        related = sorted(r for r in renamed if model in r)
        if related:
            must.append({"file": rel, "line": i, "model": model, "related": related, "kind": "name_check",
                         "reason": _REASONS["name_check"].format(related=", ".join(related))})
    for rel, lang, old_lines, todo, _rows in files:
        new_lines = list(old_lines)
        groups: dict[object, dict[str, set[str]]] = {}
        for idx, r in sorted(todo.items()):
            edits: list[tuple[int, int, str]] = [(s, e, new) for s, e, _, new, _ in r.reps]
            row_changes = [Change(rel, r.line, m, n) for _, _, m, n, _ in r.reps]
            done: set[tuple[int, int]] = set()
            for s, e, model in r.allow:
                if model not in renamed:
                    name_checks.append((rel, r.line, model))
                    continue
                lb = list_bounds(r.text, s, e)
                if lb is None or lang == "ipynb":
                    why = "notebook" if lang == "ipynb" else "multiline"
                    must.append({"file": rel, "line": r.line, "model": model, "related": [model], "kind": "allow_list",
                                 "reason": _REASONS[why].format(related=model)})
                    name_checks.append((rel, r.line, model))
                    continue
                if (lb[0], lb[1]) in done:
                    continue
                done.add((lb[0], lb[1]))
                edit, added = _allow_list_edit(r.text, lb, table, renamed)
                for old, new in added:
                    row_changes.append(Change(rel, r.line, old, new, "added"))
                if edit:
                    edits.append(edit)
                key = ("allow", idx, lb[0])
                for qs, qe in lb[2]:
                    item = r.text[qs + 1:qe - 1]
                    if item in table and item in renamed:
                        groups.setdefault(key, {}).setdefault(table[item], set()).add(item)
            for s, e, model, form in r.eq:
                if model not in renamed:
                    name_checks.append((rel, r.line, model))
                    continue
                ext = extend_equality(r.text, s, e, table[model], r.lang) if form == "lhs" and lang != "ipynb" else None
                if ext and not any(a < ext[1] and ext[0] < b for a, b, _ in edits):
                    edits.append(ext)
                    row_changes.append(Change(rel, r.line, model, table[model], "added"))
                    continue
                must.append({"file": rel, "line": r.line, "model": model, "related": [model], "kind": "equality",
                             "reason": _REASONS["equality"].format(related=model)})
                name_checks.append((rel, r.line, model))
            if not edits:
                continue
            new = _splice(old_lines[idx], r.text, sorted(edits), lang == "ipynb")
            if new is None:
                unsafe.extend((rel, r.line, c.old, "notebook") for c in row_changes)
                continue
            new_lines[idx] = new
            changes.extend(row_changes)
        for key, by_target in groups.items():
            for target, olds in by_target.items():
                if len(olds) > 1:
                    merges.append({"file": rel, "line": key[1] + 1, "container": "allow-list (new id added once)",
                                   "target": target, "old": sorted(olds)})
        if new_lines != old_lines:
            new_contents[rel] = "".join(new_lines)
            diffs.append(_unified(old_lines, new_lines, rel))
    # Left-alone patterns / recordings next to code that is renamed.
    lines_changed: dict[str, set[int]] = {}
    for c in changes:
        lines_changed.setdefault(c.file, set()).add(c.line)
    models_changed: dict[str, set[str]] = {}
    for c in changes:
        if c.action == "replace":
            models_changed.setdefault(c.file, set()).add(c.old)
    for rel, i, model, why in unsafe:
        if why == "regex" and model in renamed and any(abs(i - j) <= 10 for j in lines_changed.get(rel, ())):
            must.append({"file": rel, "line": i, "model": model, "related": [model], "kind": "regex",
                         "reason": _REASONS["regex"].format(related=model)})
        elif why == "fixture" and model in models_changed.get(rel, ()):
            must.append({"file": rel, "line": i, "model": model, "related": [model], "kind": "fixture",
                         "reason": _REASONS["fixture"].format(related=model)})
    held_mig, held_cat = [], []
    for rel, info in sorted(held_files.items()):
        rec = {"file": rel, "count": info["count"], "models": sorted(info["models"]),
               "note": FILE_HOLD_NOTES[info["reason"]]}
        (held_mig if info["reason"] == "migration" else held_cat).append(rec)
    collapsed.sort(key=lambda c: (c["file"], c["line"]))
    merges.sort(key=lambda c: (c["file"], c["line"]))
    must.sort(key=lambda w: (w["file"], w["line"]))
    dup_key.sort(key=lambda d: (d["file"], d["line"]))
    dup_id.sort(key=lambda d: (d["file"], d["line"]))
    return SwapResult(changes, skipped, "".join(diffs), new_contents, name_checks, unsafe, must, collapsed,
                      dup_key, dup_id, held_mig, held_cat, merges, kept_groups)


# ------------------------------------------------------------------ duplicate keys / ids
def _dedupe(rel: str, lang: str, rows, todo: dict[int, _Row], dup_key: list, dup_id: list, collapsed: list) -> None:
    """Drop renames that would create a duplicate key in one object/dict, or the same id twice
    in one list (or <select>). Repeats until stable: keeping one old key can clash with another rename."""
    reps = {(idx, s): (e, old, new) for idx, r in todo.items() for s, e, old, new, _ in r.reps}
    skip: dict[tuple[int, int], tuple[str, dict]] = {}
    spans: list = []          # (kind, group key, unit id, row, qs, qe, current text, field, container line, how)
    units: dict = {}          # unit id -> list of rep keys that must be skipped together
    segs: dict = {}           # unit id -> (row, lo, hi): an <option> whose equality checks stay too
    held: set = set()         # unit ids that were skipped
    # <select> dropdowns: HTML, but also EJS / PHP / JSX templates and anything else with markup
    if lang == "html" or any(_SELECT_OPEN.search(r.text) for r in rows):
        _select_units(rows, reps, spans, units, segs)
    if lang == "yaml":
        _yaml_units(rows, reps, spans, units)
    elif lang in STRUCT_LANGS:
        _struct_units(rows, lang, reps, spans, units)
    elif lang == "go":
        _go_units(rows, reps, spans, units)
    if not spans:
        return

    def cur(sp):
        _, _, _, row, qs, qe, text, *_ = sp
        out, last = [], 0
        for (idx, s), (e, old, new) in sorted(reps.items()):
            if idx == row and qs < s and e < qe and (idx, s) not in skip:
                out += [text[last:s - qs - 1], new]
                last = e - qs - 1
        return "".join(out) + text[last:]

    def renamed(sp):
        return any(idx == sp[3] and sp[4] < s and e < sp[5] and (idx, s) not in skip
                   for (idx, s), (e, _, _) in reps.items())

    while True:
        groups: dict[tuple, list] = {}
        for sp in spans:
            groups.setdefault((sp[0], sp[1], cur(sp)), []).append(sp)
        newly = False
        for (kind, gkey, value), members in groups.items():
            if len(members) < 2:
                continue
            moved = [sp for sp in members if renamed(sp)]
            if not moved:
                continue
            olds = sorted({sp[6] for sp in members})
            cline = min(sp[8] for sp in members)
            for sp in moved:
                held.add(sp[2])
                for k in units.get(sp[2], []):
                    if k in skip:
                        continue
                    e, old, new = reps[k]
                    how = (f"{len(members)} entries would share it; one already uses it" if len(moved) < len(members)
                           else f"{len(members)} entries would share it: {', '.join(olds)}")
                    rec = {"file": rel, "line": k[0] + 1, "column": k[1] + 1, "model": old, "target": new,
                           "container_line": cline, "container": sp[9]}
                    if kind == "key":
                        rec.update(key=value, reason=_DUP_KEY.format(old=old, new=new, key=value, how=how))
                        dup_key.append(rec)
                    else:
                        rec.update(field=sp[7], value=value, reason=_DUP_ID.format(old=old, new=new, field=sp[7],
                                                                                   value=value, how=how))
                        dup_id.append(rec)
                    skip[k] = (kind, rec)
                    newly = True
            if len({sp[6] for sp in moved}) > 1 and len(moved) == len(members):
                collapsed.append({"file": rel, "line": cline, "container": members[0][9],
                                  "target": value, "old": olds, "applied": False})
        if not newly:
            break
    for idx, r in todo.items():
        r.reps = [rp for rp in r.reps if (idx, rp[0]) not in skip]
    # a skipped <option> keeps its template condition exactly as it was (no `|| new` added)
    for uid in held:
        if uid in segs:
            row, lo, hi = segs[uid]
            if row in todo:
                todo[row].eq = [q for q in todo[row].eq if not lo <= q[0] < hi]


def _struct_units(rows, lang, reps, spans, units) -> None:
    code = [(r.index, r.text) for r in rows if r.mode is True]
    plang = rows[0].lang if lang == "ipynb" and rows else lang
    if lang == "ipynb":
        code = [(r.index, r.text) for r in rows if r.mode is True and r.lang == "python"]
        plang = "python"
    lits, conts = parse_structure(code, plang if lang != "ipynb" else "ipynb")
    by_row: dict[int, list[Lit]] = {}
    for lit in lits:
        by_row.setdefault(lit.row, []).append(lit)

    def lit_reps(lit):
        return [(idx, s) for (idx, s), (e, _, _) in reps.items() if idx == lit.row and lit.qs < s and e < lit.qe]

    def within(c: Cont):
        if c.end is None:
            return [k for lit in lits if lit.cont is c for k in lit_reps(lit)]
        a, b = (c.row, c.col), c.end
        return [(idx, s) for (idx, s) in reps if a < (idx, s) < b]

    touched = {lit.row for lit in lits} & {idx for idx, _ in reps}
    if not touched:
        return
    for c in [x for x in conts]:
        # duplicate keys
        if c.keys and c.kind == "{":
            if any(lit is not None and lit_reps(lit) for _, _, lit in c.keys):
                for ei, ktext, lit in c.keys:
                    uid = ("lit", id(lit)) if lit is not None else ("ident", id(c), ei)
                    units[uid] = lit_reps(lit) if lit is not None else []
                    row, qs, qe, text = (lit.row, lit.qs, lit.qe, lit.text) if lit is not None else (-1, 0, 0, ktext)
                    spans.append(("key", ("c", id(c)), uid, row, qs, qe, text, None, c.row + 1, "object/dict keys"))
        # duplicate ids among list items
        if list_like(c, lang):
            for ei, ent in c.entries.items():
                for lit in ent["lits"]:
                    if lit.role == "item":
                        uid = ("lit", id(lit))
                        units[uid] = lit_reps(lit)
                        spans.append(("id", ("c", id(c), "#item"), uid, lit.row, lit.qs, lit.qe, lit.text, "item",
                                      c.row + 1, "list"))
                el = element(c, ei)
                if el is None:
                    continue
                for kei, ktext, klit in el.keys:
                    if ktext not in ID_FIELDS:
                        continue
                    vals = [lit for lit in (el.entries.get(kei) or {}).get("lits", []) if lit.role == "value"]
                    if len(vals) != 1:
                        continue
                    v = vals[0]
                    uid = ("el", id(el))
                    units[uid] = within(el)
                    spans.append(("id", ("c", id(c), ktext), uid, v.row, v.qs, v.qe, v.text, ktext, c.row + 1,
                                  "list of objects"))


def _go_units(rows, reps, spans, units) -> None:
    """Go composite literals that sit on one line and hold only quoted strings
    (`[]string{"a", "b"}`, `[]driver.Value{"a", "b"}`): the same id twice is a duplicate list item.
    Multi-line literals and map keys are not covered."""
    text = {r.index: r.text for r in rows if r.mode is True}
    seen: set = set()
    for (idx, s), (e, _, _) in sorted(reps.items()):
        line = text.get(idx)
        if line is None:
            continue
        b = list_bounds(line, s, e)
        if not b or line[b[0]] != "{" or (idx, b[0]) in seen:
            continue
        seen.add((idx, b[0]))
        for qs, qe in b[2]:
            uid = ("go", idx, qs)
            units[uid] = [(i, s2) for (i, s2), (e2, _, _) in reps.items() if i == idx and qs < s2 and e2 < qe]
            spans.append(("id", ("go", idx, b[0]), uid, idx, qs, qe, line[qs + 1:qe - 1], "item", idx + 1, "list"))


def _yaml_units(rows, reps, spans, units) -> None:
    lines = [r.text for r in rows]
    keys, items = yaml_structure(lines)

    def in_span(row, a, b):
        return [(idx, s) for (idx, s), (e, _, _) in reps.items() if idx == row and a <= s and e <= b]

    for k in keys:
        uid = ("ykey", k.row)
        units[uid] = in_span(k.row, k.col, k.end)
        spans.append(("key", ("y", k.group), uid, k.row, k.col - 1, k.end + 1, k.key, None, k.row + 1, "mapping keys"))
    item_rows: dict[tuple, list[int]] = {}
    for k in keys:
        if k.item_group is not None:
            item_rows.setdefault(k.group, []).append(k.row)
    for k in keys:
        if k.key in ID_FIELDS and k.value and k.group[0] == "item":
            members = [x for x in keys if x.group == k.group]
            parent = next((x.item_group for x in members if x.item_group is not None), None)
            if parent is None:
                continue
            uid = ("yitem", k.group)
            units[uid] = [key for x in members if x.value for key in in_span(x.row, *x.value)]
            a, b = k.value
            spans.append(("id", ("y", parent, k.key), uid, k.row, a - 1, b + 1, lines[k.row][a:b], k.key, k.row + 1,
                          "list of mappings"))
    for row, a, b, grp in items:
        uid = ("yval", row)
        units[uid] = in_span(row, a, b)
        spans.append(("id", ("y", grp, "#item"), uid, row, a - 1, b + 1, lines[row][a:b], "item", row + 1, "list"))


_OPTION_VALUE = re.compile(r"""\bvalue\s*=\s*(["'])([^"']*)\1""", re.I)


def _select_units(rows, reps, spans, units, segs=None) -> None:
    sel = None
    for r in rows:
        raw = r.text
        if sel is None and _SELECT_OPEN.search(raw):
            sel = r.index
        if sel is not None:
            for m in _OPTION_VALUE.finditer(raw):
                a, b = m.start(2), m.end(2)
                uid = ("opt", r.index, a)
                # the whole <option>: its value and the template condition that selects it
                lo = raw.rfind("<option", 0, a)
                hi = raw.find("<option", b)
                lo, hi = (0 if lo < 0 else lo), (len(raw) if hi < 0 else hi)
                units[uid] = [(idx, s) for (idx, s), (e, _, _) in reps.items() if idx == r.index and lo <= s and e <= hi]
                if segs is not None:
                    segs[uid] = (r.index, lo, hi)
                spans.append(("id", ("sel", sel), uid, r.index, a - 1, b + 1, m.group(2), "value", sel + 1,
                              "<select> dropdown"))
        if sel is not None and _SELECT_CLOSE.search(raw):
            sel = None


def _allow_list_edit(text: str, lb, table: dict[str, str], renamed: set[str]):
    """Insert the new ids after the last item of an exact-match list: `{"a", "b"}` ->
    `{"a", "b", "new"}`. Old ids stay, so values saved before the swap still pass."""
    opener, closer, items, _trailing = lb
    present = [text[qs + 1:qe - 1] for qs, qe in items]
    added: list[tuple[str, str]] = []
    new_ids: list[str] = []
    for old in present:
        new = table.get(old)
        if old in renamed and new and new not in present and new not in new_ids:
            new_ids.append(new)
            added.append((old, new))
    if not new_ids:
        return None, []
    q = text[items[-1][0]]
    if len(items) > 1:
        sep = text[items[0][1]:items[1][0]]
    else:
        sep = ", "
    pos = items[-1][1]
    return (pos, pos, "".join(f"{sep}{q}{n}{q}" for n in new_ids)), added


_SELECT_OPEN = re.compile(r"<select\b", re.I)
_SELECT_CLOSE = re.compile(r"</select\s*>", re.I)


def _splice(raw: str, text: str, reps: list[tuple[int, int, str]], notebook: bool) -> str | None:
    """Apply edits (start, end, new text) found in `text` to the raw line. For a notebook,
    `text` is the decoded JSON string: each id is replaced at its n-th occurrence in the raw
    line (ids have no characters JSON escapes), or None if the occurrences don't line up."""
    if not notebook:
        pieces, last = [], 0
        for s, e, new in reps:
            pieces += [raw[last:s], new]
            last = e
        return "".join(pieces) + raw[last:]
    out, cuts = raw, []
    for s, e, new in reps:
        old = text[s:e]
        if not old:
            return None
        nth = text.count(old, 0, s)
        if text.count(old) != raw.count(old):
            return None
        pos = -1
        for _ in range(nth + 1):
            pos = raw.find(old, pos + 1)
        if pos < 0:
            return None
        cuts.append((pos, pos + len(old), new))
    for a, b, new in sorted(cuts, reverse=True):
        out = out[:a] + new + out[b:]
    return out


def _unified(old_lines: list[str], new_lines: list[str], rel: str) -> str:
    """Unified diff that `git apply` / `patch` accept, incl. files without a final newline."""
    out = []
    for ln in difflib.unified_diff(old_lines, new_lines, f"a/{rel}", f"b/{rel}"):
        if ln.endswith("\n"):
            out.append(ln)
        else:
            out.append(ln + "\n\\ No newline at end of file\n")
    return "".join(out)


def write(result: SwapResult, out_dir: str | Path) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    _mark(out)
    p, s = out / "model-swap.diff", out / "swap-summary.json"
    p.write_text(result.diff)
    s.write_text(json.dumps(result.summary(), indent=2))
    return p, s


def apply_in_place(root: str | Path, result: SwapResult) -> int:
    root = Path(root).resolve()
    for rel, text in result.new_contents.items():
        (root / rel).write_text(text, encoding="utf-8")
    return len(result.new_contents)
