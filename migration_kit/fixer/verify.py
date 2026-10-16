# Copyright (c) 2026 Burnt and Toast Studios Ltd. Proprietary; see LICENSE-COMMERCIAL.
"""Verify a fix plan: apply it to a scratch copy, check syntax and idempotence, then run
an eval in which each fixed call is sent exactly as it was before (old model, old
arguments) and as it is after the patch (new model, new arguments).

Live runs use the customer's own provider key and talk to the provider directly.
Without --live the eval runs in mock mode (no network): useful for the request-shape
and pipeline checks, not for behaviour.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .. import initevals
from ..evaluator import (ADAPTERS, ENDPOINT_API, REQUEST_CONTENT_PARAMS, TOKEN_CAP_PARAM, TOKEN_LIMIT_PARAMS, TOOL_PARAMS,
                         MockProvider, OpenAIProvider, load_suite, run_suite)
from ..packs import PackSet
from ..scanner import SKIP_DIRS, is_output_dir, mark_output
from . import jsfix, pyfix
from .engine import FixResult, plan_fixes

SMOKE = "Reply with the single word OK."
TOKEN_CAP = 300
CAP_PARAM = TOKEN_CAP_PARAM
TOKEN_PARAMS = TOKEN_LIMIT_PARAMS


def _copy(root: Path, dst: Path) -> None:
    def ignore(d, names):
        return {n for n in names if n in SKIP_DIRS or is_output_dir(Path(d) / n)}
    shutil.copytree(root, dst, ignore=ignore, symlinks=True)


def _apply_patch(repo: Path, res: FixResult) -> bool:
    """Apply the diff itself (not the in-memory result) so the artifact we hand over is what's tested."""
    if not res.diff:
        return True
    git = shutil.which("git")
    if git:
        pf = repo.parent / "fix.diff"
        pf.write_text(res.diff)
        r = subprocess.run([git, "apply", "--whitespace=nowarn", str(pf)], cwd=repo, capture_output=True, text=True)
        if r.returncode != 0:
            return False
        return all((repo / rel).read_text(encoding="utf-8") == text for rel, text in res.new_contents.items())
    for rel, text in res.new_contents.items():
        (repo / rel).write_text(text, encoding="utf-8")
    return True


def _syntax(repo: Path, res: FixResult) -> dict[str, str | None]:
    out = {}
    for rel, text in res.new_contents.items():
        suf = Path(rel).suffix
        if suf == ".py":
            out[rel] = pyfix.syntax_ok(text)
        elif suf in (".js", ".mjs", ".cjs", ".jsx"):
            out[rel] = jsfix.syntax_ok(text, "javascript", rel)
        elif suf in (".ts", ".tsx", ".mts"):
            out[rel] = jsfix.syntax_ok(text, "typescript", rel)
    return out


def _site_info(repo: Path, rel: str, line: int) -> dict | None:
    p = repo / rel
    sites = initevals.python_call_sites(p, rel) if p.suffix == ".py" else initevals.js_call_sites(p, rel)
    near = [s for s in sites if abs(s["line"] - line) <= 3]
    return min(near, key=lambda s: abs(s["line"] - line)) if near else None


def _cap(params: dict, api: str) -> dict:
    out = {k: v for k, v in params.items() if k not in REQUEST_CONTENT_PARAMS}
    if not TOKEN_PARAMS & set(out):
        out[CAP_PARAM[api]] = TOKEN_CAP
    return out


def build_cases(repo: Path, res: FixResult) -> tuple[dict[str, list[dict]], list[str]]:
    """Cases per API from the fixed calls: same request before/after, only the patch differs."""
    by_api: dict[str, list[dict]] = {}
    skipped = []
    for c in res.calls:
        where = f"{c.file}:{c.line_before}"
        if c.provider not in ADAPTERS:
            skipped.append(f"{where}: no eval adapter for {c.provider} yet")
            continue
        api = ENDPOINT_API.get(c.provider, {}).get(c.endpoint or "")
        if not api:
            skipped.append(f"{where}: {c.endpoint} calls can't be replayed by the eval adapter")
            continue
        if not c.old_model or not c.new_model:
            skipped.append(f"{where}: model not known statically")
            continue
        info = _site_info(repo, c.file, c.line_after) or {}
        prompt = info.get("prompt") or initevals.TODO
        case: dict = {"id": f"{Path(c.file).stem}-{c.line_before}", "source": where}
        notes: list[str] = []
        tools = info.get("tools")
        if not tools and TOOL_PARAMS & set(c.args_before):
            tools = [{"name": "placeholder_tool", "description": "Stand-in for this call's tools (not readable statically).",
                      "parameters": {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}}]
            notes.append("the call passes tools that aren't readable statically: replayed with one placeholder tool")
        if tools:
            info["tools"] = tools
            case["type"], case["tools"] = "tool_call", info["tools"]
            case["expect"] = {"tool": info["tools"][0]["name"]}
            smoke = f"Call the `{info['tools'][0]['name']}` tool with realistic example arguments."
        elif info.get("schema"):
            case["type"], case["schema"], case["schema_name"] = "structured", info["schema"], info.get("schema_name") or "output"
            smoke = "Produce a realistic example output."
        else:
            case["type"], case["min_similarity"] = "text", 0.0
            smoke = SMOKE
        if prompt.startswith(initevals.TODO):
            prompt = smoke
            notes.append("smoke prompt (the real input isn't readable statically): checks the request is accepted, not quality")
        case["prompt"] = prompt
        if info.get("system"):
            case["system"] = info["system"]
        case["models"] = {"old": c.old_model, "new": c.new_model}
        case["model_params"] = {"old": _cap(c.params_before, api), "new": _cap(c.params_after, api)}
        if not TOKEN_PARAMS & set(c.params_before):
            notes.append(f"{CAP_PARAM[api]}={TOKEN_CAP} added on both sides to cap cost")
        case["fix_rules"] = c.rules
        if notes:
            case["notes"] = notes
        by_api.setdefault(api, []).append(case)
    return by_api, skipped


