"""Live parameter probe for the 23 Oct 2026 replacements.

Checks gpt-5.6-luna, gpt-5.6-sol and gpt-5.6-terra on Chat Completions for the
rules the fixer already applies to gpt-6-luna, and only those:

- max_tokens and max_completion_tokens, at reasoning_effort none and at the
  default (omitted) effort
- temperature, top_p and logprobs at each reasoning_effort the model pages
  list (none, low, medium, high, xhigh, max), plus the omitted default
- temperature=1 at none and at the default, the value gpt-6-luna still allows
  when other temperatures are rejected
- reasoning_effort none on its own
- function tools at each listed effort and at the omitted default

The effort list is taken from the model pages (checked 2026-10-16):
https://developers.openai.com/api/docs/models/gpt-5.6-luna
https://developers.openai.com/api/docs/models/gpt-5.6-sol
https://developers.openai.com/api/docs/models/gpt-5.6-terra

Stdlib only. Reads OPENAI_API_KEY from the environment and never prints it.
Writes probes/probe_56-result.json (a JSON array, same shape as
probes/params-result.json) and prints one JSON object per probe on stdout.

Exit 2 when OPENAI_API_KEY is missing. Exit 1 when a call fails before an
HTTP status (network error). HTTP 400 is a result, not a script failure.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

MODELS = ("gpt-5.6-luna", "gpt-5.6-sol", "gpt-5.6-terra")
# Documented on each model page. "medium" is the documented default; None means omit the field.
EFFORTS = ("none", "low", "medium", "high", "xhigh", "max")
HERE = Path(__file__).resolve().parent
OUT = HERE / "probe_56-result.json"
BASE = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")

MSG = [{"role": "user", "content": "Reply with the single word OK."}]
TOOLS = [{
    "type": "function",
    "function": {
        "name": "book_table",
        "description": "Book a restaurant table",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string"},
                "time": {"type": "string"},
                "party_size": {"type": "integer"},
            },
            "required": ["date", "time", "party_size"],
        },
    },
}]
TMSG = [{"role": "user", "content": "Book a table for 4 on 2026-11-02 at 19:30."}]


def call(body: dict, timeout: int = 90) -> tuple[int, dict]:
    req = urllib.request.Request(
        BASE + "/chat/completions",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": "Bearer " + os.environ["OPENAI_API_KEY"],
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw[:500]}


def with_effort(body: dict, effort: str | None) -> dict:
    if effort is not None:
        body["reasoning_effort"] = effort
    return body


def probes_for(model: str) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for effort, label in (("none", "none"), (None, "default")):
        out.append((
            f"{model} chat max_tokens=16 effort={label}",
            with_effort({"model": model, "messages": MSG, "max_tokens": 16}, effort),
        ))
        out.append((
            f"{model} chat max_completion_tokens=16 effort={label}",
            with_effort({"model": model, "messages": MSG, "max_completion_tokens": 16}, effort),
        ))
        out.append((
            f"{model} chat temperature=1 effort={label}",
            with_effort({"model": model, "messages": MSG, "temperature": 1, "max_completion_tokens": 16}, effort),
        ))
    # Dedicated reasoning_effort=none call, with no other sampling parameters.
    out.append((
        f"{model} chat reasoning_effort=none",
        {"model": model, "messages": MSG, "reasoning_effort": "none", "max_completion_tokens": 16},
    ))
    for effort in EFFORTS:
        cap = {"max_completion_tokens": 16}
        out.append((
            f"{model} chat temperature=0.2 effort={effort}",
            {"model": model, "messages": MSG, "temperature": 0.2, "reasoning_effort": effort, **cap},
        ))
        out.append((
            f"{model} chat top_p=0.9 effort={effort}",
            {"model": model, "messages": MSG, "top_p": 0.9, "reasoning_effort": effort, **cap},
        ))
        out.append((
            f"{model} chat logprobs effort={effort}",
            {"model": model, "messages": MSG, "logprobs": True, "top_logprobs": 2,
             "reasoning_effort": effort, **cap},
        ))
    for effort in (None, *EFFORTS):
        label = "default" if effort is None else effort
        body = {"model": model, "messages": TMSG, "tools": TOOLS, "max_completion_tokens": 200}
        out.append((
            f"{model} chat tools effort={label}",
            with_effort(body, effort),
        ))
    return out


def record(name: str, body: dict, status: int, payload: dict) -> dict:
    rec = {
        "probe": name,
        "status": status,
        "request_model": body["model"],
        "reasoning_effort": body.get("reasoning_effort"),
        "sent": sorted(k for k in body if k not in ("model", "messages")),
    }
    if status == 200:
        rec["resolved_model"] = payload.get("model")
        rec["usage"] = payload.get("usage")
        choice = (payload.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        rec["finish_reason"] = choice.get("finish_reason")
        rec["content"] = (message.get("content") or "")[:80]
        rec["tool_calls"] = [tc.get("function", {}).get("name") for tc in message.get("tool_calls") or []]
        rec["logprobs_returned"] = bool(choice.get("logprobs"))
    else:
        err = payload.get("error", payload)
        if isinstance(err, dict):
            rec["error"] = {k: err.get(k) for k in ("message", "type", "param", "code")}
        else:
            rec["error"] = err
    return rec


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set", file=sys.stderr)
        return 2
    results = []
    try:
        for model in MODELS:
            for name, body in probes_for(model):
                status, payload = call(body)
                rec = record(name, body, status, payload)
                results.append(rec)
                print(json.dumps(rec), flush=True)
    except urllib.error.URLError as exc:
        print(json.dumps({"probe": "transport", "error": str(exc.reason)}), file=sys.stderr)
        if results:
            OUT.write_text(json.dumps(results, indent=1) + "\n")
        return 1
    OUT.write_text(json.dumps(results, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
