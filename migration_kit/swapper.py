"""`swap`: turn a mapping file into a reviewable unified diff."""
from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .scanner import MODEL_RE, O_SERIES_RE, _quoted_or_assigned, iter_files


@dataclass
class Mapping:
    replacements: dict[str, str]
    fine_tuned: dict[str, str] = field(default_factory=dict)
    include_docs: bool = False
    source: str = ""


def load_mapping(path: str | Path) -> Mapping:
    data = yaml.safe_load(Path(path).read_text()) or {}
    reps = {str(k): str(v) for k, v in (data.get("mappings") or {}).items()}
    for k in reps:
        if k.startswith("ft:"):
            raise ValueError(f"Fine-tuned id {k!r} belongs under 'fine_tuned:', not 'mappings:'")
    ft = {str(k): str(v) for k, v in (data.get("fine_tuned") or {}).items()}
    return Mapping(reps, ft, bool(data.get("include_docs", False)), str(data.get("source", "")))


@dataclass
class Change:
    file: str
    line: int
    old: str
    new: str


@dataclass
class SwapResult:
    changes: list[Change]
    skipped_fine_tunes: list[tuple[str, int, str]]
    diff: str
    new_contents: dict[str, str]

    def summary(self) -> dict:
        return {
            "files_changed": len(self.new_contents),
            "replacements": len(self.changes),
            "skipped_fine_tunes": [{"file": f, "line": l, "model": m} for f, l, m in self.skipped_fine_tunes],
            "changes": [c.__dict__ for c in self.changes],
        }


def plan(root: str | Path, mapping: Mapping) -> SwapResult:
    root = Path(root).resolve()
    changes: list[Change] = []
    skipped: list[tuple[str, int, str]] = []
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
        new_lines = []
        for i, line in enumerate(old_lines, 1):
            pieces, last = [], 0
            for m in MODEL_RE.finditer(line):
                model = m.group(1)
                if O_SERIES_RE.match(model) and not _quoted_or_assigned(line, m.start(1), m.end(1)):
                    continue
                if model.startswith("ft:") and model not in mapping.fine_tuned:
                    skipped.append((rel, i, model))
                    continue
                if model in table:
                    pieces.append(line[last:m.start(1)])
                    pieces.append(table[model])
                    last = m.end(1)
                    changes.append(Change(rel, i, model, table[model]))
            pieces.append(line[last:])
            new_lines.append("".join(pieces))
        if new_lines != old_lines:
            new_text = "".join(new_lines)
            new_contents[rel] = new_text
            diffs.append(_unified(old_lines, new_lines, rel))
    return SwapResult(changes, skipped, "".join(diffs), new_contents)


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
    p, s = out / "model-swap.diff", out / "swap-summary.json"
    p.write_text(result.diff)
    s.write_text(json.dumps(result.summary(), indent=2))
    return p, s


def apply_in_place(root: str | Path, result: SwapResult) -> int:
    root = Path(root).resolve()
    for rel, text in result.new_contents.items():
        (root / rel).write_text(text, encoding="utf-8")
    return len(result.new_contents)
