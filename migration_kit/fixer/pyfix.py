"""Python adapter: finds API calls and edits keyword arguments with libcst (lossless:
formatting, comments and quoting outside the edited arguments are untouched)."""
from __future__ import annotations

import ast
from typing import Any

import libcst as cst
from libcst.helpers import get_full_name_for_node
from libcst.metadata import MetadataWrapper, PositionProvider

from .callsite import UNRES, Arg, CallSite, Edit

ENV_GETTERS = {"os.getenv", "os.environ.get", "getenv", "environ.get"}


def callee_matches(dotted: str, patterns) -> str | None:
    """Longest pattern that matches `dotted` as a whole-segment suffix
    ("chat.completions.create" beats "completions.create")."""
    best = None
    for p in patterns:
        if (dotted == p or dotted.endswith("." + p)) and (best is None or len(p) > len(best)):
            best = p
    return best


# ------------------------------------------------------------------ static values
def _env(tree: ast.Module) -> dict[str, ast.expr]:
    env: dict[str, ast.expr] = {}
    for st in tree.body:
        if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
            env[st.targets[0].id] = st.value
        elif isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name) and st.value is not None:
            env[st.target.id] = st.value
    return env


def _dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def resolve(node: ast.expr, env: dict, depth: int = 0) -> tuple[Any, str | None]:
    """(value, env_var). env_var is set when the value is an env lookup's literal default."""
    if depth > 20:
        return UNRES, None
    if isinstance(node, ast.Constant):
        return node.value, None
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        v, _ = resolve(node.operand, env, depth + 1)
        return (-v if isinstance(v, (int, float)) else UNRES), None
    if isinstance(node, (ast.List, ast.Tuple)):
        vals = [resolve(e, env, depth + 1)[0] for e in node.elts]
        return (UNRES if any(v is UNRES for v in vals) else vals), None
    if isinstance(node, ast.Dict):
        out = {}
        for k, v in zip(node.keys, node.values):
            if k is None:
                return UNRES, None
            kk, vv = resolve(k, env, depth + 1)[0], resolve(v, env, depth + 1)[0]
            if kk is UNRES or vv is UNRES:
                return UNRES, None
            out[kk] = vv
        return out, None
    if isinstance(node, ast.Name):
        if node.id in env:
            return resolve(env[node.id], env, depth + 1)
        return UNRES, None
    if isinstance(node, ast.Call) and _dotted(node.func) in ENV_GETTERS and node.args:
        var = node.args[0].value if isinstance(node.args[0], ast.Constant) else None
        if len(node.args) >= 2:
            return resolve(node.args[1], env, depth + 1)[0], var
        return UNRES, var
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or) and len(node.values) == 2:
        first, second = node.values
        if isinstance(first, ast.Call) and _dotted(first.func) in ENV_GETTERS:
            var = first.args[0].value if first.args and isinstance(first.args[0], ast.Constant) else None
            return resolve(second, env, depth + 1)[0], var
    return UNRES, None


def _arg_from(name: str, src: str, env: dict) -> Arg:
    try:
        node = ast.parse(src.strip(), mode="eval").body
    except SyntaxError:
        return Arg(name, UNRES, src)
    val, var = resolve(node, env)
    nested = None
    if isinstance(node, ast.Dict):
        nested = {}
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                nested[k.value] = Arg(k.value, resolve(v, env)[0], ast.unparse(v))
    elif isinstance(node, ast.Name) and isinstance(env.get(node.id), ast.Dict):
        nested = {}
        for k, v in zip(env[node.id].keys, env[node.id].values):
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                nested[k.value] = Arg(k.value, resolve(v, env)[0], ast.unparse(v))
    return Arg(name, val, src, nested, var)


# ------------------------------------------------------------------ discovery
class _Finder(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, module: cst.Module, rel: str, callees: list[str], env: dict):
        self.module, self.rel, self.callees, self.env = module, rel, callees, env
        self.sites: list[CallSite] = []

    def visit_Call(self, node: cst.Call) -> None:
        name = get_full_name_for_node(node.func)
        if not name or not callee_matches(name, self.callees):
            return
        pos = self.get_metadata(PositionProvider, node).start
        site = CallSite(self.rel, pos.line, "python", name, key=(pos.line, pos.column))
        for a in node.args:
            if a.star == "**":
                site.opaque = True
            elif a.star == "*":
                site.opaque = True
            elif a.keyword is not None:
                src = self.module.code_for_node(a.value)
                site.args[a.keyword.value] = _arg_from(a.keyword.value, src, self.env)
        self.sites.append(site)


def find_calls(text: str, rel: str, callees: list[str]) -> list[CallSite]:
    try:
        module = cst.parse_module(text)
        tree = ast.parse(text)
    except (cst.ParserSyntaxError, SyntaxError, ValueError):
        return []
    f = _Finder(module, rel, callees, _env(tree))
    MetadataWrapper(module).visit(f)
    return f.sites


