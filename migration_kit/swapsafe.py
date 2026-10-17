# Copyright (c) 2026 Burnt and Toast Studios Ltd. Proprietary; see LICENSE-COMMERCIAL.
"""Swap safety: where a model-id rename is unsafe even though the id itself is swappable.

Used by `swap` (and so by `fix`) to skip renames, and by `scan` so that a finding's
`auto_swap` says what `swap` really does.

- File level: schema/settings migrations (historical data) and price / model catalogues.
- Token level: Azure deployment names, tokeniser arguments, comments, docstrings,
  help / description text, recorded fixture payloads in tests, exact `==` checks.
- Structure: a light bracket/quote-aware parser for JS/TS, Python and JSON (plus an
  indentation pass for YAML) that finds object keys and list items, so a rename that
  would create a duplicate key or a duplicate id in a list is skipped, not written.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

# ------------------------------------------------------------------ file level
_MIGRATION_DIRS = {"migrations", "migration"}
_CATALOG_NAME = re.compile(r"(?:^|[-_.])(?:prices?|pricing|model[-_]?catalog(?:ue)?)(?:[-_.]|$)", re.I)


def is_migration_path(rel: str) -> bool:
    """Any path segment (directory) named migrations / migration: a historical schema step."""
    return bool({p.lower() for p in PurePosixPath(rel).parts[:-1]} & _MIGRATION_DIRS)


def is_catalog_file(rel: str, text: str = "") -> bool:
    """A price list or model catalogue (a description of models, not code that calls one):
    `*price*`, `*pricing*`, `*model-catalog*` / `*model_catalog*` data files, or any JSON / YAML
    file whose entries carry both `modelName` and `matchPattern`."""
    p = PurePosixPath(rel)
    suffix = p.suffix.lower()
    if suffix not in (".json", ".yaml", ".yml", ".toml", ".csv", ".ts", ".js", ".mjs", ".py"):
        return False
    if _CATALOG_NAME.search(p.stem) and (suffix in (".json", ".yaml", ".yml", ".toml", ".csv")
                                         or "catalog" in p.stem.lower()):
        return True
    if suffix in (".json", ".yaml", ".yml") and text:
        return bool(re.search(r"""["']?modelName["']?\s*:""", text) and re.search(r"""["']?matchPattern["']?\s*:""", text))
    return False


def file_hold(rel: str, text: str = "") -> str | None:
    if is_migration_path(rel):
        return "migration"
    if is_catalog_file(rel, text):
        return "catalog"
    return None


FILE_HOLD_NOTES = {
    "migration": ("In a schema/settings migration (a `migrations/` folder). Migrations describe data written by "
                  "past versions, so `swap` never rewrites them; add a new migration step instead if saved "
                  "settings should move to the new id."),
    "catalog": ("In a price list or model catalogue. It describes models (and their prices and match patterns), "
                "so `swap` leaves it unchanged; add an entry for the new model by hand if needed."),
}

# ------------------------------------------------------------------ token level
_DEPLOY_KEY = re.compile(
    r"""(?:\b(?:azure_?)?deployment(?:_?(?:name|id))?|\bdeployment(?:Name|Id)|\bazureDeployment(?:Name)?|\bAZURE_[A-Z0-9_]*DEPLOYMENT[A-Z0-9_]*"""
    r"""|\bengine)["']?\s*(?:=>|:=|[:=])\s*(?:[A-Za-z_][\w.]*\s*\(\s*["'][^"']*["']\s*,\s*)?[rRuUfFbB]{0,2}["'`]?\s*$""", re.I)
_TOKENISER_CALL = re.compile(
    r"""\b(?:encoding_for_model|encodingForModel|getEncodingForModel|get_encoding_for_model|tokenizer_for_model"""
    r"""|tokenizerForModel)\s*\(\s*["'`]?\s*$""")
