"""`scan`: generic engine. Finds model IDs in a repository and assesses them using
migration packs (see packs.py). No provider-specific logic lives here."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import brand
from .packs import Pack, PackSet, load_packs

SKIP_DIRS = {".git", ".venv", "venv", "env", "__pycache__", "build",
             ".next", ".nuxt", ".cache", "coverage", ".tox", ".mypy_cache", ".pytest_cache",
             "site-packages", ".idea", ".vscode"}
# Collapsed to one summary line unless --include-generated. Not findings, so they
# do not count toward --fail-on-high.
VENDORED_DIRS = {"vendor", "third_party", "node_modules", ".yarn", "dist"}
CODE_EXT = {".py": "python", ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
            ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript",
            ".r": "r", ".rmd": "r", ".qmd": "r",
            ".php": "php", ".rs": "rust", ".cs": "csharp", ".go": "go", ".ejs": "ejs",
            ".sh": "shell", ".bash": "shell", ".zsh": "shell", ".http": "http", ".rest": "http",
            ".html": "html", ".htm": "html", ".mdx": "mdx"}
CONFIG_EXT = {".yaml": "yaml", ".yml": "yaml", ".json": "json", ".toml": "toml", ".ini": "ini",
              ".cfg": "ini", ".conf": "ini"}
DOC_EXT = {".md": "markdown", ".txt": "text", ".rst": "text"}
CODE_LANGS = set(CODE_EXT.values())
CONFIG_LANGS = set(CONFIG_EXT.values()) | {"env"}
DOC_LANGS = {"markdown", "text"}
# Skipped with --no-docs (and by swap/fix unless include_docs). .mdx is documentation
# even though its code fences are scanned at normal severity.
DOCS_SKIP_LANGS = DOC_LANGS | {"mdx"}
# Prose outside ``` fences is documentation; code chunks are source.
LITERATE_EXT = {".rmd", ".qmd", ".mdx"}
# Extensionless scripts: only a text file whose first line is a shebang for one of these.
SHEBANG_RE = re.compile(rb"^#![ \t]*(?:\S*/)?(?:env[ \t]+(?:-\S+[ \t]+)*)?(?:\S*/)?([A-Za-z][A-Za-z-]*)")
SHEBANG_LANG = {"python": "python", "node": "javascript", "nodejs": "javascript", "bun": "javascript",
                "deno": "typescript", "tsx": "typescript", "ts-node": "typescript",
                "bash": "shell", "sh": "shell", "zsh": "shell", "dash": "shell", "ksh": "shell"}
MAX_BYTES = 2_000_000
RISK_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3}

MODEL_KEY_RE = re.compile(r"""(?:\bmodel(?:_name|_id|Name|Id)?\b|\bdeployment\b|\bengine\b)\s*["']?\s*[:=]""", re.I)
# The key must sit immediately before a short id (`model = "o1"`, `engine: o3`).
# A bare `=o1(` in minified code is not this.
_SHORT_KEY_BEFORE = re.compile(
    r"""(?:\bmodel(?:_name|_id|Name|Id)?\b|\bdeployment\b|\bengine\b)\s*["']?\s*(?:=>|[:=])\s*["']?\s*$""", re.I)
# A prefixed identifier key such as `orgId: "o1"` or `organization_id: "o1"`
# sits immediately before the token. Bare `id` is not this: model catalogues use
# `{ id: "o3-mini" }`. Model keys (`modelId`, `model_id`) are not this either.
_ID_KEY = re.compile(r"""(?:[a-z0-9]Ids?$|[a-zA-Z0-9]IDs?$|_ids?$|_IDs?$)""")
_MODEL_KEY_NAME = re.compile(r"model|deployment|engine", re.I)
# Docs search indexes (pkgdown, MkDocs, Sphinx, Hugo, Jekyll) under a docs output folder.
SEARCH_INDEX_NAMES = {"search.json", "search_index.json", "searchindex.js", "searchindex.json",
                      "search-index.json", "search_index.js"}
