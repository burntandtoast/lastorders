"""`scan`: find model IDs in a repository and assess them."""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import catalogue as cat

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build",
             ".next", ".nuxt", ".cache", "coverage", ".tox", ".mypy_cache", ".pytest_cache",
             "site-packages", ".idea", ".vscode", "vendor"}
CODE_EXT = {".py": "python", ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
            ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript"}
CONFIG_EXT = {".yaml": "yaml", ".yml": "yaml", ".json": "json", ".toml": "toml", ".ini": "ini",
              ".cfg": "ini", ".conf": "ini"}
DOC_EXT = {".md": "markdown", ".txt": "text", ".rst": "text"}
MAX_BYTES = 2_000_000

# A model-id token: ft:..., gpt-*, chatgpt-*, or an o-series id.
_B = r"(?<![A-Za-z0-9._:/-])"
_E = r"(?![A-Za-z0-9._:-])"
MODEL_RE = re.compile(
    _B + r"(ft:[A-Za-z0-9._-]+(?::[A-Za-z0-9._-]*)*"
    r"|gpt-[0-9][A-Za-z0-9._-]*[A-Za-z0-9]"
    r"|gpt-[0-9]"
    r"|chatgpt-[A-Za-z0-9._-]*[A-Za-z0-9]"
    r"|o[1-9](?:-(?:mini|pro|preview|deep-research)(?:-[0-9]{4}-[0-9]{2}-[0-9]{2})?|-[0-9]{4}-[0-9]{2}-[0-9]{2})?)" + _E
)
# o-series ids are only trusted inside quotes or after '=' (too ambiguous in prose)
O_SERIES_RE = re.compile(r"^o[1-9]")

MODEL_KEY_RE = re.compile(r"""(?:\bmodel(?:_name|_id|Name|Id)?\b|\bdeployment\b|\bengine\b)\s*["']?\s*[:=]""", re.I)
ENV_REF_RE = re.compile(
    r"""(?:os\.environ\.get|os\.getenv|os\.environ\[|process\.env\.|process\.env\[|import\.meta\.env\.)\(?\s*["']?([A-Z][A-Z0-9_]*MODEL[A-Z0-9_]*)""")

# Simple per-file signals of API usage patterns that change risk.
SIGNALS = {
    "chat_completions": re.compile(r"chat\.completions\.create|/v1/chat/completions|ChatCompletion\.create"),
    "responses_api": re.compile(r"responses\.create|/v1/responses"),
    "tools": re.compile(r"\btools\s*[=:]|tool_choice|\bfunction_call\b|\bfunctions\s*[=:]"),
    "legacy_functions": re.compile(r"\bfunctions\s*[=:]|\bfunction_call\s*[=:]"),
    "structured_output": re.compile(r"json_schema|response_format|text_format|zodResponseFormat|\.parse\("),
    "sampling_params": re.compile(r"\btemperature\b|\btop_p\b|\bmax_tokens\b|\blogprobs\b|\bpresence_penalty\b|\bfrequency_penalty\b"),
    "assistants_api": re.compile(r"beta\.assistants|/v1/assistants|beta\.threads"),
    "legacy_completions": re.compile(r"\bcompletions\.create\b(?<!chat\.completions\.create)|/v1/completions\b"),
    "fine_tuning_jobs": re.compile(r"fine_tuning\.jobs|fineTuning\.jobs|/v1/fine_tuning"),
}


@dataclass
class Finding:
    file: str
    line: int
    column: int
    model: str
    kind: str            # sdk_call | env | config | string_literal | doc | comment
    language: str
    snippet: str
    category: str        # in_scope | fine_tune | other_deprecated | not_listed
    shutdown: str | None
    suggested: str | None
    confidence: str
    risk: str            # high | medium | low | info
    notes: list[str] = field(default_factory=list)


@dataclass
class EnvRef:
    file: str
    line: int
    variable: str
    snippet: str


@dataclass
class ScanResult:
    root: str
    files_scanned: int
    findings: list[Finding]
    env_refs: list[EnvRef]
    file_signals: dict[str, list[str]]
    checked_on: str = cat.CHECKED_ON
    source: str = cat.DEPRECATIONS_URL

    def to_dict(self) -> dict:
        d = {
            "root": self.root, "files_scanned": self.files_scanned,
            "checked_on": self.checked_on, "source": self.source,
            "summary": summarise(self),
            "findings": [asdict(f) for f in self.findings],
            "env_refs": [asdict(e) for e in self.env_refs],
            "file_signals": self.file_signals,
        }
        return d


def _language(path: Path) -> str | None:
    name = path.name
    if name.startswith(".env") or name.endswith(".env"):
        return "env"
    ext = path.suffix.lower()
    return CODE_EXT.get(ext) or CONFIG_EXT.get(ext) or DOC_EXT.get(ext)


def iter_files(root: Path, include_docs: bool = True):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            lang = _language(p)
            if lang is None:
                continue
            if not include_docs and lang in ("markdown", "text"):
                continue
            try:
                if p.stat().st_size > MAX_BYTES:
                    continue
            except OSError:
                continue
            yield p, lang


def _is_comment(line: str, lang: str) -> bool:
    s = line.strip()
    if lang == "python" or lang in ("yaml", "toml", "ini", "env"):
        return s.startswith("#")
    if lang in ("javascript", "typescript"):
        return s.startswith("//") or s.startswith("/*") or s.startswith("*")
    return False


def _kind(line: str, lang: str, prev: str) -> str:
    if lang in ("markdown", "text"):
        return "doc"
    if _is_comment(line, lang):
        return "comment"
    if lang == "env":
        return "env"
    if lang in CONFIG_EXT.values():
        return "config"
    if MODEL_KEY_RE.search(line) or MODEL_KEY_RE.search(prev):
        return "sdk_call"
    return "string_literal"


def _quoted_or_assigned(line: str, start: int, end: int) -> bool:
    before = line[:start].rstrip()
    after = line[end:end + 1]
    return (before[-1:] in "\"'`=:" and True) or after in ("\"", "'", "`")


def classify(model: str) -> tuple[str, cat.Entry | None, str | None]:
    """Return (category, entry, base_model_for_fine_tune)."""
    base = cat.base_of_fine_tune(model)
    if base is not None:
        return "fine_tune", cat.lookup(base), base
    e = cat.lookup(model)
    if e is None:
        return "not_listed", None, None
    return ("in_scope" if e.in_scope else "other_deprecated"), e, None


def _assess(f: Finding, entry: cat.Entry | None, base: str | None, signals: list[str]) -> None:
    notes = f.notes
    if f.category == "fine_tune":
        f.risk = "high"
        if entry and entry.in_scope:
            f.shutdown = entry.shutdown
            notes.append(f"Fine-tune of {base}; per OpenAI it shuts down with its base model on {entry.shutdown}.")
        elif entry:
            f.shutdown = entry.shutdown
            notes.append(f"Fine-tune of {base} (base shutdown {entry.shutdown}).")
        else:
            notes.append(f"Fine-tune of {base}; base model not in the kit's catalogue - check manually.")
        f.suggested = None
        notes.append("No automatic replacement: gpt-6-luna does not support fine-tuning. Options are "
                     "prompting/few-shot on gpt-6-luna validated with `eval`, or re-training on a "
                     "fine-tunable model (none confirmed by the kit). New fine-tuning jobs stop on 6 Jan 2027.")
        f.confidence = "confirmed" if entry and entry.confidence == "confirmed" else "inferred"
        return
    if entry is None:
        f.risk = "info"
        f.suggested = None
        f.confidence = "n/a"
        notes.append("Not in the kit's deprecation catalogue. Leave as-is unless the client wants to consolidate.")
        return
    f.shutdown, f.suggested, f.confidence = entry.shutdown, entry.replacement, entry.confidence
    if entry.note:
        notes.append(entry.note)
    if f.category == "in_scope":
        f.risk = "medium"
        if "tools" in signals and "chat_completions" in signals:
            f.risk = "high"
            notes.append("Chat Completions + tools in this file: gpt-6-luna supports function calling on "
                         "Chat Completions only with reasoning_effort set to 'none' (or move to the Responses API).")
        if "legacy_functions" in signals:
            notes.append("Uses legacy `functions`/`function_call` parameters - check support and prefer `tools`.")
        if "structured_output" in signals:
            notes.append("Structured output in this file: gpt-6-luna lists structured_outputs as supported; verify schemas with `eval`.")
        if "sampling_params" in signals:
            notes.append("Sets sampling/length params (temperature, max_tokens, etc.). gpt-6-luna is a reasoning "
                         "model; the kit could not confirm which of these it accepts - test with `eval`.")
        if "assistants_api" in signals:
            f.risk = "high"
            notes.append("Assistants API detected: gpt-6-luna does not support it (and the Assistants API shut down 26 Aug 2026).")
        if "legacy_completions" in signals:
            f.risk = "high"
            notes.append("Legacy /v1/completions detected: gpt-6-luna does not support it.")
    else:
        f.risk = "high" if (entry.shutdown or "9") < cat.PRIMARY_SHUTDOWN else "medium"
        notes.append(f"Outside the GPT-4o/4.1 migration; OpenAI's listed replacement is {entry.replacement}.")
    if f.kind in ("doc", "comment"):
        f.risk = "low"
        notes.append("Appears in documentation/comment only.")


def scan(root: str | Path, include_docs: bool = True) -> ScanResult:
    root = Path(root).resolve()
    findings: list[Finding] = []
    env_refs: list[EnvRef] = []
    file_signals: dict[str, list[str]] = {}
    n = 0
    for path, lang in iter_files(root, include_docs):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        n += 1
        rel = path.relative_to(root).as_posix()
        sig = [k for k, rx in SIGNALS.items() if lang in ("python", "javascript", "typescript") and rx.search(text)]
        lines = text.splitlines()
        file_hits = []
        for i, line in enumerate(lines, 1):
            prev = lines[i - 2] if i > 1 else ""
            for m in MODEL_RE.finditer(line):
                model = m.group(1)
                if O_SERIES_RE.match(model) and not _quoted_or_assigned(line, m.start(1), m.end(1)):
                    continue
                category, entry, base = classify(model)
                f = Finding(rel, i, m.start(1) + 1, model, _kind(line, lang, prev), lang,
                            line.strip()[:200], category, None, None, "n/a", "info")
                _assess(f, entry, base, sig)
                file_hits.append(f)
            for m in ENV_REF_RE.finditer(line):
                env_refs.append(EnvRef(rel, i, m.group(1), line.strip()[:200]))
        if file_hits or sig:
            if sig:
                file_signals[rel] = sig
        findings.extend(file_hits)
    return ScanResult(str(root), n, findings, env_refs, file_signals)


def summarise(res: ScanResult) -> dict:
    by_cat: dict[str, int] = {}
    by_risk: dict[str, int] = {}
    for f in res.findings:
        by_cat[f.category] = by_cat.get(f.category, 0) + 1
        by_risk[f.risk] = by_risk.get(f.risk, 0) + 1
    return {
        "total_findings": len(res.findings),
        "by_category": by_cat,
        "by_risk": by_risk,
        "files_with_findings": len({f.file for f in res.findings}),
        "fine_tuned_models": sorted({f.model for f in res.findings if f.category == "fine_tune"}),
        "env_var_model_refs": sorted({e.variable for e in res.env_refs}),
    }


CAT_LABEL = {"in_scope": "GPT-4o / 4.1 (shutdown 14 Jan 2027)", "fine_tune": "Fine-tuned model",
             "other_deprecated": "Other deprecated model", "not_listed": "Not in catalogue"}


def to_markdown(res: ScanResult) -> str:
    s = summarise(res)
    out = [f"# Model scan report", "",
           f"- Repository: `{res.root}`",
           f"- Files scanned: {res.files_scanned}",
           f"- Findings: {s['total_findings']} in {s['files_with_findings']} files",
           f"- Deprecation data: {res.source} (checked {res.checked_on})", ""]
    out.append("| Risk | Count |\n|---|---|")
    for r in ("high", "medium", "low", "info"):
        if s["by_risk"].get(r):
            out.append(f"| {r} | {s['by_risk'][r]} |")
    out.append("")
    order = ["fine_tune", "in_scope", "other_deprecated", "not_listed"]
    for c in order:
        items = [f for f in res.findings if f.category == c]
        if not items:
            continue
        out += [f"## {CAT_LABEL[c]}", "",
                "| File | Line | Current model | Suggested | Shutdown | Risk | Kind | Notes |",
                "|---|---|---|---|---|---|---|---|"]
        for f in items:
            notes = "<br>".join(n.replace("|", "\\|") for n in f.notes)
            sug = f"`{f.suggested}`" if f.suggested else "manual decision"
            conf = " (inferred)" if f.confidence == "inferred" else ""
            out.append(f"| `{f.file}` | {f.line} | `{f.model}` | {sug}{conf} | {f.shutdown or '-'} | "
                       f"**{f.risk}** | {f.kind} | {notes} |")
        out.append("")
    if res.env_refs:
        out += ["## Models read from environment variables", "",
                "These are set outside the repo (hosting dashboard, CI secrets, .env on servers). "
                "Check their deployed values too.", "",
                "| File | Line | Variable |", "|---|---|---|"]
        for e in res.env_refs:
            out.append(f"| `{e.file}` | {e.line} | `{e.variable}` |")
        out.append("")
    return "\n".join(out)


def write_reports(res: ScanResult, out_dir: str | Path) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    j, m = out / "scan.json", out / "scan.md"
    j.write_text(json.dumps(res.to_dict(), indent=2))
    m.write_text(to_markdown(res))
    return j, m