_TOKENISER_KEY = re.compile(r"""\b(?:tokenizerModel|tokenizer_model|tokeniserModel|tokeniser_model|tiktoken_model"""
                            r"""|tokenizer_name|tokenizerName)["']?\s*(?:=>|[:=])\s*["'`]?\s*$""")
_TOKENISER_USE = r"""\b(?:encoding_for_model|encodingForModel|getEncodingForModel|get_encoding_for_model)\s*\(\s*{var}\b"""
_ASSIGN_VAR = re.compile(r"""^\s*(?:(?:const|let|var)\s+)?([A-Za-z_$][\w$]*)\s*(?::[^=]*)?=(?!=)""")
_PARAM_DEFAULT = re.compile(r"""([A-Za-z_$][\w$]*)\s*(?::\s*[\w\[\]|. ]+)?\s*=\s*[rRuUfFbB]{0,2}["'`]$""")
_HELP_KEY = re.compile(r"""(?:\b(?:help|description|desc|usage|epilog|docstring|summary)|\bhelpText|\bhelp_text)["']?\s*(?:=>|[:=])\s*\(?\s*[rRuUfFbB]{0,2}$""")
_HELP_KEY_LINE = re.compile(r"""(?:\b(?:help|description|desc|usage|epilog|summary)|\bhelpText|\bhelp_text)["']?\s*(?:=>|[:=])\s*\(?\s*$""")
_YAML_HELP = re.compile(r"""^\s*(?:-\s+)?(?:help|description|summary|usage)\s*:\s""")
_TEST_PATH = re.compile(r"""(?:^|/)(?:tests?|__tests__|spec|specs)/|(?:^|/)test_[^/]*\.py$|_test\.py$|\.(?:test|spec)\.[cm]?[jt]sx?$""")
_RECORDING_PATH = re.compile(r"""(?:^|/)(?:cassettes|__snapshots__|recordings|vcr_cassettes)/|\.snap$""")
_COMMENT_LANGS_HASH = {"python", "r", "yaml", "toml", "ini", "env", "shell", "make"}
_COMMENT_LANGS_SLASH = {"javascript", "typescript", "go", "rust", "csharp", "php", "mdx"}

HOLD_NOTES = {
    "deployment_name": ("Azure deployment name (chosen by whoever created the deployment), not a model id; `swap` "
                        "leaves it. Create or pick a deployment of the new model and set its name by hand."),
    "tokeniser": ("Passed to a tokeniser lookup (tiktoken `encoding_for_model`, `tokenizerModel`, ...); `swap` leaves "
                  "it because a new model may not be in the tokeniser library yet. Switch it by hand with a fallback "
                  "(for example o200k_base)."),
    "comment": "In a comment; `swap` leaves comments unchanged.",
    "docstring": "In a docstring; `swap` leaves documentation text unchanged.",
    "help_text": "In help or description text; `swap` leaves it unchanged.",
    "fixture": ("In a recorded response/fixture payload in a test; `swap` leaves recordings unchanged. Re-record it "
                "or update it by hand together with the assertions that use it."),
}
MANUAL_HOLDS = {"deployment_name", "tokeniser"}


def is_test_path(rel: str) -> bool:
    return bool(_TEST_PATH.search(rel))


def string_spans(line: str, lang: str) -> tuple[list[tuple[int, int]], int | None]:
    """Quoted string spans [(open quote, index after close quote)] on one line, and where a
    trailing comment starts (None if there is none). Unterminated strings run to the end."""
    spans: list[tuple[int, int]] = []
    hashc = lang in _COMMENT_LANGS_HASH
    slash = lang in _COMMENT_LANGS_SLASH or lang == "html"
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if c in "\"'`":
            if lang == "python" and line.startswith(c * 3, i):
                j = line.find(c * 3, i + 3)
                end = n if j < 0 else j + 3
            else:
                j = i + 1
                while j < n and line[j] != c:
                    j += 2 if line[j] == "\\" else 1
                end = min(n, j + 1)
            spans.append((i, end))
            i = end
            continue
        if hashc and c == "#" and not (lang == "shell" and i and not line[i - 1].isspace()):
            return spans, i
        if slash and line.startswith("//", i) and not (i and line[i - 1] == ":"):
            return spans, i
        if lang == "php" and c == "#" and not line.startswith("#[", i):
            return spans, i
        i += 1
    return spans, None


