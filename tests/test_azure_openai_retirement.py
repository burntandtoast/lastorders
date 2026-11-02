"""Azure OpenAI retirement rows (Foundry schedule, checked 2 Nov 2026).

The OpenAI platform pack keeps its own dates. A snapshot that exists in both packs is
read on the Azure schedule only when the file shows Azure / Foundry use.
"""
import datetime as dt
import json

from conftest import ROOT
from migration_kit.packs import load_packs
from migration_kit.scanner import scan
from migration_kit.swapper import mapping_from_packs
from migration_kit.swapper import plan as swap_plan

TODAY = dt.date(2026, 10, 15)
PROVISIONED = "azure-gpt-4o-20240513-provisioned"

AZURE_PY = (
    "from openai import AzureOpenAI\n"
    "client = AzureOpenAI(azure_endpoint=\"https://acme.openai.azure.com/\", api_key=\"k\", api_version=\"2024-10-21\")\n"
    "client.chat.completions.create(model=\"gpt-4o-2024-05-13\", messages=[])\n"
    "client.chat.completions.create(model=\"gpt-4.1-mini-2025-04-14\", messages=[])\n"
    "client.chat.completions.create(model=\"gpt-5-mini-2025-08-07\", messages=[])\n"
    "client.chat.completions.create(model=\"gpt-5.1-2025-11-13\", messages=[])\n"
)

PLATFORM_PY = (
    "from openai import OpenAI\n"
    "client = OpenAI()\n"
    "client.chat.completions.create(model=\"gpt-4o-2024-05-13\", messages=[])\n"
    "client.chat.completions.create(model=\"gpt-4.1-mini-2025-04-14\", messages=[])\n"
    "client.chat.completions.create(model=\"gpt-5-mini-2025-08-07\", messages=[])\n"
)


def _pack():
    return json.loads((ROOT / "migration_kit" / "pack_data" / "azure-foundry.json").read_text())


def _model(mid):
    return next(m for m in _pack()["models"] if m["id"] == mid)


def _write(tmp_path, text):
    (tmp_path / "app.py").write_text(text)
    return tmp_path


def _by_model(root):
    out = {}
    for f in scan(root, packs=load_packs(offline=True), today=TODAY).findings:
        out.setdefault(f.model, []).append(f)
    return out


def test_azure_rows_match_the_foundry_schedule():
    gpt4o = _model("gpt-4o-2024-05-13")
    assert gpt4o["shutdown"] == "2027-01-14"
    assert gpt4o["replacement"] == "gpt-5.1"
    assert gpt4o["map_automatically"] is False
    assert "2025-11-13" in gpt4o["note"]
    assert "Global Standard and Data Zone Standard" in gpt4o["note"]
    assert "Provisioned deployments" in gpt4o["note"] and "do not" in gpt4o["note"]
    assert "gpt-5.6-sol" not in gpt4o["note"]
    mini = _model("gpt-4.1-mini-2025-04-14")
    assert mini["shutdown"] == "2027-04-14" and "replacement" not in mini
    g5 = _model("gpt-5-mini-2025-08-07")
    assert g5["shutdown"] == "2027-07-13" and "replacement" not in g5
    g51 = _model("gpt-5.1-2025-11-13")
    assert g51["shutdown"] == "2027-07-13" and "replacement" not in g51
    rule = next(r for r in _pack()["rules"] if r["id"] == PROVISIONED)
    assert "Provisioned deployments do not" in rule["message"]
    assert "gpt-5.1 version 2025-11-13" in rule["message"]
    assert rule["fix"]["action"] == "manual"
    assert "2026-12-09" not in json.dumps(_pack())


def test_openai_platform_row_and_mapping_stay_put():
    packs = load_packs(offline=True)
    oa = packs.get("openai").lookup("gpt-4o-2024-05-13")
    assert oa.shutdown == "2026-10-23" and oa.replacement == "gpt-5.6-sol"
    mapping = mapping_from_packs(packs)
    assert mapping.replacements["gpt-4o-2024-05-13"] == "gpt-5.6-sol"
    assert mapping.replacements["gpt-4.1-mini-2025-04-14"] == "gpt-6-luna"
    assert "gpt-5.1-2025-11-13" not in mapping.replacements
    assert "gpt-5-mini-2025-08-07" not in mapping.replacements
    assert "gpt-4o-2024-05-13" not in mapping.flag_only


def test_platform_file_keeps_openai_dates_and_swap(tmp_path):
    root = _write(tmp_path, PLATFORM_PY)
    found = _by_model(root)
    f = found["gpt-4o-2024-05-13"]
    assert len(f) == 1 and f[0].provider == "openai"
    assert f[0].shutdown == "2026-10-23" and f[0].suggested == "gpt-5.6-sol"
    assert PROVISIONED not in f[0].rules
    mini = found["gpt-4.1-mini-2025-04-14"][0]
    assert mini.provider == "openai" and mini.shutdown == "2027-01-14" and mini.suggested == "gpt-6-luna"
    g5 = found["gpt-5-mini-2025-08-07"][0]
    assert g5.provider == "openai" and g5.shutdown == "2026-12-11" and g5.suggested == "gpt-5.6-terra"
    packs = load_packs(offline=True)
    sw = swap_plan(root, mapping_from_packs(packs), packs)
    text = sw.new_contents["app.py"]
    assert 'model="gpt-5.6-sol"' in text and 'model="gpt-6-luna"' in text
    assert "gpt-4o-2024-05-13" not in text


def test_azure_file_uses_foundry_dates_and_does_not_swap(tmp_path):
    root = _write(tmp_path, AZURE_PY)
    found = _by_model(root)
    f = found["gpt-4o-2024-05-13"]
    assert len(f) == 1 and f[0].provider == "azure-foundry"
    assert f[0].shutdown == "2027-01-14" and f[0].suggested == "gpt-5.1"
    assert not f[0].auto_swap and f[0].no_swap_reason == "flag_only"
    assert PROVISIONED in f[0].rules
    note = " ".join(f[0].notes)
    assert "Global Standard and Data Zone Standard" in note
    assert "Provisioned deployments do not" in note
    assert "2025-11-13" in note
    assert "gpt-5.6-sol" not in note
    mini = found["gpt-4.1-mini-2025-04-14"][0]
    assert mini.provider == "azure-foundry" and mini.shutdown == "2027-04-14" and mini.suggested is None
    assert not mini.auto_swap
    g5 = found["gpt-5-mini-2025-08-07"][0]
    assert g5.provider == "azure-foundry" and g5.shutdown == "2027-07-13" and g5.suggested is None
    g51 = found["gpt-5.1-2025-11-13"][0]
    assert g51.provider == "azure-foundry" and g51.shutdown == "2027-07-13" and g51.suggested is None
    packs = load_packs(offline=True)
    sw = swap_plan(root, mapping_from_packs(packs), packs)
    assert "app.py" not in sw.new_contents
    assert "gpt-5.6-sol" not in (root / "app.py").read_text()
    assert "gpt-6-luna" not in (root / "app.py").read_text()
