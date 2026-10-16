# Copyright (c) 2026 Burnt and Toast Studios Ltd. Proprietary; see LICENSE-COMMERCIAL.
"""`init-evals`: generate a starter eval suite from the call sites the scan found.

Python call sites are read with `ast` (model, system/user messages, response_format JSON
schema and tools are extracted when they are literals or module-level constants).
JS/TS call sites are located with regexes; only the model is extracted, the rest is left
as TODOs. Anything that can't be read statically becomes a clearly marked TODO for the
customer to replace with 10-20 real examples. Runs locally; nothing is uploaded.
"""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

import yaml

from . import brand
from .evaluator import ADAPTERS
from .packs import PackSet, load_packs
from .scanner import ScanResult, scan

TODO = "TODO: replace with a real input from your app"
_UNRES = object()

# Generic call-shape names (the eval adapters speak these two shapes).
CHAT_CALL = re.compile(r"chat\.completions\.(?:create|parse)$")
RESP_CALL = re.compile(r"responses\.(?:create|parse)$")
JS_CALL = re.compile(r"(chat\.completions\.(?:create|parse)|responses\.(?:create|parse))\s*\(\s*\{")


def _dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _val(node, env, depth=0):
    """Statically evaluate literals, resolving names from module-level constants."""
    if depth > 20:
        return _UNRES
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        vals = [_val(e, env, depth + 1) for e in node.elts]
        return _UNRES if any(v is _UNRES for v in vals) else vals
    if isinstance(node, ast.Dict):
        out = {}
        for k, v in zip(node.keys, node.values):
            kk, vv = (_val(k, env, depth + 1) if k is not None else _UNRES), _val(v, env, depth + 1)
            if kk is _UNRES or vv is _UNRES:
                return _UNRES
            out[kk] = vv
        return out
    if isinstance(node, ast.Name):
        return env.get(node.id, _UNRES)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        v = _val(node.operand, env, depth + 1)
        return -v if isinstance(v, (int, float)) else _UNRES
    if isinstance(node, ast.Call) and _dotted(node.func) in ("os.getenv", "os.environ.get") and len(node.args) >= 2:
        return _val(node.args[1], env, depth + 1)       # env lookup with a literal default
    return _UNRES


def _module_env(tree) -> dict:
    env: dict = {}
    for st in tree.body:
        if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
            v = _val(st.value, env)
            if v is not _UNRES:
                env[st.targets[0].id] = v
    return env