def enclosing_string(line: str, s: int, lang: str) -> tuple[int, int] | None:
    spans, _ = string_spans(line, lang)
    for a, b in spans:
        if a < s < b:
            return a, b
    return None


def block_rows(lines: list[str], lang: str) -> dict[int, str]:
    """Rows inside multi-line comments (`/* ... */`) or Python docstrings: row -> 'comment' | 'docstring'."""
    out: dict[int, str] = {}
    if lang in ("javascript", "typescript", "go", "rust", "csharp", "php"):
        inside = False
        for i, raw in enumerate(lines):
            if inside:
                out[i] = "comment"
                if "*/" in raw:
                    inside = False
                continue
            spans, cmt = string_spans(raw, lang)
            k = raw.find("/*")
            while k >= 0 and any(a < k < b for a, b in spans):
                k = raw.find("/*", k + 1)
            if k >= 0 and (cmt is None or k < cmt) and "*/" not in raw[k + 2:]:
                if not raw[:k].strip():
                    out[i] = "comment"
                inside = True
    elif lang == "python":
        state = None             # (delimiter, label) while inside a triple-quoted string
        for i, raw in enumerate(lines):
            k, n = 0, len(raw)
            if state:
                out[i] = state[1]
                j = raw.find(state[0])
                if j < 0:
                    continue
                if raw[j + 3:].strip(" \t,);:"):
                    out.pop(i, None)             # code follows the closing quotes on this row
                k, state = j + 3, None
            while k < n:
                c = raw[k]
                if c == "#":
                    break
                if c in "\"'":
                    if raw.startswith(c * 3, k):
                        head = raw[:k].rstrip()
                        head = re.sub(r"[rRuUfFbB]{1,2}$", "", head)
                        if not head.strip():
                            label = "docstring"          # a bare string statement
                        elif _HELP_KEY_LINE.search(head + " ") or re.search(
                                r"(?:\b(?:help|description|usage|epilog|summary))\s*=\s*\(?$", head):
                            label = "help_text"
                        else:
                            label = None                 # a prompt or other value: normal rules
                        j = raw.find(c * 3, k + 3)
                        if j < 0:
                            if label:
                                out[i] = label
                            state = (c * 3, label)
                            break
                        if label and not raw[j + 3:].strip(" ,)"):
                            out[i] = label
                        k = j + 3
                        continue
                    j = k + 1
                    while j < n and raw[j] != c:
                        j += 2 if raw[j] == "\\" else 1
                    k = j + 1
                    continue
                k += 1
            if state and state[1] is None:
                state = (state[0], None)
        out = {k: v for k, v in out.items() if v}
    return out


def token_hold(line: str, s: int, e: int, lang: str, rel: str, prev: str, kind: str,
               block_row: str | None = None, after: list[str] | None = None) -> str | None:
    """Why this id must not be renamed even though it is swappable (None = rename it).

    `after` is the next few source lines (for a variable that flows into a tokeniser)."""
    if block_row:
        return block_row
    if kind == "comment":
        return "comment"
    spans, cmt = string_spans(line, lang)
    if cmt is not None and s >= cmt:
        return "comment"
    before = line[:s]
    if _DEPLOY_KEY.search(before):
        return "deployment_name"
    if _TOKENISER_CALL.search(before) or _TOKENISER_KEY.search(before):
        return "tokeniser"
    if after:
        var = None
        m = _PARAM_DEFAULT.search(before)
        if m:
            var = m.group(1)
        else:
            m = _ASSIGN_VAR.match(line)
            if m and m.end() <= s:
                var = m.group(1)
        if var and re.search(_TOKENISER_USE.format(var=re.escape(var)), "\n".join([line[e:]] + after)):
            return "tokeniser"
    enc = next(((a, b) for a, b in spans if a < s < b), None)
    if lang == "yaml" and _YAML_HELP.match(line):
        return "help_text"
    if enc:
        head = line[:enc[0]]
        if _HELP_KEY.search(head) or (not head.strip() and _HELP_KEY_LINE.search(prev.rstrip())):
            # `help="... gpt-4o ..."`: a whole-id string under a description key is still text
            return "help_text"
        if is_test_path(rel) and not (enc[0] == s - 1 and enc[1] == e + 1):
            body = line[enc[0]:enc[1]]
            if re.search(r"""\{\s*\\?["']""", body) and re.search(r"""\\?["']\s*:""", body) and len(body) > 60:
                return "fixture"
    if _RECORDING_PATH.search(rel):
        return "fixture"
    return None


