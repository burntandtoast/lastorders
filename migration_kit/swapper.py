# Copyright (c) 2026 Burnt and Toast Studios Ltd. Proprietary; see LICENSE-COMMERCIAL.
"""`swap`: turn a mapping file into a reviewable unified diff."""
from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .scanner import mark_output as _mark
from .packs import PackSet, load_packs
from .scanner import classify, iter_files, iter_model_tokens, iter_rows


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

    def summary(self) -> dict:
        return {
            "files_changed": len(self.new_contents),
            "replacements": len(self.changes),
            "skipped_fine_tunes": [{"file": f, "line": l, "model": m} for f, l, m in self.skipped_fine_tunes],
            "skipped_name_checks": [{"file": f, "line": l, "model": m} for f, l, m in self.skipped_name_checks],
            "skipped_not_swappable": [{"file": f, "line": l, "model": m, "reason": r}
                                      for f, l, m, r in self.skipped_unsafe],
            "changes": [c.__dict__ for c in self.changes],
        }


def plan(root: str | Path, mapping: Mapping, packs: PackSet | None = None) -> SwapResult:
    root = Path(root).resolve()
    packs = packs or load_packs()
    changes: list[Change] = []
    skipped: list[tuple[str, int, str]] = []
    name_checks: list[tuple[str, int, str]] = []
    unsafe: list[tuple[str, int, str, str]] = []
    diffs: list[str] = []
    new_contents: dict[str, str] = {}
    table = {**mapping.replacements, **mapping.fine_tuned}
    for path, lang in iter_files(root, include_docs=mapping.include_docs):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(root).as_posix()
        old_lines = text.splitlines(keepends=True)
        new_lines = list(old_lines)
        rows, _ = iter_rows(text, path, lang)
        for row in rows:
            if row.mode is None:
                continue
            i, text_line = row.index + 1, row.text
            reps: list[tuple[int, int, str, str]] = []
            for s, e, model, pack in iter_model_tokens(text_line, packs, row.lang, row.prev, row.mode):
                if pack.fine_tune_base(model) is not None and model not in mapping.fine_tuned:
                    skipped.append((rel, i, model))
                    continue
                if model not in table:
                    continue
                kind, block = classify(text_line, s, e, row.lang, row.prev, row.mode, rel)
                if block == "name_check":
                    # `startsWith("o1")` is a family check; renaming it changes the logic.
                    name_checks.append((rel, i, model))
                    continue
                if block:
                    unsafe.append((rel, i, model, block))
                    continue
                if kind == "doc" and lang in ("html", "ipynb") and not mapping.include_docs:
                    continue                  # an HTML code sample or a notebook markdown cell: docs
                reps.append((s, e, model, table[model]))
            if not reps:
                continue
            new = _splice(old_lines[row.index], text_line, reps, lang == "ipynb")
            if new is None:
                unsafe.extend((rel, i, m, "notebook") for _, _, m, _ in reps)
                continue
            new_lines[row.index] = new
            changes.extend(Change(rel, i, m, n) for _, _, m, n in reps)
        if new_lines != old_lines:
            new_contents[rel] = "".join(new_lines)
            diffs.append(_unified(old_lines, new_lines, rel))
    return SwapResult(changes, skipped, "".join(diffs), new_contents, name_checks, unsafe)


def _splice(raw: str, text: str, reps: list[tuple[int, int, str, str]], notebook: bool) -> str | None:
    """Apply replacements found in `text` to the raw line. For a notebook, `text` is the
    decoded JSON string: each id is replaced at its n-th occurrence in the raw line (ids
    have no characters JSON escapes), or None if the occurrences don't line up."""
    if not notebook:
        pieces, last = [], 0
        for s, e, _, new in reps:
            pieces += [raw[last:s], new]
            last = e
        return "".join(pieces) + raw[last:]
    out, cuts = raw, []
    for s, e, old, new in reps:
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
