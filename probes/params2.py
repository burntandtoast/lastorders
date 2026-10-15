import json, sys
sys.path.insert(0, "probes")
from oai import call
L = "gpt-6-luna"; IN = "Reply with the single word OK."
MSG = [{"role": "user", "content": IN}]
probes = [
 ("responses effort=none temperature=0.2", "/responses", {"model": L, "input": IN, "reasoning": {"effort": "none"}, "temperature": 0.2, "max_output_tokens": 16}),
 ("responses effort=none top_p=0.9", "/responses", {"model": L, "input": IN, "reasoning": {"effort": "none"}, "top_p": 0.9, "max_output_tokens": 16}),
 ("responses default top_p=0.9", "/responses", {"model": L, "input": IN, "top_p": 0.9, "max_output_tokens": 64}),
 ("chat gpt-4o-2024-08-06 max_completion_tokens", "/chat/completions", {"model": "gpt-4o-2024-08-06", "messages": MSG, "max_completion_tokens": 5}),
 ("chat luna effort=low temperature=0.2", "/chat/completions", {"model": L, "messages": MSG, "reasoning_effort": "low", "temperature": 0.2, "max_completion_tokens": 64}),
]
res = []
for name, path, body in probes:
    st, r = call("POST", path, body)
    rec = {"probe": name, "status": st}
    if st == 200:
        rec["usage"] = r.get("usage")
    else:
        e = r.get("error", {}); rec["error"] = e.get("message"); rec["param"] = e.get("param")
    print(json.dumps(rec)); res.append(rec)
json.dump(res, open("probes/params2-result.json", "w"), indent=1)
