"""Moonshot API pack (checked 2 Nov 2026): K2.6 and K2.7 Code to K3.1 Pro.

Flag only. Dates and behaviour notes come from platform.kimi.ai. Already-dead IDs are not rows.
"""
import datetime as dt
import json

from conftest import ROOT
from migration_kit.fixer import plan_fixes
from migration_kit.packs import load_packs, validate
from migration_kit.scanner import model_independent_rules, scan
from migration_kit.swapper import mapping_from_packs
from migration_kit.swapper import plan as swap_plan

TODAY = dt.date(2026, 11, 2)
SHUTDOWN = "2026-12-31"
THINKING = "kimi-k3-thinking-always-on"
SAMPLING = "kimi-k3-sampling-fixed"
VISION = "kimi-k3-vision-no-public-url"
EFFORT = "kimi-k3-reasoning-effort"

ROWS = {
    "kimi-k2.6": "kimi-k3.1-pro",
    "kimi-k2.7-code": "kimi-k3.1-pro",
    "kimi-k2.7-code-highspeed": "kimi-k3.1-pro",
}

PARKED = (
    "kimi-k2.5",
    "moonshot-v1-8k",
    "moonshot-v1-32k",
    "moonshot-v1-128k",
    "moonshot-v1-auto",
    "moonshot-v1-8k-vision-preview",
    "kimi-k2-0905-preview",
    "kimi-k2-0711-preview",
    "kimi-k2-turbo-preview",
    "kimi-k2-thinking",
    "kimi-k2-thinking-turbo",
    "kimi-latest",
    "kimi-thinking-preview",
)


def _pack():
    return json.loads((ROOT / "migration_kit" / "pack_data" / "moonshot.json").read_text())


def _model(mid):
    return next(m for m in _pack()["models"] if m["id"] == mid)


def _findings(root, model=None):
    found = scan(root, packs=load_packs(offline=True), today=TODAY).findings
    if model is None:
        return found
    return [f for f in found if f.model == model]


def test_pack_is_loadable_and_listed():
    data = _pack()
    validate(data)
    assert data["provider"] == "moonshot"
    assert data["name"] == "Moonshot API (Kimi)"
    assert data["version"] == "2026.11.02.1" and data["updated"] == "2026-11-02"
    assert data["status"] == "stable"
    assert [m["id"] for m in data["models"]] == [
        "kimi-k2.6",
        "kimi-k2.7-code",
        "kimi-k2.7-code-highspeed",
    ]
    assert "moonshot" in load_packs(offline=True).info()[0]["provider"] or any(
        p["provider"] == "moonshot" for p in load_packs(offline=True).info()
    )
    assert all("deepseek" not in m["id"] for m in data["models"])
    assert all("deepseek" not in (m.get("replacement") or "") for m in data["models"])
    assert all(s["checked"] == "2026-11-02" and s["url"].startswith("https://platform.kimi.ai/") for s in data["sources"])
    ids = {s["id"] for s in data["sources"]}
    for row in data["models"] + data["migrations"]:
        assert row["source"] in ids
    urls = {s["url"] for s in data["sources"]}
    assert "https://platform.kimi.ai/docs/models" in urls
    assert "https://platform.kimi.ai/docs/guide/kimi-k3-1-pro-quickstart.md" in urls
    assert "https://platform.kimi.ai/docs/guide/use-reasoning-effort.md" in urls
    assert model_independent_rules(load_packs(offline=True).get("moonshot")) == []
    notes = " ".join(data["notes"])
    for parked in ("kimi-k2.5", "moonshot-v1", "kimi-latest", "kimi-thinking-preview", "kimi-k2-thinking"):
        assert parked in notes
        assert parked not in {m["id"] for m in data["models"]}
    assert "31 Dec 2026" in notes and "exact day" in notes
    assert "kimi-k2.6-highspeed is not listed" in notes


def test_each_id_shutdown_and_replacement():
    for mid, repl in ROWS.items():
        row = _model(mid)
        assert row["shutdown"] == SHUTDOWN
        assert row["replacement"] == repl
        assert row["map_automatically"] is False
        assert row["confidence"] == "confirmed"
        assert row["migration"] == "kimi-k3-1-pro-2026-12-31"
        assert "31 Oct 2026" in row["note"] and "31 Dec 2026" in row["note"]
    assert _model("kimi-k2.7-code-highspeed")["kind"] == "alias"
    assert _model("kimi-k2.7-code-highspeed")["alias_of"] == "kimi-k2.7-code"
    mig = _pack()["migrations"][0]
    assert mig["announced"] == "2026-10-31" and mig["headline"] is True
    assert mig["shutdown"] == SHUTDOWN and mig["replacement"] == "kimi-k3.1-pro"


def test_k3_price_and_behaviour_from_docs():
    facts = _pack()["replacement_facts"]["kimi-k3.1-pro"]
    assert facts["aliases"] == ["kimi-k3.1-pro-highspeed"]
    assert facts["context_window"] == 1048576
    assert facts["thinking"] == "always-on"
    assert facts["reasoning_effort"] == ["low", "high", "max"]
    assert facts["reasoning_effort_default"] == "max"
    assert facts["sampling_fixed"] == {
        "temperature": 1.0,
        "top_p": 0.95,
        "n": 1,
        "presence_penalty": 0,
        "frequency_penalty": 0,
    }
    assert facts["price_usd_per_1m"] == {
        "input": 2.0,
        "cached_input": 0.2,
        "output": 10.0,
        "cache_write_5m": 2.0,
        "cache_write_1h": 4.0,
    }
    k26 = _model("kimi-k2.6")["note"]
    k27 = _model("kimi-k2.7-code")["note"]
    fast = _model("kimi-k2.7-code-highspeed")["note"]
    assert "$0.95 input / $0.16 cached input / $4.00 output" in k26
    assert "$0.95 input / $0.19 cached input / $4.00 output" in k27
    assert "$1.90 input / $0.38 cached input / $8.00 output" in fast
    assert "262,144" in k26 and "1,048,576" in k26
    assert "cannot be turned off" in k26
    assert "public image URL" in k26
    assert "kimi-k3.1-pro-highspeed" in facts["note"]
    assert "$4.00" in facts["note"] and "$20.00" in facts["note"]


