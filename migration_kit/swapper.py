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
from .scanner import _is_comment, classify, iter_files, iter_model_tokens, iter_prefix_checks, iter_rows, list_bounds


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
    # Distinct ids in one list, set, object/dict or <select> that map to the same new id.
    # {"file", "line", "container", "target", "old"}.
    collapsed: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "files_changed": len(self.new_contents),
            "replacements": len(self.changes),
            "must_update_together": self.must_update_together,
            "collapsed_targets": self.collapsed,
            "skipped_fine_tunes": [{"file": f, "line": l, "model": m} for f, l, m in self.skipped_fine_tunes],
            "skipped_name_checks": [{"file": f, "line": l, "model": m} for f, l, m in self.skipped_name_checks],
            "skipped_not_swappable": [{"file": f, "line": l, "model": m, "reason": r}
                                      for f, l, m, r in self.skipped_unsafe],
            "changes": [c.__dict__ for c in self.changes],
        }

    def warnings(self) -> list[str]:
        """Human-readable lines for the swap output (empty when there is nothing to check)."""
        out = []
        for w in self.must_update_together:
            out.append(f"MUST UPDATE TOGETHER {w['file']}:{w['line']} {w['model']}: {w['reason']}")
        for c in self.collapsed:
            tail = ("the new id is added once" if c["container"].startswith("allow-list")
                    else "check for duplicate entries or keys")
            out.append(f"COLLAPSED {c['file']}:{c['line']} ({c['container']}): {', '.join(c['old'])} all become "
                       f"{c['target']}; {tail}")
        return out


_REASONS = {
    "name_check": ("prefix/substring check left unchanged (renaming it changes its logic); swap renames {related} "
                   "elsewhere, so this check no longer matches after the swap. Update it by hand."),
    "multiline": ("exact-match allow-list that doesn't fit on one line or holds more than quoted ids; swap renames "
                  "{related} elsewhere, so add the new id to this list by hand."),
    "notebook": ("exact-match allow-list in a notebook cell; swap renames {related} elsewhere, so add the new id "
                 "to this list by hand."),
}


@dataclass
class _Row:
    index: int
    line: int
    text: str
    reps: list = field(default_factory=list)        # (s, e, old, new)
    allow: list = field(default_factory=list)       # (s, e, old)


def plan(root: str | Path, mapping: Mapping, packs: PackSet | None = None) -> SwapResult:
    root = Path(root).resolve()
    packs = packs or load_packs()
    skipped: list[tuple[str, int, str]] = []
    unsafe: list[tuple[str, int, str, str]] = []
    table = {**mapping.replacements, **mapping.fine_tuned}
    files: list[tuple[str, str, list[str], dict[int, _Row]]] = []
    checks: list[tuple[str, int, str]] = []          # prefix / substring name checks, in order
    family: list[tuple[str, int, str]] = []          # name checks on ids outside the mapping
    renamed: set[str] = set()                        # ids renamed in code (not comments / docs)
    # Pass 1: what each row would rename, and the checks that depend on it.
    for path, lang in iter_files(root, include_docs=mapping.include_docs):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(root).as_posix()
        rows, _ = iter_rows(text, path, lang)
        todo: dict[int, _Row] = {}
        for row in rows:
            if row.mode is None:
                continue
            i, text_line = row.index + 1, row.text
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
                r = todo.setdefault(row.index, _Row(row.index, i, text_line))
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
                r.reps.append((s, e, model, table[model]))
                if kind not in ("doc", "comment"):
                    renamed.add(model)
        if todo:
            files.append((rel, lang, text.splitlines(keepends=True), todo))
    # Pass 2: apply, adding new ids to allow-lists whose ids are renamed elsewhere.
    changes: list[Change] = []
    name_checks: list[tuple[str, int, str]] = []
    must: list[dict] = []
    collapsed: list[dict] = []
    diffs: list[str] = []
    new_contents: dict[str, str] = {}
    name_checks.extend(checks)
    for rel, i, model in checks + family:
        related = sorted(r for r in renamed if model in r)
        if related:
            must.append({"file": rel, "line": i, "model": model, "related": related, "kind": "name_check",
                         "reason": _REASONS["name_check"].format(related=", ".join(related))})
    for rel, lang, old_lines, todo in files:
        new_lines = list(old_lines)
        groups: dict[object, dict[str, set[str]]] = {}
        containers = _container_keys(old_lines, lang, todo) if todo else {}
        for idx, r in sorted(todo.items()):
            edits: list[tuple[int, int, str]] = [(s, e, new) for s, e, _, new in r.reps]
            row_changes = [Change(rel, r.line, m, n) for _, _, m, n in r.reps]
            for s, e, m, n in r.reps:
                key = containers.get((idx, s))
                if key is not None:
                    groups.setdefault(key, {}).setdefault(n, set()).add(m)
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
                    kind = key[0] if isinstance(key, tuple) else "list"
                    line = (key[1] + 1) if isinstance(key, tuple) else 0
                    collapsed.append({"file": rel, "line": line,
                                      "container": {"allow": "allow-list (new id added once)",
                                                    "select": "<select> dropdown", "list": "list/set/object"}[kind],
                                      "target": target, "old": sorted(olds)})
        if new_lines != old_lines:
            new_contents[rel] = "".join(new_lines)
            diffs.append(_unified(old_lines, new_lines, rel))
    collapsed.sort(key=lambda c: (c["file"], c["line"]))
    must.sort(key=lambda w: (w["file"], w["line"]))
    return SwapResult(changes, skipped, "".join(diffs), new_contents, name_checks, unsafe, must, collapsed)


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


