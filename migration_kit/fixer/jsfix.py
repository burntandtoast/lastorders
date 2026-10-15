"""JavaScript/TypeScript adapter, dependency-free.

A small lexer masks strings, template literals, comments and regex literals (same
length, newlines kept), so brackets and commas can be matched reliably on the masked
text. Calls are found as dotted identifier chains followed by `(`; the first argument
must be an object literal. Its top-level properties are parsed into key/value spans
and edits are applied as text splices that keep the surrounding formatting.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from .callsite import UNRES, Arg, CallSite, Edit
from .pyfix import callee_matches

_REGEX_PREV = set("(,=:[!&|?{};+-*%<>~^")
_REGEX_KW = ("return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void", "throw", "yield", "await")


def mask(src: str) -> str:
    out = list(src)
    i, n = 0, len(src)
    last_sig = ""            # last significant (non-space) char outside literals
    last_word = ""

    def blank(a: int, b: int):
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        c = src[i]
        if c in "\"'":
            j = i + 1
            while j < n and src[j] != c and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            blank(i + 1, min(j, n))
            i = j + 1
            last_sig, last_word = c, ""
        elif c == "`":
            j, depth = i + 1, 0
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if depth == 0 and src[j] == "`":
                    break
                if src.startswith("${", j):
                    depth += 1
                    j += 2
                    continue
                if depth and src[j] == "}":
                    depth -= 1
                j += 1
            blank(i + 1, min(j, n))
            i = j + 1
            last_sig, last_word = "`", ""
        elif src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
        elif c == "/" and (last_sig == "" or last_sig in _REGEX_PREV or last_word in _REGEX_KW):
            j, in_class = i + 1, False
            while j < n and src[j] != "\n":
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "[":
                    in_class = True
                elif src[j] == "]":
                    in_class = False
                elif src[j] == "/" and not in_class:
                    break
                j += 1
            blank(i + 1, min(j, n))
            i = j + 1
            last_sig, last_word = "/", ""
        else:
            if not c.isspace():
                if c.isalnum() or c in "_$":
                    m = re.match(r"[\w$]+", src[i:])
                    last_word = m.group(0)
                    last_sig = last_word[-1]
                    i += len(last_word)
                    continue
                last_sig, last_word = c, ""
            i += 1
    return "".join(out)


_PAIRS = {"(": ")", "[": "]", "{": "}"}


def _match(m: str, i: int) -> int:
    """Index of the bracket closing the one at i (on masked text), or -1."""
    stack = []
    for k in range(i, len(m)):
        ch = m[k]
        if ch in _PAIRS:
            stack.append(_PAIRS[ch])
        elif ch in ")]}":
            if not stack or stack.pop() != ch:
                return -1
            if not stack:
                return k
    return -1


@dataclass
class Prop:
    key: str
    key_span: tuple[int, int]
    val_span: tuple[int, int] | None    # None for shorthand / spread
    span: tuple[int, int]               # whole property (no comma)
    kind: str = "kv"                    # kv | shorthand | spread | other


def parse_object(src: str, m: str, a: int, b: int) -> list[Prop]:
    """Top-level properties of the object literal src[a..b] (a='{', b='}')."""
    props, i = [], a + 1
    while i < b:
        # split at the next top-level comma
        j, depth = i, 0
        while j < b:
            ch = m[j]
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            elif ch == "," and depth == 0:
                break
            j += 1
        seg_m = m[i:j]
        lead = len(seg_m) - len(seg_m.lstrip())
        s, e = i + lead, i + len(seg_m.rstrip())
        if s < e:
            seg = src[s:e]
            km = re.match(r"""(?:([A-Za-z_$][\w$]*)|"([^"]*)"|'([^']*)')\s*:""", seg)
            if seg.startswith("..."):
                props.append(Prop("...", (s, s + 3), None, (s, e), "spread"))
            elif km:
                key = km.group(1) or km.group(2) or km.group(3)
                kend = s + len(km.group(0).rstrip(":").rstrip())
                vs = s + km.end()
                while vs < e and src[vs].isspace():
                    vs += 1
                props.append(Prop(key, (s, kend), (vs, e), (s, e)))
            elif re.fullmatch(r"[A-Za-z_$][\w$]*", seg):
                props.append(Prop(seg, (s, e), None, (s, e), "shorthand"))
            else:
                props.append(Prop(seg[:20], (s, e), None, (s, e), "other"))
        i = j + 1
    return props


