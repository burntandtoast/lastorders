import json, sys
sys.path.insert(0, "probes")
from oai import call

MSG = [{"role": "user", "content": "Reply with the single word OK."}]
TOOLS = [{"type": "function", "function": {"name": "book_table", "description": "Book a restaurant table",
          "parameters": {"type": "object", "properties": {"date": {"type": "string"}, "time": {"type": "string"},
                         "party_size": {"type": "integer"}}, "required": ["date", "time", "party_size"]}}}]
TMSG = [{"role": "user", "content": "Book a table for 4 on 2026-11-02 at 19:30."}]
L = "gpt-6-luna"
probes = [
 ("chat baseline effort=none max_completion_tokens=16", "/chat/completions", {"model": L, "messages": MSG, "reasoning_effort": "none", "max_completion_tokens": 16}),
 ("chat baseline default effort max_completion_tokens=64", "/chat/completions", {"model": L, "messages": MSG, "max_completion_tokens": 64}),
 ("chat max_tokens=16 effort=none", "/chat/completions", {"model": L, "messages": MSG, "reasoning_effort": "none", "max_tokens": 16}),
 ("chat max_tokens=64 default effort", "/chat/completions", {"model": L, "messages": MSG, "max_tokens": 64}),
 ("chat temperature=0.2 effort=none", "/chat/completions", {"model": L, "messages": MSG, "reasoning_effort": "none", "temperature": 0.2, "max_completion_tokens": 16}),
 ("chat temperature=0.2 default effort", "/chat/completions", {"model": L, "messages": MSG, "temperature": 0.2, "max_completion_tokens": 64}),
 ("chat temperature=1 default effort", "/chat/completions", {"model": L, "messages": MSG, "temperature": 1, "max_completion_tokens": 64}),
 ("chat top_p=0.9 effort=none", "/chat/completions", {"model": L, "messages": MSG, "reasoning_effort": "none", "top_p": 0.9, "max_completion_tokens": 16}),
 ("chat top_p=0.9 default effort", "/chat/completions", {"model": L, "messages": MSG, "top_p": 0.9, "max_completion_tokens": 64}),
 ("chat logprobs effort=none", "/chat/completions", {"model": L, "messages": MSG, "reasoning_effort": "none", "logprobs": True, "top_logprobs": 2, "max_completion_tokens": 16}),
 ("chat logprobs default effort", "/chat/completions", {"model": L, "messages": MSG, "logprobs": True, "max_completion_tokens": 64}),
 ("chat tools, no reasoning_effort", "/chat/completions", {"model": L, "messages": TMSG, "tools": TOOLS, "max_completion_tokens": 200}),
 ("chat tools, reasoning_effort=low", "/chat/completions", {"model": L, "messages": TMSG, "tools": TOOLS, "reasoning_effort": "low", "max_completion_tokens": 200}),
 ("chat tools, reasoning_effort=none", "/chat/completions", {"model": L, "messages": TMSG, "tools": TOOLS, "reasoning_effort": "none", "max_completion_tokens": 100}),
 ("responses temperature=0.2 default effort", "/responses", {"model": L, "input": "Reply with the single word OK.", "temperature": 0.2, "max_output_tokens": 64}),
 ("responses tools default effort", "/responses", {"model": L, "input": "Book a table for 4 on 2026-11-02 at 19:30.", "max_output_tokens": 200,
   "tools": [{"type": "function", **TOOLS[0]["function"]}]}),
]
for alias in ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"]:
    probes.append((f"alias {alias} resolves", "/chat/completions", {"model": alias, "messages": MSG, "max_tokens": 5}))

results = []
for name, path, body in probes:
    st, r = call("POST", path, body)
    rec = {"probe": name, "status": st, "request_model": body["model"]}
    if st == 200:
        rec["resolved_model"] = r.get("model")
        rec["usage"] = r.get("usage")
        if path == "/chat/completions":
            ch = r["choices"][0]; m = ch["message"]
            rec["finish_reason"] = ch.get("finish_reason")
            rec["content"] = (m.get("content") or "")[:80]
            rec["tool_calls"] = [tc["function"]["name"] for tc in m.get("tool_calls") or []]
            rec["logprobs_returned"] = bool(ch.get("logprobs"))
        else:
            rec["output_types"] = [o.get("type") for o in r.get("output", [])]
            rec["status_field"] = r.get("status")
    else:
        e = r.get("error", r)
        rec["error"] = {k: e.get(k) for k in ("message", "type", "param", "code")} if isinstance(e, dict) else e
    results.append(rec)
    print(json.dumps(rec))
json.dump(results, open("probes/params-result.json", "w"), indent=1)