DOCS_OUTPUT_DIRS = {"docs", "site", "_build", "public", "_site"}
GENERATED_HEADER = re.compile(r"@generated|DO NOT EDIT|auto-generated", re.I)
ENV_REF_RE = re.compile(
    r"""(?:os\.environ\.get|os\.getenv|os\.environ\[|process\.env\.|process\.env\[|import\.meta\.env\.)\(?\s*["']?([A-Z][A-Z0-9_]*MODEL[A-Z0-9_]*)""")


@dataclass
class Finding:
    file: str
    line: int
    column: int
    model: str
    provider: str
    kind: str            # sdk_call | env | config | string_literal | doc | comment
    language: str
    snippet: str
    category: str        # in_scope | fine_tune | other_deprecated | not_listed
    shutdown: str | None
    suggested: str | None
    confidence: str
    risk: str            # high | medium | low | info
    migration: str | None = None
    rules: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    auto_swap: bool = True   # False for flag-only models (fix/swap never rewrite them)


@dataclass
class EnvRef:
    file: str
    line: int
    variable: str
    snippet: str


@dataclass
class SkippedFile:
    """A generated, minified or vendored file collapsed to one line."""
    file: str
    count: int
    reason: str          # generated | vendored | minified

    def line(self) -> str:
        noun = "model ID" if self.count == 1 else "model IDs"
        kind = {"generated": "a generated file", "vendored": "a vendored file", "minified": "a minified file"}[self.reason]
        return f"{self.file}: {self.count} {noun} in {kind}, skipped; use --include-generated to scan it"


@dataclass
class ScanResult:
    root: str
    files_scanned: int
    findings: list[Finding]
    env_refs: list[EnvRef]
    file_signals: dict[str, list[str]]
    file_sdks: dict[str, list[str]]
    packs: list[dict]
    scanned_on: str
    skipped: list[SkippedFile] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tool": brand.CLI_NAME, "root": self.root, "files_scanned": self.files_scanned,
            "scanned_on": self.scanned_on, "packs": self.packs,
            "summary": summarise(self),
            "findings": [asdict(f) for f in self.findings],
            "env_refs": [asdict(e) for e in self.env_refs],
            "file_signals": self.file_signals, "file_sdks": self.file_sdks,
            "skipped_generated": [asdict(s) for s in self.skipped],
        }


def _shebang_language(path: Path) -> str | None:
    """`#!/usr/bin/env python3`, `#!/bin/bash`, ... on an extensionless text file."""
    try:
        with path.open("rb") as fh:
            head = fh.read(256)
    except OSError:
        return None
    if not head.startswith(b"#!") or b"\0" in head:
        return None
    m = SHEBANG_RE.match(head)
    if not m:
        return None
    name = m.group(1).decode("ascii").lower()
    return SHEBANG_LANG.get(name) or SHEBANG_LANG.get(name.rstrip("-"))


def _language(path: Path) -> str | None:
    name = path.name
    if name.startswith(".env") or name.endswith(".env"):
        return "env"
    ext = path.suffix.lower()
    lang = CODE_EXT.get(ext) or CONFIG_EXT.get(ext) or DOC_EXT.get(ext)
    if lang is None and not ext and not name.startswith(".") and path.is_file() and not path.is_symlink():
        return _shebang_language(path)
    return lang


_SCRIPT_OPEN = re.compile(r"<script\b[^>]*>", re.I)
_SCRIPT_CLOSE = re.compile(r"</script\s*>", re.I)
_HTML_COMMENT = re.compile(r"<!--.*?-->")


