"""`eval`: regression harness comparing an old and a new model on a YAML suite."""
from __future__ import annotations

import copy
import difflib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
import yaml

DEFAULT_BASE = "https://api.openai.com/v1"


# ---------------------------------------------------------------- data types
@dataclass
class ToolCall:
    name: str
    arguments: Any            # parsed JSON if possible, else raw string


@dataclass
class ModelOutput:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    error: str | None = None
    latency_ms: int | None = None
    usage: dict | None = None
    simulated: bool = False
    resolved_model: str | None = None
    truncated: bool = False


@dataclass
class CaseResult:
    id: str
    type: str
    status: str                     # pass | drift | fail | improved | error
    old: dict
    new: dict
    checks: dict
    notes: list[str]


# ---------------------------------------------------------------- suite
def load_suite(path: str | Path) -> dict:
    suite = yaml.safe_load(Path(path).read_text())
    if not isinstance(suite, dict) or not suite.get("cases"):
        raise ValueError("Suite must be a mapping with a non-empty 'cases' list")
    for i, c in enumerate(suite["cases"]):
        c.setdefault("id", f"case-{i+1}")
        c.setdefault("type", "text")
        if c["type"] not in ("structured", "tool_call", "text"):
            raise ValueError(f"{c['id']}: type must be structured, tool_call or text")
        if c["type"] == "structured" and "schema" not in c:
            raise ValueError(f"{c['id']}: structured cases need a 'schema'")
        if c["type"] == "tool_call" and not c.get("tools"):
            raise ValueError(f"{c['id']}: tool_call cases need 'tools'")
        if "prompt" not in c:
            raise ValueError(f"{c['id']}: missing 'prompt'")
    return suite


# ---------------------------------------------------------------- providers
def synth(schema: dict, depth: int = 0) -> Any:
    """Smallest plausible instance of a JSON schema (for mock mode)."""
    if not isinstance(schema, dict) or depth > 8:
        return None
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    for k in ("anyOf", "oneOf"):
        if k in schema:
            return synth(schema[k][0], depth + 1)
    t = schema.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), t[0])
    if t == "object" or "properties" in schema:
        return {k: synth(v, depth + 1) for k, v in schema.get("properties", {}).items()}
    if t == "array":
        n = schema.get("minItems", 1)
        return [synth(schema.get("items", {}), depth + 1) for _ in range(n)]
    if t == "integer":
        return int(schema.get("minimum", 1))
    if t == "number":
        return float(schema.get("minimum", 1.0))
    if t == "boolean":
        return True
    if t == "null":
        return None
    fmt = schema.get("format")
    return {"date": "2026-01-01", "date-time": "2026-01-01T00:00:00Z", "email": "user@example.com"}.get(fmt, "example")


class MockProvider:
    """Deterministic, offline. Uses a case's `mock.old` / `mock.new` if given."""
    name = "mock"

    def run(self, case: dict, model: str, role: str, suite: dict) -> ModelOutput:
        canned = (case.get("mock") or {}).get(role)
        if canned is not None:
            return self._from_canned(canned)
        if case["type"] == "structured":
            return ModelOutput(text=json.dumps(synth(case["schema"])), simulated=True)
        if case["type"] == "tool_call":
            t = case["tools"][0]
            return ModelOutput(tool_calls=[ToolCall(t["name"], synth(t.get("parameters", {})))], simulated=True)
        return ModelOutput(text=f"[mock {model}] response to: {case['prompt'][:80]}", simulated=True)

    @staticmethod
    def _from_canned(c: Any) -> ModelOutput:
        if isinstance(c, dict) and ("tool_calls" in c or "text" in c or "error" in c):
            calls = [ToolCall(tc["name"], tc.get("arguments", {})) for tc in c.get("tool_calls", [])]
            text = c.get("text")
            if text is not None and not isinstance(text, str):
                text = json.dumps(text)
            return ModelOutput(text=text, tool_calls=calls, error=c.get("error"), simulated=True)
        return ModelOutput(text=c if isinstance(c, str) else json.dumps(c), simulated=True)