def _merge_user_suite(path: str, res: FixResult) -> dict:
    """Customer suite: cases whose `source` matches a fixed call get its before/after arguments."""
    suite = load_suite(path)
    calls = {f"{c.file}:{c.line_before}": c for c in res.calls}
    for case in suite["cases"]:
        c = calls.get(str(case.get("source", "")))
        if c:
            mp = case.setdefault("model_params", {})
            keep = lambda d: {k: v for k, v in d.items() if k not in REQUEST_CONTENT_PARAMS}  # noqa: E731
            mp["old"] = {**(mp.get("old") or {}), **keep(c.params_before)}
            mp["new"] = {**(mp.get("new") or {}), **keep(c.params_after)}
            case.setdefault("models", {"old": c.old_model, "new": c.new_model})
            if TOKEN_PARAMS & (set(mp["old"]) | set(mp["new"])):
                case["max_output_tokens"] = None      # the call's own limit replaces the suite default
    return suite


def _provider(api: str, live: bool):
    if not live:
        return MockProvider()
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("--live needs OPENAI_API_KEY (your own key; calls go straight to the provider)")
    return OpenAIProvider(key, api)


def _accept(run: dict) -> dict:
    out = {"cases": len(run["cases"]), "old_errors": [], "new_errors": []}
    for c in run["cases"]:
        for side in ("old", "new"):
            err = (c.get(side) or {}).get("error")
            if err:
                out[f"{side}_errors"].append({"case": c["id"], "error": err[:300]})
    return out


def verify(root: str | Path, res: FixResult, packs: PackSet, out_dir: str | Path, live: bool = False,
           suite_path: str | None = None, assume_model: str | None = None,
           include_inferred: bool = False) -> dict:
    root = Path(root).resolve()
    out = Path(out_dir)
    mark_output(out)
    report: dict = {"live": live, "steps": {}}
    with tempfile.TemporaryDirectory(prefix="fix-verify-") as tmp:
        repo = Path(tmp) / "repo"
        _copy(root, repo)
        report["steps"]["patch_applies"] = _apply_patch(repo, res)
        syn = _syntax(repo, res)
        report["steps"]["syntax"] = {"ok": all(v is None for v in syn.values()), "files": syn}
        again = plan_fixes(repo, packs, model_swap=True, assume_model=assume_model, include_inferred=include_inferred)
        leftover = [f"{i.file}:{i.line} {i.rule}" for i in again.items if i.status.startswith("fixed")]
        report["steps"]["idempotent"] = {"ok": not again.diff, "remaining_edits": leftover,
                                         "files": sorted(again.new_contents)}
        by_api, skipped = build_cases(repo, res)
        runs = []
        if suite_path:
            suite = _merge_user_suite(suite_path, res)
            r = run_suite(suite, _provider(suite.get("api", "chat"), live))
            r["_suite_cases"] = suite["cases"]
            runs.append(r)
        for api, cases in sorted(by_api.items()):
            suite = {"name": f"fix-verify-{api}", "api": api, "models": {"old": cases[0]["models"]["old"],
                                                                         "new": cases[0]["models"]["new"]},
                     "cases": cases}
            r = run_suite(suite, _provider(api, live))
            r["_suite_cases"] = cases
            runs.append(r)
        control = []
        if live:
            # Control: the UNPATCHED arguments on the new model. Shows each fix was needed.
            for api, cases in sorted(by_api.items()):
                prov = _provider(api, live)
                for case in cases:
                    mp = case["model_params"]
                    if mp["old"] == mp["new"]:
                        continue
                    c2 = {**case, "model_params": {"new": mp["old"]}}
                    o = prov.run(c2, case["models"]["new"], "new", {"api": api})
                    control.append({"case": case["id"], "model": case["models"]["new"], "params": mp["old"],
                                    "rejected": bool(o.error), "error": (o.error or "")[:300]})
        report["steps"]["control"] = control
        report["steps"]["eval"] = {"mode": "live" if live else "mock", "skipped": skipped,
                                   "runs": [{"suite": r["suite"], "api": r["api"], "summary": r["summary"],
                                             "acceptance": _accept(r), "usage": r.get("usage"),
                                             "_cases": [{"id": c["id"], "source": c.get("source")}
                                                        for c in r.get("_suite_cases", [])]} for r in runs]}
        for r in runs:
            r.pop("_suite_cases", None)
            (out / f"{r['suite']}.json").write_text(json.dumps(r, indent=2, default=str))
    # A rejection on a call that still has an open manual item is expected (the plan says so);
    # anything else is a real failure of the patch.
    manual: dict[str, list[str]] = {}
    for i in res.items:
        if i.status == "manual":
            manual.setdefault(f"{i.file}:{i.line}", []).append(i.rule)
    unexpected = 0
    for run in report["steps"]["eval"]["runs"]:
        src = {c["id"]: c.get("source") for c in run.get("_cases", [])}
        for e in run["acceptance"]["new_errors"]:
            open_items = manual.get(str(src.get(e["case"])), [])
            e["expected"] = bool(open_items)
            e["open_manual_items"] = open_items
            unexpected += 0 if open_items else 1
        run.pop("_cases", None)
    report["unexpected_rejections"] = unexpected
    report["ok"] = (report["steps"]["patch_applies"] and report["steps"]["syntax"]["ok"]
                    and report["steps"]["idempotent"]["ok"] and unexpected == 0)
    (out / "verify.json").write_text(json.dumps(report, indent=2, default=str))
    (out / "verify.md").write_text(to_markdown(report))
    return report


