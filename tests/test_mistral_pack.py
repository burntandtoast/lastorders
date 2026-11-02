"""Mistral API pack (checked 2 Nov 2026): Medium 3.5 and Large 3 to Large 4, and the three Voxtral 2 to Voxtral 3 ID renames.

Flag only. Prices and behaviour notes come from Mistral's docs. DeepSeek is not a row.
"""
import datetime as dt
import json

from conftest import ROOT
from migration_kit.packs import load_packs, validate
from migration_kit.scanner import model_independent_rules, scan
from migration_kit.swapper import mapping_from_packs
from migration_kit.swapper import plan as swap_plan

TODAY = dt.date(2026, 11, 2)
SHUTDOWN = "2027-04-30"
REASONING = "mistral-large-4-reasoning-effort"
TIMESTAMPS = "voxtral-word-timestamps-removed"
SESSION = "voxtral-realtime-session-lock"

ROWS = {
    "mistral-medium-3-5": "mistral-large-4",
    "mistral-large-2512": "mistral-large-4",
    "voxtral-mini-tts-2603": "voxtral-mini-tts-3-0",
    "voxtral-mini-2602": "voxtral-mini-transcribe-3-0",
    "voxtral-mini-transcribe-realtime-2602": "voxtral-mini-transcribe-realtime-3-0",
}


def _pack():
    return json.loads((ROOT / "migration_kit" / "pack_data" / "mistral.json").read_text())


def _model(mid):
    return next(m for m in _pack()["models"] if m["id"] == mid)


def _write(tmp_path, text, name="app.py"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / name).write_text(text)
    return tmp_path


def _findings(root, model=None):
    found = scan(root, packs=load_packs(offline=True), today=TODAY).findings
    if model is None:
        return found
    return [f for f in found if f.model == model]


def test_pack_is_the_five_mistral_rows():
    data = _pack()
    validate(data)
    assert data["provider"] == "mistral"
    assert data["version"] == "2026.11.02.1" and data["updated"] == "2026-11-02"
    assert data["status"] == "stable"
    assert [m["id"] for m in data["models"]] == [
        "mistral-medium-3-5",
        "mistral-large-2512",
        "voxtral-mini-2602",
        "voxtral-mini-transcribe-realtime-2602",
        "voxtral-mini-tts-2603",
    ]
    assert all("deepseek" not in m["id"] for m in data["models"])
    assert all("deepseek" not in (m.get("replacement") or "") for m in data["models"])
    assert all(s["checked"] == "2026-11-02" and s["url"].startswith("https://docs.mistral.ai/") for s in data["sources"])
    ids = {s["id"] for s in data["sources"]}
    for row in data["models"] + data["migrations"]:
        assert row["source"] in ids
    assert model_independent_rules(load_packs(offline=True).get("mistral")) == []


def test_each_id_shutdown_and_replacement():
    for mid, repl in ROWS.items():
        row = _model(mid)
        assert row["shutdown"] == SHUTDOWN
        assert row["replacement"] == repl
        assert row["map_automatically"] is False
        assert row["confidence"] == "confirmed"
        assert "31 Oct 2026" in row["note"] and "30 Apr 2027" in row["note"]
    chat = _pack()["migrations"][0]
    assert chat["id"] == "mistral-large-4-2027-04-30"
    assert chat["announced"] == "2026-10-31" and chat["headline"] is True
    assert chat["replacement"] == "mistral-large-4"


def test_large_4_price_and_behaviour_from_docs():
    facts = _pack()["replacement_facts"]["mistral-large-4"]
    assert facts["aliases"] == ["mistral-large-4-0"]
    assert facts["price_usd_per_1m"] == {"input": 0.7, "cached_input": 0.07, "output": 2.1}
    assert facts["reasoning_effort"] == ["low", "medium", "high"]
    assert "none" in facts["reasoning_effort_rejected"]
    medium = _model("mistral-medium-3-5")["note"]
    large = _model("mistral-large-2512")["note"]
    assert "$1.50 input / $7.50 output" in medium
    assert "$0.50 input / $1.50 output" in large
    assert "costs more" in large
    for audio in ("voxtral-mini-transcribe-3-0", "voxtral-mini-transcribe-realtime-3-0", "voxtral-mini-tts-3-0"):
        assert facts_price(audio)["price_usd_per_1m"] is None
        assert facts_price(audio)["price"]["input"] > 0
        assert "null" in facts_price(audio)["note"] or "price_usd_per_1m is null" in facts_price(audio)["note"]


def facts_price(mid):
    return _pack()["replacement_facts"][mid]


def test_voxtral_prices_and_pinned_ids():
    assert facts_price("voxtral-mini-transcribe-3-0")["price"] == {"input": 0.0035, "unit": "usd_per_minute"}
    assert facts_price("voxtral-mini-transcribe-realtime-3-0")["price"]["input"] == 0.008
    assert facts_price("voxtral-mini-tts-3-0")["price"] == {"input": 13, "unit": "usd_per_million_characters"}
    assert "$0.003 to $0.0035" in _model("voxtral-mini-2602")["note"]
    assert "$0.006 to $0.008" in _model("voxtral-mini-transcribe-realtime-2602")["note"]
    assert "$16 to $13" in _model("voxtral-mini-tts-2603")["note"]
    assert "voxtral-mini-tts-latest" in _model("voxtral-mini-tts-2603")["note"]
    assert "mistral-large-4-0" in _model("mistral-medium-3-5")["note"]


