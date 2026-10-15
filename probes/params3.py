"""Does the OLD model accept the params the fixer adds? (matters when the model id comes from an env var)."""
import json, sys
sys.path.insert(0, "probes")
from oai import call
IN = "Reply with the single word OK."
MSG = [{"role": "user", "content": IN}]
TOOLS = [{"type": "function", "function": {"name": "noop", "parameters": {"type": "object", "properties": {}}}}]
probes = [
 ("chat gpt-4o-2024-08-06 reasoning_effort=none", "/chat/completions", {"model": "gpt-4o-2024-08-06", "messages": MSG, "reasoning_effort": "none", "max_completion_tokens": 5}),
 ("chat gpt-4o-mini-2024-07-18 reasoning_effort=none + tools", "/chat/completions", {"model": "gpt-4o-mini-2024-07-18", "messages": MSG, "tools": TOOLS, "reasoning_effort": "none", "max_completion_tokens": 5}),
 ("chat gpt-4.1-2025-04-14 reasoning_effort=none", "/chat/completions", {"model": "gpt-4.1-2025-04-14", "messages": MSG, "reasoning_effort": "none", "max_completion_tokens": 5}),
 ("responses gpt-4.1-mini-2025-04-14 reasoning.effort=none", "/responses", {"model": "gpt-4.1-mini-2025-04-14", "input": IN, "reasoning": {"effort": "none"}, "max_output_tokens": 16}),
 ("chat luna effort=none + tools + max_completion_tokens", "/chat/completions", {"model": "gpt-6-luna", "messages": MSG, "tools": TOOLS, "reasoning_effort": "none", "max_completion_tokens": 16}),
]
res = []
for name, path, body in probes:
    st, r = call("POST", path, body)
    rec = {"probe": name, "status": st}
    if st == 200:
        rec["usage"] = r.get("usage")
    else:
        e = r.get("error", {}); rec["error"] = e.get("message"); rec["param"] = e.get("param")
    print(json.dumps({k: rec[k] for k in rec if k != "usage"})); res.append(rec)
json.dump(res, open("probes/params3-result.json", "w"), indent=1)
