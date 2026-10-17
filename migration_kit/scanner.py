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
from .packs import Pack, PackSet, colon_prefixes, load_packs

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
            ".html": "html", ".htm": "html", ".mdx": "mdx", ".mdc": "mdx", ".mk": "make",
            ".ipynb": "ipynb"}
CONFIG_EXT = {".yaml": "yaml", ".yml": "yaml", ".json": "json", ".toml": "toml", ".ini": "ini",
              ".cfg": "ini", ".conf": "ini"}
DOC_EXT = {".md": "markdown", ".txt": "text", ".rst": "text", ".rd": "text"}
# Config templates are scanned as the file they stand for: `livereview.toml.example` is TOML.
TEMPLATE_EXT = {".example", ".sample"}
MAKEFILE_NAMES = {"makefile", "gnumakefile"}
CODE_LANGS = set(CODE_EXT.values())
CONFIG_LANGS = set(CONFIG_EXT.values()) | {"env"}
DOC_LANGS = {"markdown", "text"}
# Skipped with --no-docs (and by swap/fix unless include_docs). .mdx is documentation
# even though its code fences are scanned at normal severity.
DOCS_SKIP_LANGS = DOC_LANGS | {"mdx"}
# Prose outside ``` fences is documentation; code chunks are source.
LITERATE_EXT = {".rmd", ".qmd", ".mdx", ".mdc"}
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
    kind: str            # sdk_call | env | config | string_literal | doc | comment | name_check | allow_list | prose
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
    auto_swap: bool = True   # False when fix/swap never rewrite it; no_swap_reason says why
    # flag_only | fine_tune | name_check | allow_list | must_update_together | prose | regex | object_key
    # | changelog (None when auto_swap)
    no_swap_reason: str | None = None


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