class OpenAIProvider:
    """Minimal HTTP client (stdlib only) for Chat Completions or Responses."""
    name = "openai"

    def __init__(self, api_key: str, api: str = "chat", timeout: int = 120, base: str | None = None):
        base = base or os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE
        self.key, self.api, self.timeout, self.base = api_key, api, timeout, base.rstrip("/")

    def _post(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(
            f"{self.base}{path}", data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")[:500]
                if e.code in (429, 500, 502, 503) and attempt < 2:
                    time.sleep(2 ** attempt * 2)
                    continue
                raise RuntimeError(f"HTTP {e.code}: {detail}") from None
        raise RuntimeError("unreachable")

    def build_request(self, case: dict, model: str, role: str, suite: dict) -> tuple[str, dict]:
        params = {**((suite.get("model_params") or {}).get(role) or {}), **((case.get("model_params") or {}).get(role) or {})}
        system = case.get("system", suite.get("system"))
        strict = case.get("strict", True)
        max_out = case.get("max_output_tokens", suite.get("max_output_tokens"))
        if self.api == "responses":
            # Chat-style reasoning_effort -> Responses `reasoning.effort`
            if "reasoning_effort" in params:
                params = dict(params)
                params["reasoning"] = {**params.get("reasoning", {}), "effort": params.pop("reasoning_effort")}
            if "max_completion_tokens" in params or "max_tokens" in params:
                params = dict(params)
                params.setdefault("max_output_tokens", params.pop("max_completion_tokens", None) or params.pop("max_tokens"))
            body: dict = {"model": model, "input": case["prompt"]}
            if max_out:
                body["max_output_tokens"] = int(max_out)
            if system:
                body["instructions"] = system
            if case["type"] == "structured":
                body["text"] = {"format": {"type": "json_schema", "name": case.get("schema_name", "output"),
                                           "schema": case["schema"], "strict": strict}}
            if case["type"] == "tool_call":
                body["tools"] = [{"type": "function", "name": t["name"], "description": t.get("description", ""),
                                  "parameters": t.get("parameters", {"type": "object", "properties": {}})}
                                 for t in case["tools"]]
                if case.get("tool_choice"):
                    body["tool_choice"] = case["tool_choice"]
            body.update(params)
            return "/responses", body
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": case["prompt"]}]
        body = {"model": model, "messages": msgs}
        if max_out:
            # `max_tokens` is rejected by gpt-6-luna (live-tested 2026-10-15);
            # `max_completion_tokens` works on both the GPT-4 series and gpt-6-luna.
            body["max_completion_tokens"] = int(max_out)
        if case["type"] == "structured":
            body["response_format"] = {"type": "json_schema", "json_schema": {
                "name": case.get("schema_name", "output"), "schema": case["schema"], "strict": strict}}
        if case["type"] == "tool_call":
            body["tools"] = [{"type": "function", "function": {
                "name": t["name"], "description": t.get("description", ""),
                "parameters": t.get("parameters", {"type": "object", "properties": {}})}} for t in case["tools"]]
            if case.get("tool_choice"):
                body["tool_choice"] = case["tool_choice"]
        body.update(params)
        return "/chat/completions", body

    def run(self, case: dict, model: str, role: str, suite: dict) -> ModelOutput:
        path, body = self.build_request(case, model, role, suite)
        t0 = time.time()
        try:
            data = self._post(path, body)
        except Exception as e:  # noqa: BLE001 - report every failure as a result
            return ModelOutput(error=str(e), latency_ms=int((time.time() - t0) * 1000))
        ms = int((time.time() - t0) * 1000)
        return self.parse(data, ms)

    def parse(self, data: dict, ms: int | None = None) -> ModelOutput:
        out = ModelOutput(latency_ms=ms, usage=data.get("usage"), resolved_model=data.get("model"))
        if self.api == "responses":
            if data.get("status") == "incomplete":
                out.truncated = True
            texts = []
            for item in data.get("output", []):
                if item.get("type") == "message":
                    texts += [c.get("text", "") for c in item.get("content", []) if c.get("type") == "output_text"]
                elif item.get("type") == "function_call":
                    out.tool_calls.append(ToolCall(item.get("name"), _maybe_json(item.get("arguments"))))
            out.text = "".join(texts) or None
            return out
        choice = (data.get("choices") or [{}])[0]
        if choice.get("finish_reason") == "length":
            out.truncated = True
        msg = choice.get("message", {})
        out.text = msg.get("content")
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            out.tool_calls.append(ToolCall(fn.get("name"), _maybe_json(fn.get("arguments"))))
        if msg.get("refusal"):
            out.error = f"refusal: {msg['refusal']}"
        return out


def _maybe_json(s: Any) -> Any:
    if isinstance(s, str):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return s
    return s


# ---------------------------------------------------------------- comparison
def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def similarity(a: str | None, b: str | None) -> float:
    if not a and not b:
        return 1.0
    return round(difflib.SequenceMatcher(None, _norm(a or ""), _norm(b or "")).ratio(), 3)


def _validate(instance: Any, schema: dict) -> list[str]:
    v = jsonschema.Draft202012Validator(schema)
    return [f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}" for e in v.iter_errors(instance)][:10]


def diff_values(a: Any, b: Any, path: str = "") -> list[dict]:
    """Field-level differences between two JSON-like values."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            p = f"{path}.{k}" if path else k
            if k not in a:
                out.append({"path": p, "change": "added", "new": b[k]})
            elif k not in b:
                out.append({"path": p, "change": "removed", "old": a[k]})
            else:
                out += diff_values(a[k], b[k], p)
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff_values(x, y, f"{path}[{i}]")
        return out
    return [] if a == b else [{"path": path or "(root)", "change": "changed", "old": a, "new": b}]


def _side_structured(o: ModelOutput, schema: dict) -> dict:
    if o.error:
        return {"ok": False, "errors": [o.error], "value": None}
    try:
        val = json.loads(o.text or "")
    except json.JSONDecodeError as e:
        return {"ok": False, "errors": [f"not valid JSON: {e}"], "value": None}
    errs = _validate(val, schema)
    return {"ok": not errs, "errors": errs, "value": val}


def _side_tools(o: ModelOutput, case: dict) -> dict:
    if o.error:
        return {"ok": False, "errors": [o.error], "calls": []}
    tools = {t["name"]: t for t in case["tools"]}
    errs = []
    if not o.tool_calls:
        errs.append("no tool call made")
    for tc in o.tool_calls:
        if tc.name not in tools:
            errs.append(f"unknown tool '{tc.name}'")
            continue
        if not isinstance(tc.arguments, dict):
            errs.append(f"{tc.name}: arguments are not a JSON object")
            continue
        errs += [f"{tc.name}: {e}" for e in _validate(tc.arguments, tools[tc.name].get("parameters", {}))]
    exp = case.get("expect") or {}
    names = [tc.name for tc in o.tool_calls]
    if exp.get("tool") and exp["tool"] not in names:
        errs.append(f"expected tool '{exp['tool']}', got {names or 'none'}")
    if exp.get("args") and o.tool_calls:
        args = o.tool_calls[0].arguments if isinstance(o.tool_calls[0].arguments, dict) else {}
        for k, v in exp["args"].items():
            if args.get(k) != v:
                errs.append(f"expected arg {k}={v!r}, got {args.get(k)!r}")
    return {"ok": not errs, "errors": errs, "calls": [asdict(tc) for tc in o.tool_calls]}


def compare(case: dict, old: ModelOutput, new: ModelOutput) -> CaseResult:
    t = case["type"]
    notes: list[str] = []
    checks: dict = {}
    thr = float(case.get("min_similarity", 0.6 if t == "text" else 0.85))
    if t == "structured":
        so, sn = _side_structured(old, case["schema"]), _side_structured(new, case["schema"])
        checks["schema_valid"] = {"old": so["ok"], "new": sn["ok"]}
        checks["schema_errors"] = {"old": so["errors"], "new": sn["errors"]}
        if so["value"] is not None and sn["value"] is not None:
            ignore = set(case.get("ignore_fields") or [])
            all_diffs = diff_values(so["value"], sn["value"])
            checks["field_diff"] = [d for d in all_diffs if d["path"].split("[")[0].split(".")[0] not in ignore]
            if ignore:
                checks["ignored_fields"] = sorted(ignore)
            def _strip(v):
                return {k: x for k, x in v.items() if k not in ignore} if isinstance(v, dict) else v
            checks["similarity"] = similarity(json.dumps(_strip(so["value"]), sort_keys=True),
                                              json.dumps(_strip(sn["value"]), sort_keys=True))
        old_ok, new_ok = so["ok"], sn["ok"]
        drift = bool(checks.get("field_diff"))
    elif t == "tool_call":
        so, sn = _side_tools(old, case), _side_tools(new, case)
        on, nn = [c["name"] for c in so["calls"]], [c["name"] for c in sn["calls"]]
        checks["tool_names"] = {"old": on, "new": nn, "match": on == nn}
        checks["errors"] = {"old": so["errors"], "new": sn["errors"]}
        arg_diffs = []
        for i, (a, b) in enumerate(zip(so["calls"], sn["calls"])):
            if a["name"] == b["name"]:
                d = diff_values(a["arguments"], b["arguments"])
                if d:
                    arg_diffs.append({"call": i, "tool": a["name"], "diff": d})
        checks["argument_diff"] = arg_diffs
        old_ok, new_ok = so["ok"], sn["ok"]
        drift = not checks["tool_names"]["match"] or bool(arg_diffs)
    else:
        sim = similarity(old.text, new.text)
        checks["similarity"] = sim
        must = case.get("must_include") or []
        missing = [m for m in must if m.lower() not in (new.text or "").lower()]
        checks["missing_phrases"] = missing
        old_ok = not old.error
        new_ok = not new.error and not missing
        drift = sim < thr
        if new.error:
            checks["errors"] = {"new": [new.error]}
    if "similarity" in checks:
        checks["similarity_threshold"] = thr
    if new.error:
        status = "error"
    elif not new_ok:
        status = "fail"
        if not old_ok:
            notes.append("Old model also failed this case - the test or schema may need fixing.")
    elif not old_ok:
        status = "improved"
    elif drift:
        status = "drift"
    else:
        status = "pass"
    for side, o in (("old", old), ("new", new)):
        if o.truncated:
            notes.append(f"{side} model output was cut off by the output-token limit.")
    if old.simulated or new.simulated:
        notes.append("Simulated (dry-run) output - not a real model response.")
    if t != "text" and checks.get("similarity") is not None and checks["similarity"] < thr:
        notes.append(f"Output similarity {checks['similarity']} below {thr}.")
    return CaseResult(case["id"], t, status, _out(old), _out(new), checks, notes)


def _out(o: ModelOutput) -> dict:
    d = asdict(o)
    return {k: v for k, v in d.items() if v not in (None, [], False) or k == "simulated"}


# ---------------------------------------------------------------- runner
def run_suite(suite: dict, provider, old_model: str | None = None, new_model: str | None = None) -> dict:
    models = suite.get("models", {})
    old_m = old_model or models.get("old")
    new_m = new_model or models.get("new")
    if not old_m or not new_m:
        raise ValueError("Need old and new models (suite 'models:' or --old/--new)")
    results = []
    for case in suite["cases"]:
        if case.get("skip"):
            continue
        cm = case.get("models") or {}           # per-case override, e.g. a fine-tune vs the new base model
        o = provider.run(case, cm.get("old", old_m), "old", suite)
        n = provider.run(case, cm.get("new", new_m), "new", suite)
        results.append(compare(case, o, n))
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    usage = usage_and_cost(results, suite.get("pricing") or {}, old_m, new_m)
    return {
        "usage": usage,
        "suite": suite.get("name", "unnamed"),
        "api": suite.get("api", "chat"),
        "mode": provider.name,
        "old_model": old_m, "new_model": new_m,
        "run_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "summary": counts,
        "cases": [asdict(r) for r in results],
    }


def _tokens(u: dict | None) -> tuple[int, int]:
    if not u:
        return 0, 0
    return (int(u.get("prompt_tokens", u.get("input_tokens", 0)) or 0),
            int(u.get("completion_tokens", u.get("output_tokens", 0)) or 0))


def usage_and_cost(results: list[CaseResult], pricing: dict, old_m: str, new_m: str) -> dict:
    """Token totals per side and, if the suite gives prices (USD per 1M tokens), an estimated cost."""
    out = {}
    for side, model in (("old", old_m), ("new", new_m)):
        tin = tout = 0
        for r in results:
            i, o = _tokens(getattr(r, side).get("usage"))
            tin, tout = tin + i, tout + o
        rec = {"model": model, "input_tokens": tin, "output_tokens": tout}
        price = pricing.get(model)
        if price:
            rec["est_cost_usd"] = round(tin / 1e6 * price["input"] + tout / 1e6 * price["output"], 6)
        out[side] = rec
    if all("est_cost_usd" in out[s] for s in ("old", "new")):
        out["total_est_cost_usd"] = round(out["old"]["est_cost_usd"] + out["new"]["est_cost_usd"], 6)
    return out


# Provider adapters the eval can call (provider-specific by design; the scanner/report are not).
ADAPTERS = {"openai"}
# Pack endpoint signal ids -> the request shape each adapter speaks.
ENDPOINT_API = {"openai": {"chat_completions": "chat", "responses_api": "responses"}}
# Arguments the adapter builds itself from the case (prompt, schema, tools); everything else a
# fixed call passes (token limits, sampling, reasoning) is replayed verbatim by `fix --verify`.
REQUEST_CONTENT_PARAMS = {"messages", "input", "instructions", "tools", "tool_choice", "functions", "function_call",
                          "response_format", "text", "text_format", "stream", "stream_options", "metadata", "store",
                          "user", "previous_response_id", "conversation", "prompt", "background", "include",
                          "extra_headers", "extra_body", "timeout", "parallel_tool_calls"}
TOOL_PARAMS = {"tools", "functions"}
TOKEN_LIMIT_PARAMS = {"max_tokens", "max_completion_tokens", "max_output_tokens"}
TOKEN_CAP_PARAM = {"chat": "max_completion_tokens", "responses": "max_output_tokens"}


def make_provider(suite: dict, dry_run: bool):
    key = os.environ.get("OPENAI_API_KEY")
    if dry_run or not key:
        return MockProvider(), (None if dry_run else "OPENAI_API_KEY not set - running in mock (dry-run) mode.")
    return OpenAIProvider(key, suite.get("api", "chat")), None


STATUS_ICON = {"pass": "PASS", "drift": "DRIFT", "fail": "FAIL", "improved": "IMPROVED", "error": "ERROR"}


def to_markdown(res: dict) -> str:
    out = [f"# Regression eval: {res['suite']}", "",
           f"- Old model: `{res['old_model']}`  ->  New model: `{res['new_model']}`",
           f"- API: {res['api']} | Mode: **{res['mode']}** | Run: {res['run_at']}"]
    if res["mode"] == "mock":
        out.append("- **Dry run: outputs are simulated, not real model responses.**")
    u = res.get("usage") or {}
    if res["mode"] != "mock" and u:
        for side in ("old", "new"):
            r = u.get(side, {})
            cost = f", est. ${r['est_cost_usd']:.4f}" if "est_cost_usd" in r else ""
            out.append(f"- {side}: `{r.get('model')}` {r.get('input_tokens', 0)} in / {r.get('output_tokens', 0)} out tokens{cost}")
    out += ["", "| Status | Count |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(res["summary"].items())] + [""]
    out += ["| Case | Type | Status | Key checks |", "|---|---|---|---|"]
    for c in res["cases"]:
        out.append(f"| `{c['id']}` | {c['type']} | **{STATUS_ICON.get(c['status'], c['status'])}** | {_key_checks(c)} |")
    out.append("")
    for c in res["cases"]:
        if c["status"] == "pass":
            continue
        out += [f"## {c['id']} ({c['status']})", "", "```json", json.dumps(c["checks"], indent=2, default=str)[:4000], "```", ""]
    return "\n".join(out)


def _key_checks(c: dict) -> str:
    ch = c["checks"]
    bits = []
    if "schema_valid" in ch:
        bits.append(f"schema valid old={ch['schema_valid']['old']} new={ch['schema_valid']['new']}")
    if "tool_names" in ch:
        bits.append(f"tools {ch['tool_names']['old']} -> {ch['tool_names']['new']}")
    if ch.get("argument_diff"):
        n = sum(len(d["diff"]) for d in ch["argument_diff"])
        bits.append(f"{n} argument difference(s)")
    if ch.get("field_diff"):
        bits.append(f"{len(ch['field_diff'])} field difference(s)")
    if "similarity" in ch:
        bits.append(f"similarity {ch['similarity']}")
    if ch.get("missing_phrases"):
        bits.append(f"missing {ch['missing_phrases']}")
    return "; ".join(bits).replace("|", "/")


def write(res: dict, out_dir: str | Path) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    from .scanner import mark_output
    mark_output(out)
    j, m = out / "eval.json", out / "eval.md"
    j.write_text(json.dumps(res, indent=2, default=str))
    m.write_text(to_markdown(res))
    return j, m