def test_scan_flags_and_does_not_swap(tmp_path):
    (tmp_path / "chat.py").write_text(
        "from mistralai.client import Mistral\n"
        "client = Mistral(api_key='k')\n"
        "client.chat.complete(model='mistral-medium-3-5', messages=[], reasoning_effort='none')\n"
        "client.chat.complete(model='mistral-large-2512', messages=[])\n"
    )
    (tmp_path / "audio.py").write_text(
        "client.audio.transcriptions.complete(model='voxtral-mini-2602', file={}, timestamp_granularities=['word'])\n"
        "client.audio.speech.complete(model='voxtral-mini-tts-2603', input='hello')\n"
        "client.chat.complete(model='mistral-large-2512', messages=[], reasoning_effort='high')\n"
    )
    by = {}
    for f in _findings(tmp_path):
        by.setdefault((f.file, f.model), f)
    medium = by[("chat.py", "mistral-medium-3-5")]
    large_with_none = by[("chat.py", "mistral-large-2512")]
    large_ok = by[("audio.py", "mistral-large-2512")]
    transcribe = by[("audio.py", "voxtral-mini-2602")]
    tts = by[("audio.py", "voxtral-mini-tts-2603")]
    assert medium.provider == "mistral" and medium.shutdown == SHUTDOWN
    assert medium.suggested == "mistral-large-4"
    assert medium.category == "in_scope" and medium.risk == "medium"
    assert not medium.auto_swap and medium.no_swap_reason == "flag_only"
    # The bad reasoning_effort is file-level, so both Large 4 targets in chat.py carry the rule.
    assert REASONING in medium.rules and REASONING in large_with_none.rules
    assert REASONING not in large_ok.rules
    assert TIMESTAMPS in transcribe.rules and TIMESTAMPS not in tts.rules
    assert tts.suggested == "voxtral-mini-tts-3-0"
    packs = load_packs(offline=True)
    mapping = mapping_from_packs(packs)
    assert not any(mid in mapping.replacements for mid in ROWS)
    assert set(ROWS) <= set(mapping.flag_only)
    sw = swap_plan(tmp_path, mapping, packs)
    assert "chat.py" not in sw.new_contents and "audio.py" not in sw.new_contents
    assert "mistral-large-4" not in (tmp_path / "chat.py").read_text()
    assert "voxtral-mini-transcribe-3-0" not in (tmp_path / "audio.py").read_text()


def test_realtime_session_rule_and_near_misses(tmp_path):
    text = (
        "ws.session.update(model='voxtral-mini-transcribe-realtime-2602')\n"
        "other = 'voxtral-mini-2602'\n"
        "skip = 'mistral-medium-3-50'\n"
        "skip2 = 'mistral-large-25120'\n"
        "skip3 = 'voxtral-mini-26020'\n"
        "alias = 'mistral-large-latest'\n"
        "small = 'voxtral-small-2507'\n"
        "foundry = 'mistral-small-2503'\n"
        "new = 'mistral-large-4'\n"
    )
    root = _write(tmp_path, text)
    found = {f.model: f for f in _findings(root)}
    assert set(found) == {
        "voxtral-mini-transcribe-realtime-2602",
        "voxtral-mini-2602",
        "mistral-small-2503",
    }
    rt = found["voxtral-mini-transcribe-realtime-2602"]
    assert rt.provider == "mistral" and rt.suggested == "voxtral-mini-transcribe-realtime-3-0"
    assert SESSION in rt.rules
    assert TIMESTAMPS not in rt.rules
    assert found["mistral-small-2503"].provider == "azure-foundry"
    assert found["voxtral-mini-2602"].provider == "mistral"


def test_urgent_window_and_docs(tmp_path):
    code = _write(tmp_path / "code", "model = 'mistral-medium-3-5'\n")
    late = scan(code, packs=load_packs(offline=True), today=dt.date(2027, 4, 15)).findings
    assert len(late) == 1 and late[0].risk == "high" and late[0].provider == "mistral"
    docs_root = _write(tmp_path / "docs", "Use mistral-medium-3-5 in this guide.\n", name="notes.md")
    docs = scan(docs_root, packs=load_packs(offline=True), today=dt.date(2027, 4, 15)).findings
    assert len(docs) == 1 and docs[0].kind == "doc" and docs[0].risk == "low"


def test_openai_and_foundry_packs_are_not_mistral_rows():
    packs = load_packs(offline=True)
    for prov in ("openai", "azure-foundry"):
        data = json.dumps(packs.get(prov).data)
        for mid in ROWS:
            assert mid not in data
    foundry = packs.get("azure-foundry").lookup("mistral-small-2503")
    assert foundry.shutdown == "2027-02-15"
    assert foundry.replacement == "mistralai-mistral-small-4-119b-2603"