def line_modes(lines: list[str], path: Path | str, lang: str) -> list[bool | None]:
    """Per line: True = code, False = prose (documentation), None = not scanned.

    R Markdown / Quarto / MDX: prose outside ``` fences is documentation (the fence
    line itself too). HTML: only lines inside <script> blocks are scanned; markup is not.
    Everything else: every line is code."""
    suffix = Path(path).suffix.lower()
    if suffix in LITERATE_EXT:
        out: list[bool | None] = []
        in_code = False
        for line in lines:
            if line.strip().startswith("```"):
                out.append(False)
                in_code = not in_code
            else:
                out.append(in_code)
        return out
    if lang == "html":
        out = []
        in_script = False
        for raw in lines:
            line = raw if in_script else _HTML_COMMENT.sub(lambda m: " " * len(m.group(0)), raw)
            pos, touched = 0, in_script
            while True:
                if in_script:
                    m = _SCRIPT_CLOSE.search(line, pos)
                    if not m:
                        break
                    in_script, pos = False, m.end()
                else:
                    m = _SCRIPT_OPEN.search(line, pos)
                    if not m:
                        break
                    in_script, pos, touched = True, m.end(), True
            out.append(True if touched else None)
        return out
    return [True] * len(lines)


OUTPUT_MARKER = f".{brand.CLI_NAME}-output"   # dropped into every output folder so later runs skip it


def mark_output(out_dir: str | Path) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    m = out / OUTPUT_MARKER
    if not m.exists():
        m.write_text(f"Generated by {brand.CLI_NAME}; this folder is skipped by scans.\n")


def is_output_dir(path: Path) -> bool:
    return (path / OUTPUT_MARKER).exists()


def _name_skip_reason(name: str) -> str | None:
    if ".generated." in name or ".gen." in name or name.endswith("_pb2.py"):
        return "generated"
    if name.endswith(".min.js"):
        return "minified"
    return None


def _peek_head(path: Path, n: int = 5) -> str:
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            return "".join(next(fh, "") for _ in range(n))
    except OSError:
        return ""


def _is_docs_search_index(rel: str) -> bool:
    parts = Path(rel).parts
    name = parts[-1].lower() if parts else ""
    if name not in SEARCH_INDEX_NAMES:
        return False
    return bool(set(parts[:-1]) & DOCS_OUTPUT_DIRS)


def file_skip_reason(path: Path, rel: str, text: str | None = None) -> str | None:
    """Why this file is generated, minified or vendored, or None to scan it."""
    if set(Path(rel).parts) & VENDORED_DIRS:
        return "vendored"
    if _is_docs_search_index(rel):
        return "generated"
    named = _name_skip_reason(path.name)
    if named:
        return named
    head = "\n".join(text.splitlines()[:5]) if text is not None else _peek_head(path)
    if GENERATED_HEADER.search(head):
        return "generated"
    return None


def iter_files(root: Path, include_docs: bool = True, include_generated: bool = False):
    blocked = set(SKIP_DIRS) if include_generated else SKIP_DIRS | VENDORED_DIRS
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in blocked and not is_output_dir(Path(dirpath) / d))
        base = Path(dirpath)
        for fn in sorted(filenames):
            p = base / fn
            lang = _language(p)
            if lang is None or (not include_docs and lang in DOCS_SKIP_LANGS):
                continue
            try:
                if p.stat().st_size > MAX_BYTES:
                    continue
            except OSError:
                continue
            if not include_generated:
                rel = p.relative_to(root).as_posix()
                if file_skip_reason(p, rel) is not None:
                    continue
            yield p, lang


def _is_comment(line: str, lang: str) -> bool:
    s = line.strip()
    # Roxygen (`#'`) and Quarto/R Markdown chunk comments are `#` comments.
    if lang in ("python", "r", "yaml", "toml", "ini", "env", "shell"):
        return s.startswith("#")
    if lang in ("javascript", "typescript", "rust", "csharp", "go"):
        return s.startswith(("//", "/*", "*"))
    if lang == "html":       # inside <script>
        return s.startswith(("//", "/*", "*", "<!--"))
    if lang == "http":
        return s.startswith(("#", "//"))
    if lang == "mdx":        # inside a code fence (JS/TS, shell or Python snippets)
        return s.startswith(("//", "/*", "*", "#"))
    if lang == "php":
        # `#[Attribute]` is PHP 8 syntax, not a comment.
        return s.startswith(("//", "/*", "*")) or (s.startswith("#") and not s.startswith("#["))
    if lang == "ejs":
        return s.startswith(("<%#", "<!--"))
    return False