# ------------------------------------------------------------------ editing
def py_literal(value: Any, quote: str = '"') -> str:
    if isinstance(value, str):
        r = repr(value)
        if quote == '"' and r.startswith("'") and '"' not in value:
            r = '"' + r[1:-1] + '"'
        return r
    if isinstance(value, dict):
        return "{" + ", ".join(f"{py_literal(k, quote)}: {py_literal(v, quote)}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(py_literal(v, quote) for v in value) + "]"
    return repr(value)


def _quote_of(node: cst.Call) -> str:
    for a in node.args:
        if isinstance(a.value, cst.SimpleString):
            q = a.value.value.lstrip("rbuRBUfF")[:1]
            if q in "'\"":
                return q
    return '"'


def _add_arg(args: list[cst.Arg], new: cst.Arg, call: cst.Call) -> list[cst.Arg]:
    if not args:
        return [new]
    last = args[-1]
    if len(args) >= 2 and isinstance(args[-2].comma, cst.Comma):
        sep = args[-2].comma
    elif isinstance(last.comma, cst.Comma) and isinstance(last.comma.whitespace_after, cst.ParenthesizedWhitespace):
        sep = last.comma.with_changes(whitespace_after=cst.ParenthesizedWhitespace(
            first_line=cst.TrailingWhitespace(), empty_lines=[],
            indent=True, last_line=cst.SimpleWhitespace(_indent_of(call, last))))
    elif isinstance(call.whitespace_before_args, cst.ParenthesizedWhitespace):
        sep = cst.Comma(whitespace_after=call.whitespace_before_args)
    else:
        sep = cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))
    return [*args[:-1], last.with_changes(comma=sep), new.with_changes(comma=last.comma)]


def _indent_of(call: cst.Call, arg: cst.Arg) -> str:
    ws = call.whitespace_before_args
    if isinstance(ws, cst.ParenthesizedWhitespace):
        return ws.last_line.value
    return "    "


def _kwarg(name: str, value: Any, quote: str) -> cst.Arg:
    return cst.Arg(keyword=cst.Name(name), value=cst.parse_expression(py_literal(value, quote)),
                   equal=cst.AssignEqual(whitespace_before=cst.SimpleWhitespace(""),
                                         whitespace_after=cst.SimpleWhitespace("")))


def _dict_set(d: cst.Dict, key: str, value: Any, quote: str) -> cst.Dict:
    el = cst.DictElement(cst.parse_expression(py_literal(key, quote)), cst.parse_expression(py_literal(value, quote)))
    els = list(d.elements)
    if els:
        last = els[-1]
        sep = els[-2].comma if len(els) >= 2 and isinstance(els[-2].comma, cst.Comma) else \
            cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))
        els = [*els[:-1], last.with_changes(comma=sep), el.with_changes(comma=last.comma)]
    else:
        els = [el]
    return d.with_changes(elements=els)


class _Editor(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, edits: dict[tuple, list[Edit]]):
        self.edits = edits
        self.applied: list[tuple[tuple, Edit]] = []

    def leave_Call(self, original: cst.Call, updated: cst.Call) -> cst.Call:
        pos = self.get_metadata(PositionProvider, original).start
        key = (pos.line, pos.column)
        if key not in self.edits:
            return updated
        q = _quote_of(original)
        args = list(updated.args)
        for e in self.edits[key]:
            head, _, rest = e.path.partition(".")
            idx = next((i for i, a in enumerate(args) if a.keyword is not None and a.keyword.value == head), None)
            if e.op == "rename" and idx is not None and not rest:
                args[idx] = args[idx].with_changes(keyword=cst.Name(e.new_name))
            elif e.op == "remove" and idx is not None and not rest:
                if idx == len(args) - 1 and idx > 0:
                    args[idx - 1] = args[idx - 1].with_changes(comma=args[idx].comma)
                del args[idx]
            elif e.op == "set" and not rest and idx is None:
                args = _add_arg(args, _kwarg(head, e.value, q), updated)
            elif e.op == "set" and rest and idx is None:
                args = _add_arg(args, _kwarg(head, {rest: e.value}, q), updated)
            elif e.op == "set" and rest and isinstance(args[idx].value, cst.Dict):
                args[idx] = args[idx].with_changes(value=_dict_set(args[idx].value, rest, e.value, q))
            else:
                continue
            self.applied.append((key, e))
        return updated.with_changes(args=args)


def apply_edits(text: str, edits: dict[tuple, list[Edit]]) -> tuple[str, list]:
    module = cst.parse_module(text)
    ed = _Editor(edits)
    new = MetadataWrapper(module).visit(ed)
    return new.code, ed.applied


def syntax_ok(text: str) -> str | None:
    try:
        compile(text, "<patched>", "exec")
        return None
    except SyntaxError as e:
        return f"{e.msg} (line {e.lineno})"