# ------------------------------------------------------------------ static values
_NUM = re.compile(r"-?\d+(?:\.\d+)?(?:e-?\d+)?$")
_DECL = re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(.+?);?\s*$", re.M)
_ENV = re.compile(r"""^(?:process\.env\.([A-Z_][A-Z0-9_]*)|process\.env\[\s*["']([A-Z_][A-Z0-9_]*)["']\s*\]|import\.meta\.env\.([A-Z_][A-Z0-9_]*))\s*(?:\?\?|\|\|)\s*(.+)$""")


def literal(text: str, env: dict[str, str], depth: int = 0) -> tuple[Any, str | None]:
    t = text.strip().rstrip(",").strip()
    if depth > 10 or not t:
        return UNRES, None
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'" and t[0] not in t[1:-1]:
        return t[1:-1], None
    if len(t) >= 2 and t[0] == t[-1] == "`" and "${" not in t:
        return t[1:-1], None
    if _NUM.match(t):
        return (float(t) if any(x in t for x in ".e") else int(t)), None
    if t in ("true", "false", "null"):
        return {"true": True, "false": False, "null": None}[t], None
    em = _ENV.match(t)
    if em:
        var = em.group(1) or em.group(2) or em.group(3)
        return literal(em.group(4), env, depth + 1)[0], var
    if re.fullmatch(r"[A-Za-z_$][\w$]*", t) and t in env:
        return literal(env[t], env, depth + 1)
    return UNRES, None


def _env(src: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in _DECL.finditer(src)}


_CALL = re.compile(r"((?:new\s+)?[A-Za-z_$][\w$]*(?:\s*\??\.\s*[A-Za-z_$][\w$]*)*)\s*\(")


def _calls(src: str, m: str, callees: list[str]):
    for cm in _CALL.finditer(m):
        dotted = re.sub(r"\s|\?", "", cm.group(1)).removeprefix("new")
        dotted = re.sub(r"^new(?=[A-Z])", "", dotted)
        if not callee_matches(dotted, callees):
            continue
        lp = cm.end() - 1
        rp = _match(m, lp)
        if rp < 0:
            continue
        k = lp + 1
        while k < rp and m[k].isspace():
            k += 1
        yield dotted, cm.start(), lp, rp, k


def find_calls(src: str, rel: str, callees: list[str], lang: str = "javascript") -> list[CallSite]:
    m = mask(src)
    env = _env(src)
    sites = []
    for dotted, start, lp, rp, k in _calls(src, m, callees):
        line = src.count("\n", 0, start) + 1
        site = CallSite(rel, line, lang, dotted, key=start)
        if m[k] != "{":
            site.opaque = k < rp            # options passed as a variable
            sites.append(site)
            continue
        ob = _match(m, k)
        for p in parse_object(src, m, k, ob):
            if p.kind in ("spread", "other"):
                site.opaque = True
                continue
            if p.kind == "shorthand":
                val, var = literal(p.key, env)
                site.args[p.key] = Arg(p.key, val, p.key, None, var)
                continue
            vs, ve = p.val_span
            vtext = src[vs:ve]
            val, var = literal(vtext, env)
            nested = None
            if m[vs] == "{":
                vend = _match(m, vs)
                nested = {}
                for q in parse_object(src, m, vs, vend):
                    if q.val_span:
                        nested[q.key] = Arg(q.key, literal(src[q.val_span[0]:q.val_span[1]], env)[0],
                                            src[q.val_span[0]:q.val_span[1]])
                if nested and all(a.value is not UNRES for a in nested.values()):
                    val = {kk: a.value for kk, a in nested.items()}
            site.args[p.key] = Arg(p.key, val, vtext, nested, var)
        sites.append(site)
    return sites


# ------------------------------------------------------------------ editing
def js_literal(v: Any, quote: str = '"') -> str:
    if isinstance(v, str):
        s = json.dumps(v)
        if quote == "'":
            s = "'" + s[1:-1].replace("'", "\\'").replace('\\"', '"') + "'"
        return s
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k if re.fullmatch(r'[A-Za-z_$][\w$]*', k) else json.dumps(k)}: {js_literal(x, quote)}"
                                for k, x in v.items()) + " }"
    if isinstance(v, list):
        return "[" + ", ".join(js_literal(x, quote) for x in v) + "]"
    return json.dumps(v)