# ------------------------------------------------------------------ equality checks
_EQ_BEFORE = re.compile(r"""(?P<lhs>[A-Za-z_$][\w$]*(?:\s*(?:\?\.|\.)\s*[A-Za-z_$][\w$]*|\[[^\[\]]*\]|\(\))*)\s*(?P<op>===|!==|==|!=)\s*$""")
_EQ_AFTER = re.compile(r"""^\s*(?P<op>===|!==|==|!=)""")
_CASE_BEFORE = re.compile(r"""\bcase\s+$""")
_OK_LEFT = re.compile(r"""(?:^|[([{,;?:]|&&|\|\||(?<![=!<>])=|=>|\b(?:return|if|elif|while|and|or|not|assert|when)\s*)\s*$""")
_OK_RIGHT = re.compile(r"""^\s*(?:$|[)\]},;?:]|&&|\|\||\b(?:and|or|if|else|then)\b|//|#)""")


def equality_check(line: str, s: int, e: int) -> str | None:
    """'lhs' when the quoted id is the right operand of `x == 'id'`-style comparisons,
    'other' for `'id' === x` / `case 'id':`, None when it isn't an equality test."""
    if s < 1 or e >= len(line) or line[s - 1] != line[e] or line[e] not in "\"'`":
        return None
    q0, q1 = s - 1, e + 1
    if _EQ_BEFORE.search(line[:q0]):
        return "lhs"
    if _EQ_AFTER.match(line[q1:]) or (_CASE_BEFORE.search(line[:q0]) and line[q1:].lstrip().startswith(":")):
        return "other"
    if re.search(r"""(?:===|!==|==|!=)\s*$""", line[:q0]):
        return "other"
    return None


def extend_equality(line: str, s: int, e: int, new: str, lang: str) -> tuple[int, int, str] | None:
    """`x === 'old'` -> `(x === 'old' || x === 'new')` (`!==`: `&&`; Python: `or` / `and`).
    None when the comparison can't be extended safely on this line."""
    q0, q1 = s - 1, e + 1
    m = _EQ_BEFORE.search(line[:q0])
    if not m:
        return None
    a = m.start("lhs")
    if not _OK_LEFT.search(line[:a]) or not _OK_RIGHT.match(line[q1:]):
        return None
    lhs, op, q = m.group("lhs"), m.group("op"), line[q0]
    if "(" in lhs and not lhs.endswith("()"):
        return None
    neg = op in ("!==", "!=")
    if lang == "python":
        join = " and " if neg else " or "
    elif lang in ("javascript", "typescript", "php", "go", "rust", "csharp", "html", "mdx", "ejs"):
        join = " && " if neg else " || "
    else:
        return None
    old_cmp = line[a:q1]
    return a, q1, f"({old_cmp}{join}{lhs} {op} {q}{new}{q})"


# ------------------------------------------------------------------ structure (keys, list items)
ID_FIELDS = {"id", "_id", "name", "model_id", "modelId", "modelName", "model_name", "value", "key", "slug"}
STRUCT_LANGS = {"javascript", "typescript", "python", "json", "ipynb"}