_COMMENT_START = {"python": "#", "r": "#", "yaml": "#", "toml": "#", "ini": "#", "env": "#", "shell": "#",
                  "make": "#", "javascript": "//", "typescript": "//", "go": "//", "rust": "//", "csharp": "//",
                  "php": "//", "html": None, "mdx": None}
_SELECT_OPEN = re.compile(r"<select\b", re.I)
_SELECT_CLOSE = re.compile(r"</select\s*>", re.I)


def _container_keys(lines: list[str], lang: str, todo: dict) -> dict[tuple[int, int], object]:
    """For each (row index, column) being renamed, the list/set/dict/<select> it sits in
    (a hashable key), so ids that collapse to the same new id can be reported. Brackets
    are tracked across lines; quotes are skipped and reset at each line end."""
    want = {idx: sorted(s for s, _, _, _ in r.reps) for idx, r in todo.items() if r.reps}
    out: dict[tuple[int, int], object] = {}
    if not want or lang == "ipynb":
        return out
    if lang == "html":
        sel = None
        for idx, raw in enumerate(lines):
            if sel is None and _SELECT_OPEN.search(raw):
                sel = idx
            if sel is not None:
                for s in want.get(idx, []):
                    out[(idx, s)] = ("select", sel)
            if sel is not None and _SELECT_CLOSE.search(raw):
                sel = None
        return out
    cmt = _COMMENT_START.get(lang, "#")
    stack: list[tuple[str, int, int]] = []
    for idx, raw in enumerate(lines):
        cols = want.get(idx, [])
        ci = 0
        q = None
        k = 0
        n = len(raw)
        while k < n:
            while ci < len(cols) and cols[ci] <= k:
                if stack and stack[-1][0] in "[{":
                    out[(idx, cols[ci])] = ("list", stack[-1][1], stack[-1][2])
                ci += 1
            c = raw[k]
            if q:
                if c == "\\":
                    k += 2
                    continue
                if c == q:
                    q = None
            elif c in "\"'`":
                q = c
            elif cmt and raw.startswith(cmt, k):
                break
            elif c in "[({":
                stack.append((c, idx, k))
            elif c in "])}":
                if stack:
                    stack.pop()
            k += 1
        while ci < len(cols):
            if stack and stack[-1][0] in "[{":
                out[(idx, cols[ci])] = ("list", stack[-1][1], stack[-1][2])
            ci += 1
    return out


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