def _kind(line: str, lang: str, prev: str, in_code: bool = True) -> str:
    # R Markdown / Quarto prose sits outside ``` fences. That is documentation.
    # Code chunks are source; `#` inside a chunk is still a comment.
    if lang in DOC_LANGS or not in_code:
        return "doc"
    if _is_comment(line, lang):
        return "comment"
    if lang == "env":
        return "env"
    if lang in CONFIG_LANGS:
        return "config"
    if MODEL_KEY_RE.search(line) or MODEL_KEY_RE.search(prev):
        return "sdk_call"
    return "string_literal"


def _whole_quoted_token(line: str, start: int, end: int) -> bool:
    """The match is the entire quoted string: `"o1"`, `'o3-mini'`, not `=o1(` or `"use o1"`."""
    if start < 1 or end >= len(line):
        return False
    left, right = line[start - 1], line[end]
    return left == right and left in "\"'`"


def _config_value(line: str, start: int, end: int) -> bool:
    """The token is the whole value after `:` or `=`, or a YAML list item."""
    tail = line[end:].lstrip()
    if tail and tail[0] not in "#,}]":
        return False
    return bool(re.search(r"(?:[:=]\s*|-\s+)$", line[:start]))


def _non_model_id_key(before: str) -> bool:
    """`orgId: "o1"`, `organization_id: "o1"`, `rowId: 'o1'`: an identifier, not a model."""
    m = re.search(r"""(?<![\w$])["']?([A-Za-z_$][\w$]*)["']?\s*(?:=>|[:=])\s*["'`]?\s*$""", before)
    if not m:
        return False
    key = m.group(1)
    return bool(_ID_KEY.search(key)) and not _MODEL_KEY_NAME.search(key)


# A router / provider prefix right before a short id: `<provider>/o1`, `openrouter/<provider>/o4-mini`,
# `azure/o3-mini`. The last segment is the pack's provider name or an Azure host prefix
# (`azure`, `azure_ai`, `azure-<provider>`). The prefixed id must end the quoted string or value.
_ROUTER_PREFIX_RES: dict[str, re.Pattern] = {}


def _router_prefix_re(provider: str) -> re.Pattern:
    rx = _ROUTER_PREFIX_RES.get(provider)
    if rx is None:
        prov = re.escape(provider)
        rx = re.compile(r"""(?:(["'`])|[:=]\s*)(?:[A-Za-z0-9_.-]+/)*(?:""" + prov
                        + r"""|azure(?:[-_]?(?:ai|""" + prov + r"""))?)/$""", re.I)
        _ROUTER_PREFIX_RES[provider] = rx
    return rx


def router_prefixed(line: str, start: int, end: int, provider: str) -> bool:
    """`"<provider>/o1"` (closing quote matches) or `model: <provider>/o1` (end of the value)."""
    if not provider or start < 1 or line[start - 1] != "/":
        return False
    m = _router_prefix_re(provider).search(line[max(0, start - 120):start])
    if not m:
        return False
    if m.group(1):
        return end < len(line) and line[end] == m.group(1)
    tail = line[end:].lstrip()
    return not tail or tail[0] in "#,}]"


# A model-name check, not a pinned model: `m.startsWith("o1")`, `s.includes('o1')`,
# `name.startswith(("o1", "o3"))`, `strings.HasPrefix(m, "o1")`, `str_contains($m, 'o1')`,
# `"o1" in model`. The token is the whole quoted argument.
_NAME_CHECK_FN = (r"startsWith|endsWith|includes|indexOf|lastIndexOf|startswith|endswith|starts_with|ends_with"
                  r"|contains|Contains|StartsWith|EndsWith|HasPrefix|HasSuffix|str_starts_with|str_ends_with"
                  r"|str_contains|strpos|stripos|strstr|stristr|grepl")