def _effective_suffix(path: Path | str) -> str:
    """`.toml` for `livereview.toml.example`; otherwise the file's own suffix."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext in TEMPLATE_EXT:
        inner = Path(p.stem).suffix.lower()
        if inner:
            return inner
    return ext


def _language(path: Path) -> str | None:
    name = path.name
    if name.startswith(".env") or name.endswith(".env"):
        return "env"
    if name.lower() in MAKEFILE_NAMES:
        return "make"
    ext = _effective_suffix(path)
    lang = CODE_EXT.get(ext) or CONFIG_EXT.get(ext) or DOC_EXT.get(ext)
    if lang is None and not ext and not name.startswith(".") and path.is_file() and not path.is_symlink():
        return _shebang_language(path)
    return lang


_SCRIPT_OPEN = re.compile(r"<script\b[^>]*>", re.I)
_SCRIPT_CLOSE = re.compile(r"</script\s*>", re.I)
_HTML_COMMENT = re.compile(r"<!--.*?-->")


MARKUP = "markup"


def line_modes(lines: list[str], path: Path | str, lang: str) -> list[bool | str | None]:
    """Per line: True = code, False = prose (documentation), MARKUP = HTML markup,
    None = not scanned.

    R Markdown / Quarto / MDX / Cursor .mdc: prose outside ``` fences is documentation
    (the fence line itself too). HTML: lines inside <script> blocks are code; markup
    lines are MARKUP, where only quoted values count (`<option value="<id>">`,
    Django/Jinja `{% if m == '<id>' %}`, a `"model": "<id>"` code sample).
    Everything else: every line is code."""
    suffix = _effective_suffix(path)
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
            out.append(True if touched else MARKUP)
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


# Rendered HTML: an .html/.htm next to its same-stem source (README.html beside README.Rmd).
RENDER_SOURCE_EXT = (".Rmd", ".rmd", ".qmd", ".md", ".Rmarkdown", ".rmarkdown", ".ipynb")
_HTML_EXT = {".html", ".htm"}
# Code-coverage reports: covr (R), coverage.py, Istanbul/nyc, lcov genhtml, JaCoCo.
_COVERAGE_NAME = re.compile(r"^(?:coverage|covr)(?:[-_.].*)?\.html?$", re.I)
_COVERAGE_DIRS = {"htmlcov", "coverage-report", "coverage_html", "lcov-report", "coverage-html"}
_COVERAGE_MARKERS = re.compile(
    r"""data-tabsetid="covr"|id="tab-covr-|<meta name="generator" content="coverage\.py|coverage\.py v\d"""
    r"""|class="coverage-summary"|Code coverage generated by istanbul|LCOV - code coverage report"""
    r"""|<title>Coverage report|tr\.covered td""", re.I)


def _peek_bytes(path: Path, n: int = 65536) -> str:
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            return fh.read(n)
    except OSError:
        return ""


def html_generated(path: Path, rel: str, text: str | None = None) -> bool:
    """A rendered page (same-stem .Rmd/.qmd/.md/.ipynb source beside it) or a coverage report."""
    if path.suffix.lower() not in _HTML_EXT:
        return False
    stem = path.with_suffix("")
    if any(stem.with_name(stem.name + ext).is_file() for ext in RENDER_SOURCE_EXT):
        return True
    parts = {d.lower() for d in Path(rel).parts[:-1]}
    if parts & _COVERAGE_DIRS:
        return True
    head = text[:65536] if text is not None else _peek_bytes(path)
    if _COVERAGE_MARKERS.search(head):
        return True
    return bool(_COVERAGE_NAME.match(path.name) and re.search(r"\b(?:covr|coverage)\b", head, re.I))


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
    if html_generated(path, rel, text):
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
    if lang in ("python", "r", "yaml", "toml", "ini", "env", "shell", "make"):
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
    if lang in DOC_LANGS or in_code is False:
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


_COLON_PREFIX_RES: dict[str, re.Pattern] = {}


def _colon_prefix_re(provider: str) -> re.Pattern:
    rx = _COLON_PREFIX_RES.get(provider)
    if rx is None:
        alts = "|".join(re.escape(p) for p in colon_prefixes(provider))
        rx = re.compile(r"""(["'`])(?:[A-Za-z0-9_.-]+/)*(?:""" + alts + r"""):$""", re.I)
        _COLON_PREFIX_RES[provider] = rx
    return rx


def router_prefixed(line: str, start: int, end: int, provider: str) -> bool:
    """`"<provider>/o1"` (closing quote matches) or `model: <provider>/o1` (end of the value).
    Also `"<provider>:o3-mini"` (provider:model form, closing quote matches)."""
    if not provider or start < 1:
        return False
    if line[start - 1] == ":":
        m = _colon_prefix_re(provider).search(line[max(0, start - 120):start])
        return bool(m) and end < len(line) and line[end] == m.group(1)
    if line[start - 1] != "/":
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
                  r"|str_contains|strpos|stripos|strstr|stristr|grepl|in_array")
_NAME_CHECK_BEFORE = re.compile(
    r"""\b(?P<fn>""" + _NAME_CHECK_FN + r""")\s*\(\s*(?:[^()"'`,]*,\s*)?(?P<arr>(?:array\s*)?[(\[])?\s*(?:(["'`])[^"'`]*\3\s*,\s*)*$""")
_IN_AFTER = re.compile(r"""\s+(?:not\s+)?in\s+[A-Za-z_$]""")


# Array membership: `['o1', 'o1-mini', 'o3-mini'].includes(model)`, `[...].indexOf(m)`,
# `new Set(['o1']).has(m)`, Python `m in ("o1", "o3-mini")`. Not `for m in ["o1", ...]`,
# which iterates over models that are then called.
_ARRAY_MEMBER_AFTER = re.compile(
    r"""\s*(?:,\s*(["'`])[^"'`]*\1\s*)*,?\s*[\])}]\s*\)?\s*\.\s*(?P<meth>includes|indexOf|has|contains|some)\s*\(""")
_IN_ARRAY_BEFORE = re.compile(r"""\b(?:not\s+)?in\s*[\[({]\s*(?:(["'])[^"']*\1\s*,\s*)*$""")
_FOR_IN_BEFORE = re.compile(r"""\bfor\b[^:]*\bin\s*[\[({]\s*(?:(["'])[^"']*\1\s*,\s*)*$""")


def is_array_membership(line: str, start: int, end: int) -> bool:
    if not _whole_quoted_token(line, start, end):
        return False
    if _ARRAY_MEMBER_AFTER.match(line, end + 1):
        return True
    before = line[max(0, start - 1 - 200):start - 1]
    return bool(_IN_ARRAY_BEFORE.search(before)) and not _FOR_IN_BEFORE.search(before)


def is_exact_membership(line: str, start: int, end: int) -> bool:
    """An exact-match allow-list: the token is one item of a literal list/set/tuple that a
    value is tested against for equality (`m in {"a", "b"}`, `["a"].includes(m)`,
    `new Set(["a"]).has(m)`, `in_array($m, ["a"])`). Not `.some(...)` (usually a prefix
    test), and not a string needle (`"a" in m`, `m.includes("a")`), which can be a substring test."""
    if not _whole_quoted_token(line, start, end):
        return False
    m = _ARRAY_MEMBER_AFTER.match(line, end + 1)
    if m:
        return m.group("meth") != "some"
    before = line[max(0, start - 1 - 200):start - 1]
    if _IN_ARRAY_BEFORE.search(before) and not _FOR_IN_BEFORE.search(before):
        lb = list_bounds(line, start, end)
        # `m in ("gpt-4")` is a string, so a substring test.
        return not (lb and line[lb[0]] == "(" and len(lb[2]) == 1 and not lb[3])
    n = _NAME_CHECK_BEFORE.search(before)
    return bool(n and n.group("fn") == "in_array" and n.group("arr"))


_PAIRS = {"[": "]", "(": ")", "{": "}"}


def list_bounds(line: str, start: int, end: int):
    """The literal list holding the quoted token at line[start:end], when the whole list sits
    on this line and holds only quoted strings: (open index, close index, item spans
    [(quote_start, quote_end_exclusive)], has_trailing_comma). None otherwise."""
    if not _whole_quoted_token(line, start, end):
        return None
    items = [(start - 1, end + 1)]
    j = start - 2
    while True:
        while j >= 0 and line[j] in " \t":
            j -= 1
        if j < 0:
            return None
        c = line[j]
        if c in _PAIRS:
            opener = j
            break
        if c != ",":
            return None
        j -= 1
        while j >= 0 and line[j] in " \t":
            j -= 1
        if j < 0 or line[j] not in "\"'`":
            return None
        q = line[j]
        k = line.rfind(q, 0, j)
        if k < 0:
            return None
        items.insert(0, (k, j + 1))
        j = k - 1
    k = end + 1
    trailing = False
    while True:
        while k < len(line) and line[k] in " \t":
            k += 1
        if k >= len(line):
            return None
        c = line[k]
        if c == _PAIRS[line[opener]]:
            closer = k
            break
        if c != "," or trailing:
            return None
        k += 1
        while k < len(line) and line[k] in " \t":
            k += 1
        if k < len(line) and line[k] == _PAIRS[line[opener]]:
            trailing = True
            continue
        if k >= len(line) or line[k] not in "\"'`":
            return None
        q = line[k]
        e2 = line.find(q, k + 1)
        if e2 < 0:
            return None
        items.append((k, e2 + 1))
        k = e2 + 1
    return opener, closer, items, trailing


def is_name_check(line: str, start: int, end: int) -> bool:
    # `startsWith("<id>.")`: a family prefix with a trailing dot is still the whole argument.
    if (end + 1 < len(line) and line[end] == "." and start >= 1 and line[end + 1] == line[start - 1]
            and line[start - 1] in "\"'`"):
        end += 1
    if not _whole_quoted_token(line, start, end):
        return False
    if _NAME_CHECK_BEFORE.search(line[max(0, start - 1 - 160):start - 1]):
        return True
    if _IN_AFTER.match(line, end + 1):
        return True
    return is_array_membership(line, start, end)


# A family prefix check with a separator: `startsWith("<id>-")`, `startswith('<id>.')`. The id
# token itself is followed by `-`/`.`/`_`, so it is not matched as a model id; it is
# reported as a name check on the id it tests for.
_PREFIX_ARG = re.compile(r"""(["'`])([A-Za-z0-9][A-Za-z0-9._:-]*?)[-_]\1""")


def iter_prefix_checks(line: str, packs: PackSet):
    """Yield (start, end, token, pack) for `startsWith("<id>-")`-style family checks."""
    if "(" not in line:
        return
    for m in _PREFIX_ARG.finditer(line):
        s, e = m.start(2), m.end(2)
        if not _NAME_CHECK_BEFORE.search(line[max(0, s - 1 - 160):s - 1]):
            continue
        for pack in packs:
            if any(rx.fullmatch(m.group(2)) for rx in pack.bare_res):
                yield s, e, m.group(2), pack
                break


# An unquoted JS/TS object key holding a table entry: `o1: { input: 15, output: 60 },`.
_OBJECT_KEY_LANGS = {"javascript", "typescript", "html", "mdx"}
_OBJECT_KEY_BEFORE = re.compile(r"""(?:^|[{,])\s*$""")
_OBJECT_KEY_AFTER = re.compile(r"""\s*\??:\s*\{""")


def is_object_key(line: str, start: int, end: int, lang: str) -> bool:
    return (lang in _OBJECT_KEY_LANGS and bool(_OBJECT_KEY_BEFORE.search(line[:start]))
            and bool(_OBJECT_KEY_AFTER.match(line, end)) and line[end:end + 2] != "::")


# A regex held in a pattern key: `"matchPattern": "(?i)^(<provider>\/)?(o1)$"`.
_REGEX_KEY_BEFORE = re.compile(r"""(?:[Pp]attern|[Rr]egexp?|REGEX|PATTERN|[Mm]atcher)["']?\s*(?:=>|[:=])\s*[rR]?["'`/]""")
_REGEX_CHARS = set("()^$|?*+[]\\")


def is_regex_pattern(line: str, start: int, end: int) -> bool:
    m = None
    for m in _REGEX_KEY_BEFORE.finditer(line[:start]):
        pass
    if m is None:
        return False
    body = line[m.end():start]
    if any(q in body for q in "\"'`"):
        return False
    left = line[start - 1] if start else ""
    right = line[end] if end < len(line) else ""
    return left in _REGEX_CHARS or right in _REGEX_CHARS


def short_id_in_context(line: str, start: int, end: int, lang: str, prev: str, provider: str = "") -> bool:
    """Bare o1/o3-style ids count only in a model context, not in minified identifiers."""
    if _non_model_id_key(line[:start]):
        return False
    if _whole_quoted_token(line, start, end):
        return True
    if is_object_key(line, start, end, lang):
        return True
    if is_regex_pattern(line, start, end):
        return True
    if router_prefixed(line, start, end, provider):
        return True
    if _SHORT_KEY_BEFORE.search(line[:start]):
        return True
    if not line[:start].strip() and _SHORT_KEY_BEFORE.search(prev.rstrip()):
        return True
    return lang in CONFIG_LANGS and _config_value(line, start, end)


_URL_RE = re.compile(r"""https?://([^/\s"'`<>)\]]+)[^\s"'`<>)\]]*""")
# URLs that can carry a model id in a real request: API hosts, local servers, templated hosts.
_API_HOST_RE = re.compile(r"""^(?:api\.|.*\.googleapis\.com|.*\.azure\.com|.*\.azure-api\.net|.*amazonaws\.com"""
                          r"""|localhost|127\.0\.0\.1|0\.0\.0\.0|.*[{$<])""", re.I)


def _non_api_url_spans(line: str) -> list[tuple[int, int]]:
    """Spans of web-page links (`https://<vendor>.com/<id>`), where an id is a page name, not a call."""
    if "://" not in line:
        return []
    return [(m.start(), m.end()) for m in _URL_RE.finditer(line) if not _API_HOST_RE.match(m.group(1))]


_MARKUP_QUOTES = ("&quot;", "&#34;", "&#39;", "&apos;")


def markup_quoted(line: str, start: int, end: int) -> bool:
    """In HTML markup only a quoted value counts: an attribute value, a quoted string in a
    template tag, or a quoted id in a code sample (`"gpt-4"` or `&quot;gpt-4&quot;`)."""
    if _whole_quoted_token(line, start, end):
        return True
    for q in _MARKUP_QUOTES:
        if line[max(0, start - len(q)):start] == q and line[end:end + len(q)] == q:
            return True
    return False


def markup_text(line: str, start: int, end: int) -> bool:
    """Visible text between tags on this line (`<div>Models: <id>, <id></div>`), not inside a tag
    or template logic."""
    before, after = line[:start], line[end:]
    gt = before.rfind(">")
    if gt < 0 or before.rfind("<") > gt:
        return False
    if "{%" in before[gt:] or "{{" in before[gt:]:
        return False
    lt = after.find("<")
    return lt >= 0 and ">" not in after[:lt]


def markup_value(line: str, start: int) -> bool:
    """An attribute value (`value="<id>"`) or a string inside `{% %}` / `{{ }}` (template logic)."""
    before = line[:start]
    if re.search(r"""[\w:.@-]+\s*=\s*["']$""", before):
        return True
    o = max(before.rfind("{%"), before.rfind("{{"))
    return o >= 0 and max(before.rfind("%}"), before.rfind("}}")) < o


def iter_model_tokens(line: str, packs: PackSet, lang: str = "", prev: str = "", mode=True):
    """Yield (start, end, token, pack) for every model-id token on a line, longest match first per span.

    Ids inside a web-page link are skipped. With mode=MARKUP (HTML outside <script>),
    only quoted values count and `<!-- -->` comments are ignored."""
    seen: list[tuple[int, int]] = []
    hits = []
    text_hits = []
    if mode == MARKUP:
        line = _HTML_COMMENT.sub(lambda m: " " * len(m.group(0)), line)
    urls = _non_api_url_spans(line)
    for pack in packs:
        for rx, quoted_only in pack.id_res:
            for m in rx.finditer(line):
                if quoted_only and not short_id_in_context(line, m.start(1), m.end(1), lang, prev, pack.provider):
                    continue
                if mode == MARKUP and not markup_quoted(line, m.start(1), m.end(1)):
                    if markup_text(line, m.start(1), m.end(1)):
                        text_hits.append((m.start(1), m.end(1), m.group(1), pack))
                    continue
                if urls and any(us <= m.start(1) and m.end(1) <= ue for us, ue in urls):
                    continue
                hits.append((m.start(1), m.end(1), m.group(1), pack))
    if text_hits:
        # Visible text counts only as a list of models (`Models: <id>, <id>`): two or more
        # ids in one text node. A single label (`<option ...>GPT 4.1</option>`) is skipped.
        nodes: dict[int, list] = {}
        for h in text_hits:
            nodes.setdefault(line.rfind(">", 0, h[0]), []).append(h)
        hits += [h for group in nodes.values() if len({x[2] for x in group}) >= 2 for h in group]
    for s, e, tok, pack in sorted(hits, key=lambda h: (h[0], -(h[1] - h[0]))):
        if any(s < pe and e > ps for ps, pe in seen):
            continue
        seen.append((s, e))
        yield s, e, tok, pack


# ------------------------------------------------------------------ swap safety
# An id in running text (an LLM prompt, a heredoc, a help or log message) is an example,
# not the model the code calls; renaming it can corrupt a prompt. "Prose" means: not a
# whole quoted string, not right after `=` / `=>` / a model key / a CLI flag, bordered
# like a word, and at least PROSE_MIN_WORDS plain words elsewhere on the line (a trailing
# `#` or `//` comment doesn't count, so `model: <id>  # long comment` stays code).
PROSE_MIN_WORDS = 8
# A plain word in running text: space-separated, so quoted list items (`["summarize", ...]`)
# and identifiers don't count.
_PROSE_WORD = re.compile(r"""(?:(?<=\s)|(?<=\()|^)[A-Za-z][a-z]+(?=[\s,.;:!?)]|$)""")
_ASSIGN_BEFORE = re.compile(r"""(?:=>|->|[=])\s*["'`]?\s*(?:[A-Za-z0-9_.-]+[/:])*$""")
_MODEL_KEY_BEFORE = re.compile(
    r"""(?:\bmodel(?:_name|_id|Name|Id|s)?\b|\bdeployment\b|\bengine\b)\s*["']?\s*(?:=>|[:=])?\s*["'`]?\s*(?:[A-Za-z0-9_.-]+[/:])*$""", re.I)
_FLAG_BEFORE = re.compile(r"""(?:^|\s)-{1,2}[A-Za-z][\w-]*(?:\s+|=)["']?(?:[A-Za-z0-9_.-]+[/:])*$""")
_QUOTED_PATH_BEFORE = re.compile(r"""(["'`])(?:[A-Za-z0-9_.@-]+[/:])+$""")
_TRAILING_COMMENT = re.compile(r"""\s(?:#|//)\s.*$""")


def is_prose(line: str, start: int, end: int) -> bool:
    # Escaped quotes (`\"model\":\"<id>\"` in a recorded request) count as quotes.
    line = line.replace('\\"', '""').replace("\\'", "''")
    if _whole_quoted_token(line, start, end):
        return False
    left, right = line[:start], line[end:]
    if _ASSIGN_BEFORE.search(left) or _MODEL_KEY_BEFORE.search(left) or _FLAG_BEFORE.search(left):
        return False
    q = _QUOTED_PATH_BEFORE.search(left)
    if q and right[:1] == q.group(1):          # "<router>/<provider>/<id>": a whole id string
        return False
    lc = left[-1:] or " "
    rc = right[:1] or " "
    if not (lc.isspace() or lc in "(/:,\"'`*_") or not (rc.isspace() or rc in ",.;:)!?\"'`*_\\"):
        return False
    right = _TRAILING_COMMENT.sub("", right)
    return len(_PROSE_WORD.findall(left)) + len(_PROSE_WORD.findall(right)) >= PROSE_MIN_WORDS


# Historical changelogs and release notes: what a past release did, not code to migrate.
_CHANGELOG_NAME = re.compile(
    r"^(?:change[-_ ]?log|changes|history|news|release[-_ ]?notes?|releases?|whats[-_]?new)(?:[-_.][\w.-]*)?$", re.I)
_CHANGELOG_DIRS = {"release-notes", "release_notes", "releasenotes", "releases", "changelog", "changelogs", "changes"}
_VERSION_DOC = re.compile(r"^v?\d+(?:\.\d+)+(?:-?(?:alpha|beta|rc|pre|dev)[\w.]*)?$", re.I)
_DOC_LIKE_EXT = {"", ".md", ".mdx", ".markdown", ".rst", ".txt", ".adoc"}


def is_changelog(rel: str) -> bool:
    parts = Path(rel).parts
    if not parts:
        return False
    p = Path(parts[-1])
    if p.suffix.lower() not in _DOC_LIKE_EXT:
        return False
    if _CHANGELOG_NAME.match(p.name) or _CHANGELOG_NAME.match(p.stem):
        return True
    dirs = {d.lower() for d in parts[:-1]}
    return bool(dirs & _CHANGELOG_DIRS) or bool(_VERSION_DOC.match(p.stem) and dirs & {"docs", "doc", "news"})


def classify(line: str, start: int, end: int, lang: str, prev: str, mode, rel: str = "") -> tuple[str, str | None]:
    """The finding kind for this token, and why `swap` / `fix` must not rewrite it (None = they may).

    Reasons: name_check (a family check, renaming changes logic), prose (an example in
    running text), regex (inside a pattern string), object_key (an unquoted `o1: {` key;
    the replacement needs quotes), changelog (historical release notes)."""
    if mode == MARKUP:
        if markup_value(line, start):
            kind = "sdk_call" if MODEL_KEY_RE.search(line[:start]) else "string_literal"
        else:
            kind = "doc"                       # a quoted id in a code sample or text
    else:
        kind = _kind(line, lang, prev, mode)
    block = None
    if kind not in ("doc", "comment"):
        if is_exact_membership(line, start, end):
            kind, block = "allow_list", "allow_list"
        elif is_name_check(line, start, end):
            kind, block = "name_check", "name_check"
        elif lang in SHELL_LANGS and is_echo_message(line, start, end):
            kind, block = "prose", "prose"
        elif is_regex_pattern(line, start, end):
            block = "regex"
        elif is_object_key(line, start, end, lang):
            block = "object_key"
        elif is_prose(line, start, end):
            kind, block = "prose", "prose"
    if rel and is_changelog(rel):
        block = block or "changelog"
    return kind, block


BLOCK_NOTES = {
    "prose": ("Appears in running text (a prompt, heredoc, help or log message), not as a model argument; "
              "`fix` and `swap` leave it unchanged. Check whether the text should still name it."),
    "regex": ("Inside a regex pattern; `fix` and `swap` leave it unchanged. "
              "Update the pattern by hand together with the model name it matches."),
    "object_key": ("Unquoted object key; `fix` and `swap` leave it unchanged because the replacement id "
                   "needs quotes. Rename the key by hand (and its lookups)."),
    "changelog": "Historical changelog or release notes; `fix` and `swap` leave it unchanged.",
}
BLOCK_RISK_CAP = {"prose": "low", "regex": "low", "changelog": "info", "name_check": "low", "allow_list": "low"}


def apply_block(f: "Finding", block: str | None) -> None:
    if not block:
        return
    f.auto_swap = False
    if f.no_swap_reason in (None, "flag_only"):
        f.no_swap_reason = block
    cap = BLOCK_RISK_CAP.get(block)
    if cap and RISK_RANK[f.risk] > RISK_RANK[cap]:
        f.risk = cap
    if block in BLOCK_NOTES:
        f.notes.append(BLOCK_NOTES[block])


# `echo "Running benchmark (<id>)..."` / `@echo` / `printf`: a message, not a value.
# Not when the output is redirected or piped (`echo <id> > model.txt`, `| tee`) or captured
# (`$(echo <id>)`), where the text is data.
_CMD_SEP = re.compile(r"""(?:;|&&|\|\||\||\$\(|`|\bthen\b|\bdo\b|\belse\b)""")
_ECHO_START = re.compile(r"""^\s*[@+-]*\s*(?:echo|printf)\b""")
_REDIRECT = re.compile(r"""(?<![0-9&>])>(?!&)|(?<!\|)\|(?!\|)""")


def is_echo_message(line: str, start: int, end: int) -> bool:
    before = line[:start]
    seps = list(_CMD_SEP.finditer(before))
    if seps:
        last = seps[-1]
        if last.group(0) in ("$(", "`"):
            return False
        seg = before[last.end():]
    else:
        seg = before
    if not _ECHO_START.match(seg):
        return False
    rest = re.split(r";|&&|\|\||\)", line[end:], maxsplit=1)[0]
    return not _REDIRECT.search(rest)


# In shell scripts and Makefiles a provider-prefixed word with no digit is a command,
# package or file name (`<vendor>-hooks`, `<vendor>-mem`, `<vendor>-cli`), not a model id.
SHELL_LANGS = {"shell", "make"}


def shell_noise(tok: str, lang: str, pack: Pack) -> bool:
    return (lang in SHELL_LANGS and not any(c.isdigit() for c in tok)
            and pack.lookup(tok) is None and pack.fine_tune_base(tok) is None)


def full_stop_noise(line: str, end: int, tok: str, pack: Pack) -> bool:
    """`adopted from <vendor>-mem.`: a digit-less unlisted word before a full stop is a name
    (a package, a tool), not a model id. Same rule as shell noise, in every language."""
    return (line[end:end + 1] == "." and not any(c.isdigit() for c in tok)
            and pack.lookup(tok) is None and pack.fine_tune_base(tok) is None)


# ------------------------------------------------------------------ rows
@dataclass
class Row:
    index: int            # 0-based raw line index in the file
    text: str             # text scanned (the decoded source line for a notebook)
    mode: object          # True code | False prose | MARKUP | None (not scanned)
    lang: str
    prev: str
    note: str = ""


_NB_SOURCE = re.compile(r"""^\s*"source"\s*:\s*\[\s*$""")


def _notebook_lang(nb: dict) -> str:
    md = nb.get("metadata") or {}
    name = str((md.get("kernelspec") or {}).get("language") or (md.get("language_info") or {}).get("name") or "python").lower()
    return {"python": "python", "python3": "python", "r": "r", "javascript": "javascript",
            "typescript": "typescript", "bash": "shell"}.get(name, "python")


def notebook_rows(text: str) -> tuple[list[Row], str] | None:
    """Rows for a Jupyter notebook: each source line of each cell, at its raw JSON line number.

    Code cells use the kernel language; markdown cells are documentation; outputs are not
    scanned. Assumes nbformat's usual layout (one source line per JSON line); a cell that
    isn't laid out that way is skipped."""
    try:
        nb = json.loads(text)
    except ValueError:
        return None
    cells = nb.get("cells") if isinstance(nb, dict) else None
    if not isinstance(cells, list):
        return None
    lang = _notebook_lang(nb)
    raw = text.splitlines()
    rows: list[Row] = []
    ptr = 0
    for ci, cell in enumerate(cells, 1):
        src = cell.get("source") if isinstance(cell, dict) else None
        if not isinstance(src, list) or not src:
            continue
        j = next((k for k in range(ptr, len(raw)) if _NB_SOURCE.match(raw[k])), None)
        if j is None:
            break
        ptr = j + 1
        ok = j + len(src) < len(raw)
        decoded = []
        for k, piece in enumerate(src):
            if not ok:
                break
            r = raw[j + 1 + k].strip()
            try:
                ok = json.loads(r[:-1] if r.endswith(",") else r) == piece
            except ValueError:
                ok = False
            decoded.append(str(piece).rstrip("\r\n"))
        if not ok:
            continue
        ptr = j + 1 + len(src)
        ctype = cell.get("cell_type")
        mode = True if ctype == "code" else (False if ctype == "markdown" else None)
        for k, d in enumerate(decoded):
            rows.append(Row(j + 1 + k, d, mode, lang if mode else "markdown",
                            decoded[k - 1] if k else "", f"Notebook cell {ci}, line {k + 1}."))
    return rows, lang


def iter_rows(text: str, path: Path | str, lang: str) -> tuple[list[Row], str]:
    """The lines to scan and the language for file signals."""
    if lang == "ipynb":
        nb = notebook_rows(text)
        if nb is not None:
            return nb
        return [], "json"
    lines = text.splitlines()
    modes = line_modes(lines, path, lang)
    return [Row(i, line, modes[i], lang, lines[i - 1] if i else "") for i, line in enumerate(lines)], lang


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
        f.auto_swap, f.no_swap_reason = False, "fine_tune"   # a fine-tune can't be renamed to another model
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
        f.auto_swap, f.no_swap_reason = False, "flag_only"
        f.notes.append(f"Flag-only: `fix` and `swap` do not rewrite {f.model}. It shuts down "
                       f"{m.shutdown or 'on a date not yet announced'}; switch it to {m.replacement} by hand"
                       + (" (see the note above for what the switch needs)." if m.note else "."))
    if f.kind in ("doc", "comment"):
        if RISK_RANK[f.risk] > RISK_RANK["low"]:
            f.risk = "low"
        f.notes.append("Appears in documentation/comment only.")
    elif f.kind == "allow_list":
        if RISK_RANK[f.risk] > RISK_RANK["low"]:
            f.risk = "low"
        f.auto_swap, f.no_swap_reason = False, "allow_list"
    elif f.kind == "name_check":
        if RISK_RANK[f.risk] > RISK_RANK["low"]:
            f.risk = "low"
        f.auto_swap, f.no_swap_reason = False, "name_check"
        f.notes.append("Model-name check (startsWith/includes/in or a list membership test), not a pinned model. "
                       "Review the branch it guards; `fix` and `swap` leave it unchanged.")


def count_model_tokens(text: str, packs: PackSet, lang: str, path: Path | str = "") -> int:
    rows, _ = iter_rows(text, path, lang)
    n = 0
    for r in rows:
        if r.mode is None:
            continue
        n += sum(1 for _ in iter_model_tokens(r.text, packs, r.lang, r.prev, r.mode))
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
        rows, sig_lang = iter_rows(text, path, lang)
        sig_text = text if sig_lang == lang else "\n".join(r.text for r in rows if r.mode is True)
        sig, sdks = file_signals(sig_text, sig_lang, packs)
        if sig:
            fsig[rel] = sig
        if sdks:
            fsdk[rel] = sdks
        for r in rows:
            if r.mode is None:
                continue
            line, i = r.text, r.index + 1
            for s, e, tok, pack in iter_model_tokens(line, packs, r.lang, r.prev, r.mode):
                if shell_noise(tok, r.lang, pack) or full_stop_noise(line, e, tok, pack):
                    continue
                kind, block = classify(line, s, e, r.lang, r.prev, r.mode, rel)
                f = Finding(rel, i, s + 1, tok, pack.provider, kind, r.lang,
                            line.strip()[:200], "not_listed", None, None, "n/a", "info")
                assess(f, pack, sig, today)
                apply_block(f, block)
                if r.mode == MARKUP and kind == "doc" and not markup_quoted(line, s, e):
                    f.risk = "info"
                    f.notes.append("Visible page text (not a value the page sends); "
                                   "`swap` leaves it unless docs are included.")
                if r.note:
                    f.notes.append(r.note)
                findings.append(f)
            if r.mode is True and r.lang not in DOC_LANGS and not _is_comment(line, r.lang):
                for s, e, tok, pack in iter_prefix_checks(line, packs):
                    f = Finding(rel, i, s + 1, tok, pack.provider, "name_check", r.lang,
                                line.strip()[:200], "not_listed", None, None, "n/a", "info")
                    assess(f, pack, sig, today)
                    apply_block(f, "name_check")
                    f.notes.append(f"Prefix check for the {tok} family (`{line[s:e + 1]}`).")
                    if r.note:
                        f.notes.append(r.note)
                    findings.append(f)
            for m in ENV_REF_RE.finditer(line):
                env_refs.append(EnvRef(rel, i, m.group(1), line.strip()[:200]))
    link_checks(findings, {k for p in packs for k in p.default_mapping()})
    return ScanResult(str(root), n, findings, env_refs, fsig, fsdk, packs.info(), today.isoformat(), skipped)


ALLOW_LIST_SWAP_NOTE = ("Exact-match allow-list. `swap` adds the replacement id to this list (the old ids stay), "
                        "because the default mapping renames {model} elsewhere in this repo and the swapped values "
                        "must still pass this check.")
ALLOW_LIST_KEEP_NOTE = ("Exact-match allow-list. The default `swap` mapping doesn't rename {model} anywhere else "
                        "in this repo, so the list is left unchanged.")
MUST_UPDATE_NOTE = ("Must update together: the default `swap` mapping renames {related} elsewhere in this repo, but this check is "
                    "left unchanged (renaming a prefix or substring test changes its logic). After the swap it "
                    "no longer matches the new id; update it by hand in the same change.")


def link_checks(findings: list[Finding], mapped: set[str]) -> None:
    """Repo-level pass, matching what `swap` does with the default mapping (`mapped`): an
    allow-list is swapped together with the values it checks; a name check on an id that is
    renamed elsewhere is `must_update_together`."""
    swapped = {f.model for f in findings
               if f.auto_swap and f.model in mapped and f.language not in DOCS_SKIP_LANGS
               and f.kind not in ("allow_list", "name_check", "doc", "comment")}
    if not swapped:
        for f in findings:
            if f.kind == "allow_list":
                f.notes.append(ALLOW_LIST_KEEP_NOTE.format(model=f.model))
        return
    for f in findings:
        if f.kind == "allow_list":
            if f.model in swapped and f.no_swap_reason == "allow_list":
                f.auto_swap, f.no_swap_reason = True, None
                f.notes.append(ALLOW_LIST_SWAP_NOTE.format(model=f.model))
            else:
                f.notes.append(ALLOW_LIST_KEEP_NOTE.format(model=f.model))
        elif f.kind == "name_check" and f.no_swap_reason == "name_check":
            related = sorted(r for r in swapped if f.model in r)
            if related:
                f.no_swap_reason = "must_update_together"
                shown = ", ".join(related[:5]) + (f" and {len(related) - 5} more" if len(related) > 5 else "")
                f.notes.append(MUST_UPDATE_NOTE.format(related=shown))


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
