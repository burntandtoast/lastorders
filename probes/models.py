import json, sys
sys.path.insert(0, "probes")
from oai import call

ids = ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4o-2024-08-06", "gpt-4o-2024-11-20",
       "gpt-4o-mini-2024-07-18", "gpt-4.1-2025-04-14", "gpt-4.1-mini-2025-04-14", "gpt-6-luna",
       "gpt-4.1-nano", "gpt-4o-2024-05-13"]
st, lst = call("GET", "/models")
print("list status", st)
data = {m["id"]: m for m in lst.get("data", [])} if st == 200 else {}
print("total models listed:", len(data))
out = {}
for i in ids:
    s, m = call("GET", f"/models/{i}")
    out[i] = {"retrieve_status": s, "in_list": i in data,
              "shutdown_date": (m.get("shutdown_date", "<field absent>") if s == 200 else None),
              "keys": sorted(m.keys()) if s == 200 else None,
              "error": (m.get("error", {}) or {}).get("message") if s != 200 else None}
print(json.dumps(out, indent=1))
json.dump({"list_status": st, "models": out,
           "listed_with_shutdown": {k: v.get("shutdown_date") for k, v in data.items() if v.get("shutdown_date")}},
          open("probes/models-result.json", "w"), indent=1)