_NAME_CHECK_BEFORE = re.compile(
    r"""\b(?:""" + _NAME_CHECK_FN + r""")\s*\(\s*(?:[^()"'`,]*,\s*)?[(\[]?\s*(?:(["'`])[^"'`]*\1\s*,\s*)*$""")
_IN_AFTER = re.compile(r"""\s+(?:not\s+)?in\s+[A-Za-z_$]""")


def is_name_check(line: str, start: int, end: int) -> bool:
    if not _whole_quoted_token(line, start, end):
        return False
    if _NAME_CHECK_BEFORE.search(line[max(0, start - 1 - 160):start - 1]):
        return True
    return bool(_IN_AFTER.match(line, end + 1))


def short_id_in_context(line: str, start: int, end: int, lang: str, prev: str, provider: str = "") -> bool:
    """Bare o1/o3-style ids count only in a model context, not in minified identifiers."""
    if _non_model_id_key(line[:start]):
        return False
    if _whole_quoted_token(line, start, end):
        return True
    if router_prefixed(line, start, end, provider):
        return True
    if _SHORT_KEY_BEFORE.search(line[:start]):
        return True
    if not line[:start].strip() and _SHORT_KEY_BEFORE.search(prev.rstrip()):
        return True
    return lang in CONFIG_LANGS and _config_value(line, start, end)


def iter_model_tokens(line: str, packs: PackSet, lang: str = "", prev: str = ""):
    """Yield (start, end, token, pack) for every model-id token on a line, longest match first per span."""
    seen: list[tuple[int, int]] = []
    hits = []
    for pack in packs:
        for rx, quoted_only in pack.id_res:
            for m in rx.finditer(line):
                if quoted_only and not short_id_in_context(line, m.start(1), m.end(1), lang, prev, pack.provider):
                    continue
                hits.append((m.start(1), m.end(1), m.group(1), pack))
    for s, e, tok, pack in sorted(hits, key=lambda h: (h[0], -(h[1] - h[0]))):
        if any(s < pe and e > ps for ps, pe in seen):
            continue
        seen.append((s, e))
        yield s, e, tok, pack


def file_signals(text: str, lang: str, packs: PackSet) -> tuple[list[str], list[str]]:
    sig, sdks = set(), set()
    if lang in DOC_LANGS:
        return [], []
    for pack in packs:
        for sid, rx, langs, sdk in pack.signals:
            if (not langs or lang in langs) and rx.search(text):
                sig.add(sid)
                if sdk:
                    sdks.add(f"{pack.provider}:{sdk}")
    return sorted(sig), sorted(sdks)


def _rule_applies(rule: dict, model_repl: str | None, migration: str | None, sig: set[str]) -> bool:
    at = rule.get("applies_to") or {}
    if at:
        ok = (model_repl in (at.get("replacements") or [])) or (migration and migration in (at.get("migrations") or []))
        if not ok:
            return False
    if rule.get("when_all") and not set(rule["when_all"]) <= sig:
        return False
    if rule.get("when_any") and not (set(rule["when_any"]) & sig):
        return False
    if rule.get("unless_any") and (set(rule["unless_any"]) & sig):
        return False
    return bool(rule.get("when_all") or rule.get("when_any"))


def _bump(risk: str, to: str) -> str:
    return to if RISK_RANK[to] > RISK_RANK[risk] else risk