def _tools_to_suite(tools) -> list[dict] | None:
    out = []
    for t in tools if isinstance(tools, list) else []:
        if not isinstance(t, dict):
            return None
        fn = t.get("function", t) if t.get("type", "function") == "function" else None
        if not fn or "name" not in fn:
            return None
        out.append({"name": fn["name"], "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {"type": "object", "properties": {}})})
    return out or None


def _schema_from_response_format(rf):
    if isinstance(rf, dict) and rf.get("type") == "json_schema":
        js = rf.get("json_schema") or {}
        return js.get("schema"), js.get("name")
    if isinstance(rf, dict) and rf.get("format", {}).get("type") == "json_schema":   # Responses `text=`
        f = rf["format"]
        return f.get("schema"), f.get("name")
    return None, None


def python_call_sites(path: Path, rel: str) -> list[dict]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    env = _module_env(tree)
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted(node.func)
        api = "chat" if CHAT_CALL.search(name) else "responses" if RESP_CALL.search(name) else None
        if not api:
            continue
        kw = {k.arg: k.value for k in node.keywords if k.arg}
        site = {"file": rel, "line": node.lineno, "api": api, "todos": []}
        model = _val(kw["model"], env) if "model" in kw else _UNRES
        site["model"] = model if isinstance(model, str) else None
        system = user = None
        if api == "chat" and "messages" in kw:
            msgs = kw["messages"]
            if isinstance(msgs, ast.List):
                for m in msgs.elts:
                    if isinstance(m, ast.Dict):
                        d = {(_val(k, env) if k else None): v for k, v in zip(m.keys, m.values)}
                        role = _val(d.get("role"), env) if d.get("role") is not None else None
                        content = _val(d.get("content"), env) if d.get("content") is not None else _UNRES
                        src = ast.unparse(d["content"]) if d.get("content") is not None else "?"
                        if role == "system":
                            system = content if isinstance(content, str) else None
                        elif role == "user":
                            user = content if isinstance(content, str) else f"{TODO} (was `{src}`)"
            else:
                site["todos"].append(f"messages built dynamically (`{ast.unparse(msgs)[:60]}`)")
        if api == "responses":
            if "instructions" in kw:
                v = _val(kw["instructions"], env)
                system = v if isinstance(v, str) else None
            if "input" in kw:
                v = _val(kw["input"], env)
                user = v if isinstance(v, str) else f"{TODO} (was `{ast.unparse(kw['input'])[:60]}`)"
        site["system"], site["prompt"] = system, user or TODO
        schema = name_ = None
        for key in ("response_format", "text"):
            if key in kw:
                rf = _val(kw[key], env)
                if rf is _UNRES:
                    site["todos"].append(f"`{key}` not readable statically; paste the JSON schema")
                else:
                    schema, name_ = _schema_from_response_format(rf)
        site["schema"], site["schema_name"] = schema, name_
        tools = None
        if "tools" in kw:
            tv = _val(kw["tools"], env)
            tools = _tools_to_suite(tv) if tv is not _UNRES else None
            if tools is None:
                site["todos"].append("`tools` not readable statically; paste the tool definitions")
        site["tools"] = tools
        sites.append(site)
    return sites


def js_call_sites(path: Path, rel: str) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    sites = []
    for m in JS_CALL.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        window = text[m.end(): m.end() + 1500]
        end = window.find("});")
        window = window[:end] if end >= 0 else window          # stay inside this call's object literal
        mm = re.search(r"""\bmodel\s*:\s*["'`]([^"'`]+)["'`]""", window)
        api = "chat" if m.group(1).startswith("chat") else "responses"
        todos = ["prompt, schema and tools are not extracted from JS/TS yet; paste them in"]
        if re.search(r"\btools\s*:", window):
            todos.append("this call passes `tools`: add them and set type: tool_call")
        sites.append({"file": rel, "line": line, "api": api, "model": mm.group(1) if mm else None,
                      "system": None, "prompt": TODO, "schema": None, "schema_name": None, "tools": None, "todos": todos})
    return sites


def build_suite(root: str | Path, res: ScanResult | None = None, packs: PackSet | None = None) -> tuple[dict, list[str]]:
    root = Path(root).resolve()
    packs = packs or load_packs()
    res = res or scan(root, packs=packs)
    by_file: dict[str, list] = {}
    for f in res.findings:
        by_file.setdefault(f.file, []).append(f)
    sites, skipped = [], []
    for rel in sorted(set(by_file) | set(res.file_signals)):
        provs = {f.provider for f in by_file.get(rel, [])}
        if provs and not (provs & ADAPTERS):
            skipped.append(f"{rel}: {', '.join(sorted(provs))} call sites (no eval adapter for this provider yet)")
            continue
        p = root / rel
        if p.suffix == ".py":
            sites += python_call_sites(p, rel)
        elif p.suffix in (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts"):
            sites += js_call_sites(p, rel)
    # Resolve model ids the AST couldn't see from scan findings on/near the call line
    in_scope = [f for f in res.findings if f.category in ("in_scope", "fine_tune") and f.provider in ADAPTERS]
    for s in sites:
        if not s["model"]:
            near = [f for f in in_scope if f.file == s["file"] and abs(f.line - s["line"]) <= 25]
            if near:
                s["model"] = min(near, key=lambda f: abs(f.line - s["line"])).model
    # Old/new defaults: most common headline model -> its replacement
    olds = Counter(f.model for f in in_scope if f.category == "in_scope" and f.kind in ("sdk_call", "string_literal"))
    old = olds.most_common(1)[0][0] if olds else None
    new = next((f.suggested for f in in_scope if f.model == old), None)
    pack = next((p for p in packs if p.provider in ADAPTERS and p.lookup(old or "")), None)
    eval_hint = ((pack.data.get("replacement_facts") or {}).get(new) or {}).get("eval", {}) if pack and new else {}
    apis = Counter(s["api"] for s in sites)
    cases = []
    for i, s in enumerate(sites, 1):
        base = Path(s["file"]).stem.replace("_", "-")
        c: dict = {"id": f"{base}-{s['line']}", "source": f"{s['file']}:{s['line']}"}
        if s["tools"]:
            c["type"] = "tool_call"
        elif s["schema"]:
            c["type"] = "structured"
        else:
            c["type"] = "text"
        if s["system"]:
            c["system"] = s["system"]
        c["prompt"] = s["prompt"]
        if s["schema"]:
            c["schema_name"] = s["schema_name"] or "output"
            c["schema"] = s["schema"]
        if s["tools"]:
            c["tools"] = s["tools"]
            c["expect"] = {"tool": s["tools"][0]["name"]}
        if c["type"] == "text":
            c["min_similarity"] = 0.5
        m = s["model"]
        if m and m.startswith("ft:"):
            c["models"] = {"old": m, "new": new}
            s["todos"].append("fine-tuned model: compares the fine-tune with the new base model + your prompt")
        elif m and m != old:
            fm = next((f for f in in_scope if f.model == m), None)
            if fm and fm.suggested:
                c["models"] = {"old": m, "new": fm.suggested}
        if s["api"] != (apis.most_common(1)[0][0] if apis else "chat"):
            s["todos"].append(f"uses the {s['api']} API; run it in a separate suite with --api {s['api']}")
        if s["todos"]:
            c["todo"] = s["todos"]
        cases.append(c)
    suite = {"name": f"{root.name}-regression", "api": apis.most_common(1)[0][0] if apis else "chat",
             "models": {"old": old, "new": new}, "max_output_tokens": 500}
    if eval_hint.get("model_params"):
        suite["model_params"] = {"old": {}, "new": eval_hint["model_params"]}
    suite["cases"] = cases
    return suite, skipped


HEADER = """# Starter regression suite generated by {cli} init-evals from {n} call site(s).
#
# NEXT STEPS
# 1. Replace every TODO prompt with a real input from your app, and copy each case so you
#    have 10-20 real examples covering your important paths (edge cases too).
# 2. Check the extracted schemas/tools still match your code; resolve the `todo:` notes,
#    then delete them.
# 3. Run with YOUR OWN key (calls go straight to the provider, never to us):
#      OPENAI_API_KEY=... {cli} eval {path}
#    or offline first:  {cli} eval {path} --dry-run
{model_params_note}{skipped}"""


def write_suite(suite: dict, skipped: list[str], out: str | Path) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    mp = ""
    if suite.get("model_params"):
        mp = "#\n# model_params.new comes from the migration pack (the new model needs it for tools/sampling).\n"
    sk = ("#\n# Not covered:\n" + "".join(f"#   - {x}\n" for x in skipped)) if skipped else ""
    head = HEADER.format(cli=brand.CLI_NAME, n=len(suite["cases"]), path=out.name, model_params_note=mp, skipped=sk)
    out.write_text(head + "\n" + yaml.safe_dump(suite, sort_keys=False, allow_unicode=True, width=110))
    return out