def test_scan_flags_and_does_not_swap_or_fix(tmp_path):
    (tmp_path / "chat.py").write_text(
        "import os\n"
        "from openai import OpenAI\n"
        "client = OpenAI(api_key=os.environ['MOONSHOT_API_KEY'], base_url='https://api.moonshot.ai/v1')\n"
        "client.chat.completions.create(model='kimi-k2.6', messages=[], "
        "extra_body={'thinking': {'type': 'disabled'}}, temperature=0.6, reasoning_effort='medium')\n"
    )
    (tmp_path / "code.py").write_text(
        "client.chat.completions.create(model='kimi-k2.7-code', messages=[], top_p=0.95)\n"
    )
    (tmp_path / "vision.py").write_text(
        "client.chat.completions.create(model='kimi-k2.7-code-highspeed', messages=[\n"
        "    {'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'https://example.com/a.png'}}]}\n"
        "])\n"
    )
    (tmp_path / "plain.py").write_text(
        "client.chat.completions.create(model='kimi-k2.6', messages=[], reasoning_effort='high')\n"
    )
    by = {}
    for f in _findings(tmp_path):
        by.setdefault((f.file, f.model), f)
    k26 = by[("chat.py", "kimi-k2.6")]
    k27 = by[("code.py", "kimi-k2.7-code")]
    fast = by[("vision.py", "kimi-k2.7-code-highspeed")]
    k26_ok = by[("plain.py", "kimi-k2.6")]
    assert k26.provider == "moonshot" and k26.shutdown == SHUTDOWN
    assert k26.suggested == "kimi-k3.1-pro"
    assert k26.category == "in_scope" and k26.risk == "medium"
    assert not k26.auto_swap and k26.no_swap_reason == "flag_only"
    assert THINKING in k26.rules and SAMPLING in k26.rules and EFFORT in k26.rules
    assert VISION not in k26.rules
    assert THINKING not in k27.rules and SAMPLING in k27.rules and EFFORT not in k27.rules
    assert VISION in fast.rules and THINKING not in fast.rules
    assert EFFORT not in k26_ok.rules and SAMPLING not in k26_ok.rules
    assert fast.suggested == "kimi-k3.1-pro"
    packs = load_packs(offline=True)
    mapping = mapping_from_packs(packs)
    assert not any(mid in mapping.replacements for mid in ROWS)
    assert set(ROWS) <= set(mapping.flag_only)
    sw = swap_plan(tmp_path, mapping, packs)
    assert "chat.py" not in sw.new_contents and "code.py" not in sw.new_contents
    assert "vision.py" not in sw.new_contents and "plain.py" not in sw.new_contents
    assert "kimi-k3.1-pro" not in (tmp_path / "chat.py").read_text()
    fixed = plan_fixes(tmp_path, packs)
    assert "kimi-k3.1-pro" not in fixed.new_contents.get("chat.py", (tmp_path / "chat.py").read_text())
    assert "temperature=0.6" in (tmp_path / "chat.py").read_text()
    assert fixed.new_contents.get("chat.py", (tmp_path / "chat.py").read_text()) == (tmp_path / "chat.py").read_text()


def test_near_misses_and_parked_ids(tmp_path):
    lines = [
        "skip = 'kimi-k2.60'\n",
        "skip2 = 'kimi-k2.7-coder'\n",
        "skip3 = 'kimi-k2.6-highspeed'\n",
        "current = 'kimi-k3'\n",
        "new = 'kimi-k3.1-pro'\n",
        "fast_new = 'kimi-k3.1-pro-highspeed'\n",
        "keep = 'kimi-k2.6'\n",
    ]
    lines += [f"old = '{mid}'\n" for mid in PARKED]
    (tmp_path / "app.py").write_text("".join(lines))
    found = {f.model for f in _findings(tmp_path) if f.provider == "moonshot"}
    assert found == {"kimi-k2.6"}


def test_urgent_window_and_docs(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "app.py").write_text("model = 'kimi-k2.7-code'\n")
    early = scan(tmp_path / "code", packs=load_packs(offline=True), today=TODAY).findings
    assert len(early) == 1 and early[0].risk == "medium" and early[0].provider == "moonshot"
    late = scan(tmp_path / "code", packs=load_packs(offline=True), today=dt.date(2026, 12, 15)).findings
    assert len(late) == 1 and late[0].risk == "high"
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "notes.md").write_text("Use kimi-k2.6 in this guide.\n")
    docs = scan(tmp_path / "docs", packs=load_packs(offline=True), today=dt.date(2026, 12, 15)).findings
    assert len(docs) == 1 and docs[0].kind == "doc" and docs[0].risk == "low"


def test_other_packs_are_unchanged():
    packs = load_packs(offline=True)
    for prov in ("openai", "anthropic", "google", "mistral", "azure-foundry"):
        data = json.dumps(packs.get(prov).data)
        for mid in ROWS:
            assert mid not in data
        for parked in ("kimi-k2.5", "moonshot-v1-8k", "kimi-latest"):
            assert parked not in data