def assess(f: Finding, pack: Pack, sig: list[str], today: dt.date) -> None:
    sigset = set(sig)
    base = pack.fine_tune_base(f.model)
    if base is not None:
        f.category = "fine_tune"
        ft = pack.data.get("fine_tune") or {}
        f.risk = ft.get("risk", "high")
        fb = pack.fine_tune_override(base)
        bm = pack.lookup(base)
        if fb:
            f.shutdown, f.confidence = fb["shutdown"], fb.get("confidence", "confirmed")
            f.migration = bm.migration if bm else None
            f.notes.append(f"Fine-tune of {base}; {pack.provider} shuts down fine-tunes of this base on {fb['shutdown']}."
                           + (f" Recommended replacement base model: {fb['replacement']}." if fb.get("replacement") else ""))
            f.notes += fb.get("notes") or ft.get("notes", [])
            return
        if bm:
            f.shutdown, f.migration = bm.shutdown, bm.migration
            f.notes.append(f"Fine-tune of {base}; it shuts down with its base model on {bm.shutdown}.")
            f.confidence = "confirmed" if bm.confidence in ("confirmed", "live-tested") else bm.confidence
        else:
            f.notes.append(f"Fine-tune of {base}; base model not in the {pack.provider} pack - check manually.")
            f.confidence = "n/a"
        f.notes += ft.get("notes", [])
        return
    m = pack.lookup(f.model)
    if m is None:
        f.category, f.risk, f.confidence = "not_listed", "info", "n/a"
        f.notes.append(f"Not listed as retiring in the {pack.provider} pack (v{pack.version}).")
        return
    headline = {x["id"] for x in pack.headline_migrations}
    f.category = "in_scope" if m.migration in headline else "other_deprecated"
    f.shutdown, f.suggested, f.confidence, f.migration = m.shutdown, m.replacement, m.confidence, m.migration
    policy = pack.data.get("risk_policy") or {}
    f.risk = policy.get("default_risk", "medium")
    # When shutdown_risk_when_any is set, the date raises risk only if the file
    # has one of those signals. Otherwise the finding stays at default_risk.
    gate = set(policy.get("shutdown_risk_when_any") or [])
    on_platform = (not gate) or bool(gate & sigset)
    if m.note and (on_platform or not policy.get("otherwise_note")):
        f.notes.append(m.note)
    if not on_platform and policy.get("otherwise_note"):
        f.notes.append(policy["otherwise_note"])
    if m.shutdown and on_platform:
        days = (dt.date.fromisoformat(m.shutdown) - today).days
        if days < 0:
            f.risk = "high"
            f.notes.append(f"Shutdown date {m.shutdown} has passed; calls are likely failing now.")
        elif days <= pack.urgent_days:
            f.risk = "high"
            f.notes.append(f"Shuts down in {days} days.")
    if f.category == "other_deprecated":
        f.notes.append(f"Outside the headline migration; the listed replacement is {m.replacement}.")
    for rule in pack.data.get("rules", []):
        if _rule_applies(rule, m.replacement, m.migration, sigset):
            f.rules.append(rule["id"])
            tag = " [live-tested]" if rule.get("confidence") == "live-tested" else (
                " [inferred]" if rule.get("confidence") == "inferred" else "")
            f.notes.append(rule["message"] + tag)
            if rule["risk"] != "info":
                f.risk = _bump(f.risk, rule["risk"])
    if not m.map_automatically and m.replacement:
        f.auto_swap = False
        f.notes.append(f"Flag-only: `fix` and `swap` do not rewrite {f.model}. It shuts down "
                       f"{m.shutdown or 'on a date not yet announced'}; switch it to {m.replacement} by hand"
                       + (" (see the note above for what the switch needs)." if m.note else "."))
    if f.kind in ("doc", "comment"):
        if RISK_RANK[f.risk] > RISK_RANK["low"]:
            f.risk = "low"
        f.notes.append("Appears in documentation/comment only.")
    elif f.kind == "name_check":
        if RISK_RANK[f.risk] > RISK_RANK["low"]:
            f.risk = "low"
        f.notes.append("Model-name check (startsWith/includes/in), not a pinned model. "
                       "Review the branch it guards; `fix` and `swap` leave it unchanged.")


def count_model_tokens(text: str, packs: PackSet, lang: str, path: Path | str = "") -> int:
    lines = text.splitlines()
    modes = line_modes(lines, path, lang)
    n = 0
    for i, line in enumerate(lines):
        if modes[i] is None:
            continue
        prev = lines[i - 1] if i else ""
        n += sum(1 for _ in iter_model_tokens(line, packs, lang, prev))
    return n