@dataclass
class Lit:
    row: int
    qs: int          # opening quote column
    qe: int          # column after the closing quote
    text: str        # content between the quotes
    cont: "Cont | None"
    entry: int
    role: str = "other"     # key | value | item | other
    key: str | None = None  # for role == value: the key it is the value of


@dataclass
class Cont:
    kind: str                # { [ (
    row: int
    col: int
    parent: "Cont | None"
    entry: int               # entry index in the parent
    call: bool = False       # `(` of a call (or definition), not a tuple
    end: tuple[int, int] | None = None
    keys: list = field(default_factory=list)      # (entry, key text, Lit | None)
    entries: dict = field(default_factory=dict)   # entry -> {"toks": n, "lits": [Lit], "conts": [Cont], "key": str|None}


_KEYWORDS = {"in", "return", "and", "or", "not", "if", "elif", "else", "yield", "for", "while", "assert", "lambda",
             "is", "await", "case", "typeof", "instanceof", "of", "new", "throw", "delete", "void", "export", "default"}


def _entry(c: Cont, i: int) -> dict:
    return c.entries.setdefault(i, {"toks": 0, "lits": [], "conts": [], "key": None, "idents": 0})


def parse_structure(rows: list[tuple[int, str]], lang: str) -> tuple[list[Lit], list[Cont]]:
    """Light parser over (row index, text) lines. Returns every string literal (with its
    container, entry and role) and every bracket container. Best effort: unbalanced or
    unusual syntax only makes the result less complete, never raises."""
    py = lang == "python"
    js = lang in ("javascript", "typescript")
    lits: list[Lit] = []
    conts: list[Cont] = []
    stack: list[Cont] = []
    idx: list[int] = []          # current entry index per stack level
    pend_key: list[str | None] = []
    root = Cont("{", -1, -1, None, 0)
    stack.append(root)
    idx.append(0)
    pend_key.append(None)
    in_block = False             # /* */
    tri = None                   # python triple-quote delimiter (multi-line string)
    tmpl = 0                     # JS template literal spanning lines
    last_row = None
    last_sig = ""                # last significant char (for JS regex literals)
    last_word = ""

    def cur():
        return stack[-1], idx[-1]

    for row, line in rows:
        if last_row is not None and row != last_row + 1 and lang == "ipynb":
            del stack[1:], idx[1:], pend_key[1:]
        last_row = row
        i, n = 0, len(line)
        while i < n:
            c = line[i]
            if in_block:
                j = line.find("*/", i)
                if j < 0:
                    break
                in_block, i = False, j + 2
                continue
            if tri:
                j = line.find(tri, i)
                if j < 0:
                    break
                tri, i = None, j + 3
                last_sig = "q"
                continue
            if tmpl:
                j = line.find("`", i)
                if j < 0:
                    break
                tmpl, i = 0, j + 1
                last_sig = "q"
                continue
            if c in " \t\r\n":
                i += 1
                continue
            if (py or lang in ("yaml",)) and c == "#":
                break
            if js and line.startswith("//", i):
                break
            if js and line.startswith("/*", i):
                in_block = True
                i += 2
                continue
            if js and c == "/" and (last_sig in "([{,;:=!&|?+-*%<>~^" or last_sig in ("", "k")):
                # regex literal
                j, cls = i + 1, False
                while j < n:
                    ch = line[j]
                    if ch == "\\":
                        j += 2
                        continue
                    if ch == "[":
                        cls = True
                    elif ch == "]":
                        cls = False
                    elif ch == "/" and not cls:
                        break
                    j += 1
                if j < n:
                    i = j + 1
                    while i < n and line[i].isalpha():
                        i += 1
                    last_sig = "q"
                    continue
            if c in "\"'`" or (py and c in "rRbBuUfF" and i + 1 < n and line[i + 1] in "\"'"
                               and (i == 0 or not (line[i - 1].isalnum() or line[i - 1] == "_"))):
                if c not in "\"'`":
                    i += 1
                    if line[i] in "rRbBuUfF":
                        i += 1
                    c = line[i]
                if py and line.startswith(c * 3, i):
                    j = line.find(c * 3, i + 3)
                    if j < 0:
                        tri = c * 3
                        break
                    i = j + 3
                    last_sig = "q"
                    _tok(stack, idx)
                    continue
                if c == "`":
                    j, depth = i + 1, 0
                    while j < n:
                        ch = line[j]
                        if ch == "\\":
                            j += 2
                            continue
                        if depth == 0 and ch == "`":
                            break
                        if line.startswith("${", j):
                            depth += 1
                            j += 2
                            continue
                        if depth and ch == "}":
                            depth -= 1
                        j += 1
                    if j >= n:
                        tmpl = 1
                        _tok(stack, idx)
                        break
                    end = j + 1
                else:
                    j = i + 1
                    while j < n and line[j] != c:
                        j += 2 if line[j] == "\\" else 1
                    end = min(n, j + 1)
                cont, ei = cur()
                lit = Lit(row, i, end, line[i + 1:end - 1], cont, ei)
                ent = _entry(cont, ei)
                # key?
                k = end
                while k < n and line[k] in " \t":
                    k += 1
                nxt = line[k] if k < n else ""
                is_key = False
                if ent["toks"] == 0 and c != "`":
                    if cont.kind == "{" and nxt == ":" and line[k:k + 2] != "::":
                        is_key = True
                if is_key:
                    lit.role = "key"
                    cont.keys.append((ei, lit.text, lit))
                    ent["key"] = lit.text
                    ent["keyed"] = True
                else:
                    ent["toks"] += 1
                    ent["lits"].append(lit)
                lits.append(lit)
                i = end
                last_sig = "q"
                continue
            if c.isalpha() or c in "_$":
                j = i
                while j < n and (line[j].isalnum() or line[j] in "_$"):
                    j += 1
                word = line[i:j]
                cont, ei = cur()
                ent = _entry(cont, ei)
                k = j
                while k < n and line[k] in " \t":
                    k += 1
                nxt = line[k:k + 2]
                if ent["toks"] == 0 and not ent.get("keyed") and (
                        (cont.kind == "{" and nxt[:1] == ":" and nxt != "::")
                        or (py and cont.kind == "(" and nxt[:1] == "=" and nxt != "==")):
                    cont.keys.append((ei, word, None))
                    ent["key"] = word
                    ent["keyed"] = True
                    i = k + 1
                    last_sig = ":"
                    continue
                ent["idents"] += 1
                ent["toks"] += 1
                i = j
                last_sig = "k" if word in _KEYWORDS else "a"
                last_word = word
                continue
            if c in "[({":
                cont, ei = cur()
                ent = _entry(cont, ei)
                call = c == "(" and last_sig in ("a", ")", "]", "q")
                nc = Cont(c, row, i, cont, ei, call)
                ent["conts"].append(nc)
                ent["toks"] += 1
                conts.append(nc)
                stack.append(nc)
                idx.append(0)
                pend_key.append(None)
                i += 1
                last_sig = c
                continue
            if c in "])}":
                if len(stack) > 1:
                    stack[-1].end = (row, i)
                    stack.pop()
                    idx.pop()
                    pend_key.pop()
                i += 1
                last_sig = c
                continue
            if c == ",":
                idx[-1] += 1
                i += 1
                last_sig = ","
                continue
            if c == ":" and stack[-1].kind == "{":
                # `[expr]: value` computed key, or a ternary; mark the entry keyed
                ent = _entry(*cur())
                ent["keyed"] = True
                ent["toks"] = 0 if ent.get("key") is None else ent["toks"]
            cont, ei = cur()
            if c not in ":":
                _entry(cont, ei)["toks"] += 1
            i += 1
            last_sig = c
    # roles for values / items
    for lit in lits:
        if lit.role == "key" or lit.cont is None:
            continue
        ent = lit.cont.entries.get(lit.entry) or {}
        sole = ent.get("toks") == 1 and len(ent.get("lits", [])) == 1
        if not sole:
            continue
        if ent.get("key") is not None:
            lit.role, lit.key = "value", ent["key"]
        elif not ent.get("keyed"):
            lit.role = "item"
    return lits, conts