def _insert_prop(src: str, m: str, a: int, b: int, text: str) -> tuple[int, int, str]:
    """Splice (start, end, replacement) that adds `text` as the last property of {a..b}."""
    props = parse_object(src, m, a, b)
    if not props:
        return a + 1, a + 1, f" {text} "
    last = props[-1]
    after = m[last.span[1]:b]
    has_comma = after.lstrip().startswith(",")
    multiline = "\n" in m[a:props[0].span[0]]
    if multiline:
        ls = src.rfind("\n", 0, last.span[0]) + 1
        indent = re.match(r"[ \t]*", src[ls:]).group(0)
        if has_comma:
            cpos = last.span[1] + after.index(",") + 1
            return cpos, cpos, f"\n{indent}{text},"
        return last.span[1], last.span[1], f",\n{indent}{text}"
    if has_comma:
        cpos = last.span[1] + after.index(",") + 1
        return cpos, cpos, f" {text},"
    return last.span[1], last.span[1], f", {text}"


def _quote(src: str, site_start: int, end: int) -> str:
    seg = src[site_start:end]
    d, s = seg.count('"'), seg.count("'")
    return "'" if s > d else '"'


def apply_edits(src: str, edits: dict[int, list[Edit]], callees: list[str]) -> tuple[str, list]:
    m = mask(src)
    splices: list[tuple[int, int, str]] = []
    applied = []
    for dotted, start, lp, rp, k in _calls(src, m, callees):
        if start not in edits or m[k] != "{":
            continue
        ob = _match(m, k)
        props = {p.key: p for p in parse_object(src, m, k, ob) if p.kind == "kv"}
        q = _quote(src, k, ob)
        for e in edits[start]:
            head, _, rest = e.path.partition(".")
            p = props.get(head)
            if e.op == "rename" and p and not rest:
                ktext = src[p.key_span[0]:p.key_span[1]]
                nk = e.new_name if ktext[0] not in "\"'" else ktext[0] + e.new_name + ktext[0]
                splices.append((p.key_span[0], p.key_span[1], nk))
            elif e.op == "remove" and p and not rest:
                s, t = p.span
                tail = m[t:ob]
                if tail.lstrip().startswith(","):
                    t = t + tail.index(",") + 1
                ls = src.rfind("\n", 0, s) + 1
                le = src.find("\n", t)
                if src[ls:s].strip() == "" and le >= 0 and src[t:le].strip() == "":
                    s, t = ls, le + 1                      # property on its own line(s): drop the lines
                splices.append((s, t, ""))
            elif e.op == "set" and p is None:
                val = e.value if not rest else {rest: e.value}
                splices.append(_insert_prop(src, m, k, ob, f"{head}: {js_literal(val, q)}"))
            elif e.op == "set" and rest and p and m[p.val_span[0]] == "{":
                vs = p.val_span[0]
                splices.append(_insert_prop(src, m, vs, _match(m, vs), f"{rest}: {js_literal(e.value, q)}"))
            else:
                continue
            applied.append((start, e))
    out = src
    for _, (s, t, r) in sorted(enumerate(splices), key=lambda x: (x[1][0], x[1][1], x[0]), reverse=True):
        out = out[:s] + r + out[t:]
    return out, applied


def syntax_ok(src: str, lang: str, path_hint: str = "") -> str | None:
    """Bracket balance on masked text for every file; `node --check` for plain JS when node exists."""
    m = mask(src)
    stack = []
    for i, ch in enumerate(m):
        if ch in _PAIRS:
            stack.append((_PAIRS[ch], i))
        elif ch in ")]}":
            if not stack or stack.pop()[0] != ch:
                return f"unbalanced '{ch}' at line {src.count(chr(10), 0, i) + 1}"
    if stack:
        return f"unclosed bracket from line {src.count(chr(10), 0, stack[-1][1]) + 1}"
    node = shutil.which("node")
    if node and lang == "javascript" and not path_hint.endswith(".jsx"):
        try:
            r = subprocess.run([node, "--check", "--input-type=module"], input=src, capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                r2 = subprocess.run([node, "--check"], input=src, capture_output=True, text=True, timeout=30)
                if r2.returncode != 0:
                    return (r.stderr.strip().splitlines() or ["node --check failed"])[-1][:200]
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None