def scan(root: str | Path, include_docs: bool = True, packs: PackSet | None = None,
         today: dt.date | None = None, include_generated: bool = False) -> ScanResult:
    root = Path(root).resolve()
    packs = packs or load_packs()
    today = today or dt.date.today()
    findings: list[Finding] = []
    env_refs: list[EnvRef] = []
    fsig: dict[str, list[str]] = {}
    fsdk: dict[str, list[str]] = {}
    n = 0
    skipped: list[SkippedFile] = []
    for path, lang in iter_files(root, include_docs, include_generated=True):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(root).as_posix()
        reason = file_skip_reason(path, rel, text)
        if reason and not include_generated:
            count = count_model_tokens(text, packs, lang, path)
            if count:
                skipped.append(SkippedFile(rel, count, reason))
            continue
        n += 1
        sig, sdks = file_signals(text, lang, packs)
        if sig:
            fsig[rel] = sig
        if sdks:
            fsdk[rel] = sdks
        lines = text.splitlines()
        modes = line_modes(lines, path, lang)
        for i, line in enumerate(lines, 1):
            this_in_code = modes[i - 1]
            if this_in_code is None:
                continue
            prev = lines[i - 2] if i > 1 else ""
            for s, e, tok, pack in iter_model_tokens(line, packs, lang, prev):
                kind = _kind(line, lang, prev, this_in_code)
                if kind not in ("doc", "comment") and is_name_check(line, s, e):
                    kind = "name_check"
                f = Finding(rel, i, s + 1, tok, pack.provider, kind, lang,
                            line.strip()[:200], "not_listed", None, None, "n/a", "info")
                assess(f, pack, sig, today)
                findings.append(f)
            for m in ENV_REF_RE.finditer(line):
                env_refs.append(EnvRef(rel, i, m.group(1), line.strip()[:200]))
    return ScanResult(str(root), n, findings, env_refs, fsig, fsdk, packs.info(), today.isoformat(), skipped)


def summarise(res: ScanResult) -> dict:
    by_cat: dict[str, int] = {}
    by_risk: dict[str, int] = {}
    by_provider: dict[str, int] = {}
    for f in res.findings:
        by_cat[f.category] = by_cat.get(f.category, 0) + 1
        by_risk[f.risk] = by_risk.get(f.risk, 0) + 1
        by_provider[f.provider] = by_provider.get(f.provider, 0) + 1
    return {
        "total_findings": len(res.findings),
        "by_category": by_cat, "by_risk": by_risk, "by_provider": by_provider,
        "files_with_findings": len({f.file for f in res.findings}),
        "fine_tuned_models": sorted({f.model for f in res.findings if f.category == "fine_tune"}),
        "env_var_model_refs": sorted({e.variable for e in res.env_refs}),
        "sdks": sorted({s for v in res.file_sdks.values() for s in v}),
    }


CAT_LABEL = {"in_scope": "Headline migration", "fine_tune": "Fine-tuned model",
             "other_deprecated": "Other retiring model", "not_listed": "Not listed as retiring"}


def _esc(s: str) -> str:
    return s.replace("|", "\\|")