def _tok(stack, idx):
    _entry(stack[-1], idx[-1])["toks"] += 1


def list_like(c: Cont, lang: str) -> bool:
    """A list, Python set or tuple literal (not a call's arguments, not a JS block)."""
    if c.row < 0:
        return False
    if c.kind == "[":
        return True
    if c.kind == "{":
        return lang in ("python", "ipynb") and not c.keys
    return c.kind == "(" and not c.call


def element(c: Cont, ei: int) -> Cont | None:
    """The object (or call) that makes up entry `ei` of list `c`, if the entry is one."""
    ent = c.entries.get(ei)
    if not ent or ent["lits"] or len(ent["conts"]) != 1 or ent["idents"] > 2:
        return None
    sub = ent["conts"][0]
    if sub.kind == "{" or (sub.kind == "(" and sub.call):
        return sub
    return None


# ------------------------------------------------------------------ YAML (indentation)
_YAML_KEY = re.compile(r"""^(?P<ind>\s*)(?P<dash>-\s+)?(?P<q>["']?)(?P<key>[^"'#\s][^"'#:]*?)(?P=q)\s*:(?:\s|$)""")
_YAML_ITEM = re.compile(r"""^(?P<ind>\s*)-\s+(?P<q>["']?)(?P<val>[^"'#\s][^"'#]*?)(?P=q)\s*(?:#.*)?$""")