def to_markdown(r: dict) -> str:
    s = r["steps"]
    yes = lambda b: "PASS" if b else "FAIL"  # noqa: E731
    out = ["# Fix verification", "",
           f"- Overall: **{yes(r['ok'])}**" + ("" if r["live"] else " (mock eval: request shapes and pipeline only, no real model calls)"),
           f"- Unexpected API rejections of patched calls: **{r.get('unexpected_rejections', 0)}**",
           f"- Patch applies to a clean copy: **{yes(s['patch_applies'])}**",
           f"- Syntax of changed files: **{yes(s['syntax']['ok'])}**"]
    for f, err in s["syntax"]["files"].items():
        if err:
            out.append(f"  - `{f}`: {err}")
    out.append(f"- Re-running the fixer on the patched code changes nothing: **{yes(s['idempotent']['ok'])}**")
    for x in s["idempotent"]["remaining_edits"]:
        out.append(f"  - still fixable: {x}")
    ev = s["eval"]
    out += ["", f"## Eval ({ev['mode']})", "",
            "Each fixed call is sent as before the patch (old model, old arguments) and as after it (new model, patched arguments).", "",
            "| Suite | API | Cases | Old rejected | New rejected | Results |", "|---|---|---|---|---|---|"]
    for run in ev["runs"]:
        a = run["acceptance"]
        res = ", ".join(f"{k} {v}" for k, v in sorted(run["summary"].items()))
        out.append(f"| {run['suite']} | {run['api']} | {a['cases']} | {len(a['old_errors'])} | {len(a['new_errors'])} | {res} |")
    news = [(run, e) for run in ev["runs"] for e in run["acceptance"]["new_errors"]]
    if news:
        out += ["", "### Patched calls the API still rejects", ""]
        for run, e in news:
            tag = (f"expected: open manual item ({', '.join(e['open_manual_items'])})" if e.get("expected")
                   else "**unexpected: the patch is wrong here**")
            out.append(f"- `{e['case']}` ({run['api']}): {tag}. {' '.join(e['error'].split())[:220]}")
    olds = [(run, e) for run in ev["runs"] for e in run["acceptance"]["old_errors"]]
    if olds:
        out += ["", "### Original calls that already failed (before the patch)", ""]
        for run, e in olds:
            out.append(f"- `{e['case']}` ({run['api']}): {' '.join(e['error'].split())[:220]}")
    if s.get("control"):
        out += ["", "### Control: unpatched arguments on the new model", "",
                "| Case | Arguments | Result |", "|---|---|---|"]
        for c in s["control"]:
            err = " ".join(c["error"].split())
            res = f"rejected: {err[:200]}" if c["rejected"] else "accepted (this fix was not strictly required)"
            out.append(f"| `{c['case']}` | `{json.dumps(c['params'])}` | {res.replace('|', '/')} |")
    if ev["skipped"]:
        out += ["", "Not replayed:"] + [f"- {x}" for x in ev["skipped"]]
    out += ["", "Drift on smoke prompts is expected: they check that the API accepts the patched request. "
                "Behaviour is checked by your own suite (`init-evals`, then `--evals`)."]
    return "\n".join(out) + "\n"