def to_markdown(res: ScanResult) -> str:
    s = summarise(res)
    packs = ", ".join(f"{p['provider']} v{p['version']} ({p['source']})" for p in res.packs)
    out = ["# Model scan report", "",
           f"- Repository: `{res.root}`",
           f"- Files scanned: {res.files_scanned}",
           f"- Findings: {s['total_findings']} in {s['files_with_findings']} files",
           f"- Migration packs: {packs}",
           f"- SDKs detected: {', '.join(s['sdks']) or 'none'}", "",
           "| Risk | Count |", "|---|---|"]
    out += [f"| {r} | {s['by_risk'][r]} |" for r in ("high", "medium", "low", "info") if s["by_risk"].get(r)]
    out.append("")
    for c in ["fine_tune", "in_scope", "other_deprecated", "not_listed"]:
        items = [f for f in res.findings if f.category == c]
        if not items:
            continue
        out += [f"## {CAT_LABEL[c]}", "",
                "| File | Line | Provider | Current model | Suggested | Shutdown | Risk | Kind | Notes |",
                "|---|---|---|---|---|---|---|---|---|"]
        for f in items:
            sug = f"`{f.suggested}`" if f.suggested else "manual decision"
            if f.suggested and not f.auto_swap:
                sug += " (by hand; not auto-swapped)"
            conf = " (inferred)" if f.confidence == "inferred" and f.suggested else ""
            out.append(f"| `{f.file}` | {f.line} | {f.provider} | `{f.model}` | {sug}{conf} | {f.shutdown or '-'} | "
                       f"**{f.risk}** | {f.kind} | {'<br>'.join(_esc(n) for n in f.notes)} |")
        out.append("")
    if res.env_refs:
        out += ["## Models read from environment variables", "",
                "These are set outside the repo (hosting dashboard, CI secrets, .env on servers). Check their deployed values too.", "",
                "| File | Line | Variable |", "|---|---|---|"]
        out += [f"| `{e.file}` | {e.line} | `{e.variable}` |" for e in res.env_refs]
        out.append("")
    if res.skipped:
        out += ["## Generated and vendored files", "",
                "Not counted as findings, and not toward `--fail-on-high`. "
                "Pass `--include-generated` to scan them.", ""]
        out += [f"- {s.line()}" for s in res.skipped]
        out.append("")
    return "\n".join(out)


def to_summary_markdown(res: ScanResult, max_rows: int = 25) -> str:
    """Compact markdown for CI job summaries (GitHub caps step summaries at 1 MiB)."""
    s = summarise(res)
    hi = s["by_risk"].get("high", 0)
    head = "### :red_circle:" if hi else ("### :large_orange_diamond:" if s["total_findings"] else "### :white_check_mark:")
    out = [f"{head} Model retirement scan: {s['total_findings']} reference(s), {hi} high risk", "",
           "| Risk | Count |", "|---|---|"]
    out += [f"| {r} | {s['by_risk'].get(r, 0)} |" for r in ("high", "medium", "low", "info")]
    out += ["", "| Risk | File:line | Model | Suggested | Shutdown |", "|---|---|---|---|---|"]
    rows = sorted(res.findings, key=lambda f: (-RISK_RANK[f.risk], f.file, f.line))
    for f in rows[:max_rows]:
        out.append(f"| {f.risk} | `{f.file}:{f.line}` | `{f.model}` | {('`'+f.suggested+'`') if f.suggested else '-'} | {f.shutdown or '-'} |")
    if len(rows) > max_rows:
        out.append(f"\n_{len(rows) - max_rows} more in the `scan.json` artifact._")
    packs = ", ".join(f"{p['provider']} v{p['version']}" for p in res.packs)
    out += ["", f"<sub>{brand.PRODUCT_NAME} free scan · packs: {packs} · scanned {res.scanned_on}</sub>"]
    return "\n".join(out)


def github_annotations(res: ScanResult, base: str | Path | None = None) -> list[str]:
    """GitHub workflow commands so findings show inline on PRs. Paths are made relative to
    `base` (the workspace / current directory), which is what GitHub expects."""
    base = Path(base or Path.cwd()).resolve()
    out = []
    for f in res.findings:
        try:
            path = (Path(res.root) / f.file).resolve().relative_to(base).as_posix()
        except ValueError:
            path = f.file
        if f.risk in ("high", "medium"):
            level = "error" if f.risk == "high" else "warning"
            msg = f"{f.model} -> {f.suggested or 'manual decision'} (shutdown {f.shutdown or '?'}). " + " ".join(f.notes[:2])
            msg = msg.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            out.append(f"::{level} file={path},line={f.line},title=Retiring model {f.model}::{msg[:900]}")
    return out


def write_reports(res: ScanResult, out_dir: str | Path) -> tuple[Path, Path]:
    out = Path(out_dir)
    mark_output(out)
    out.mkdir(parents=True, exist_ok=True)
    j, m = out / "scan.json", out / "scan.md"
    j.write_text(json.dumps(res.to_dict(), indent=2))
    m.write_text(to_markdown(res))
    return j, m