@dataclass
class YamlKey:
    row: int
    col: int
    end: int
    key: str
    group: tuple
    value: tuple[int, int] | None    # span of the scalar value on the row
    item_group: tuple | None = None  # for `- key: v` / keys of a list-item mapping


def yaml_structure(lines: list[str]) -> tuple[list[YamlKey], list[tuple[int, int, int, tuple]]]:
    """Block-style YAML only: mapping keys grouped by the mapping they belong to (with the list
    they are an item of, for `- key: v`), and plain `- value` list items grouped by list."""
    keys: list[YamlKey] = []
    items: list[tuple[int, int, int, tuple]] = []
    stack: list[tuple[int, tuple]] = [(-1, ("root",))]
    for i, raw in enumerate(lines):
        if not raw.strip() or raw.lstrip().startswith(("#", "---", "...")):
            continue
        m = _YAML_KEY.match(raw)
        mi = None if m else _YAML_ITEM.match(raw)
        if not m and not mi:
            continue
        d = len((m or mi).group("ind"))
        if mi:
            while len(stack) > 1 and stack[-1][0] > d:
                stack.pop()
            items.append((i, mi.start("val"), mi.end("val"), ("list", stack[-1][1], d)))
            continue
        if m.group("dash"):
            k = d + len(m.group("dash"))
            while len(stack) > 1 and stack[-1][0] > d:
                stack.pop()
            parent_list = ("list", stack[-1][1], d)
            grp = ("item", i)
            stack.append((k, grp))
        else:
            k = d
            while len(stack) > 1 and stack[-1][0] > k:
                stack.pop()
            if stack[-1][0] < k:
                stack.append((k, ("map", i)))
            grp = stack[-1][1]
            parent_list = next((g for ind, g in reversed(stack) if g[0] == "item" and ind == k), None)
            parent_list = None if parent_list is None else ("item-of", parent_list)
        rest = raw[m.end():]
        vs = None
        vm = re.match(r"""\s*(["']?)([^"'#\s|>&*!][^#]*?)\1\s*(?:#.*)?$""", rest)
        if vm and vm.group(2):
            vs = (m.end() + vm.start(2), m.end() + vm.end(2))
        keys.append(YamlKey(i, m.start("key"), m.end("key"), m.group("key"), grp, vs,
                            parent_list if m.group("dash") else None))
    return keys, items
