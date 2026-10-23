"""22 Oct 2026 pack release: Anthropic API version 2026-10-21 sampling rules, and the Microsoft Foundry pack
(mistral-small-2503 date, Cohere Embed v3 rebuild warning, Llama 3.3 / Llama 4 Maverick / Phi-4 rows)."""
import datetime as dt
import json
import re

import pytest

from conftest import ROOT
from migration_kit.fixer import plan_fixes
from migration_kit.packs import load_packs
from migration_kit.scanner import scan
from migration_kit.swapper import mapping_from_packs
from migration_kit.swapper import plan as swap_plan

TODAY = dt.date(2026, 10, 15)
ERR = "claude-sampling-removed-api-2026-10-21"
WARN = "claude-sampling-api-2026-10-21-warning"
OLD = "claude-sampling-deprecated"
COHERE = "foundry-cohere-embed-v3-rebuild-index"


def _pack(name):
    return json.loads((ROOT / "migration_kit" / "pack_data" / f"{name}.json").read_text())


def _rule(pack, rid):
    return next(r for r in _pack(pack)["rules"] if r["id"] == rid)


def _write(tmp_path, files):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


def _claude_call(model, version=None, temperature="0.2"):
    headers = f'default_headers={{"anthropic-version": "{version}"}}' if version else ""
    return ("import anthropic\n"
            f"client = anthropic.Anthropic({headers})\n"
            f'resp = client.messages.create(model="{model}", max_tokens=100, temperature={temperature}, messages=[])\n')


def _findings(root, model):
    return [f for f in scan(root, packs=load_packs(offline=True), today=TODAY).findings if f.model == model]


# ------------------------------------------------------------------ Anthropic: version boundary
@pytest.mark.parametrize("version,new", [
    ("2023-06-01", False), ("2026-10-20", False), ("2026-09-30", False), ("2025-12-31", False),
    ("2026-10-21", True), ("2026-10-31", True), ("2026-11-01", True), ("2026-12-31", True), ("2027-01-01", True),
])
def test_anthropic_version_signal_boundary(version, new):
    sig = next(s for s in _pack("anthropic")["signals"] if s["id"] == "anthropic_version_2026_10_21")
    rx = re.compile(sig["pattern"])
    forms = [f'"anthropic-version": "{version}"', f"-H 'anthropic-version: {version}'",
             f"ANTHROPIC_VERSION={version}", f"headers['anthropic-version'] = '{version}'",
             f"anthropic_version: {version}"]
    for form in forms:
        assert bool(rx.search(form)) is new, form


def test_rule_severity_error_and_warning():
    assert _rule("anthropic", ERR)["risk"] == "high"        # error
    assert _rule("anthropic", WARN)["risk"] == "medium"     # warning
    assert _rule("anthropic", ERR)["confidence"] == _rule("anthropic", WARN)["confidence"] == "confirmed"


@pytest.mark.parametrize("version,rule", [("2026-10-21", ERR), ("2026-11-05", ERR), ("2026-10-20", WARN), (None, WARN)])
def test_scan_error_at_or_after_2026_10_21_else_warning(tmp_path, version, rule):
    root = _write(tmp_path, {"app.py": _claude_call("claude-sonnet-4-5-20250929", version)})
    (f,) = _findings(root, "claude-sonnet-4-5-20250929")
    other = WARN if rule == ERR else ERR
    assert rule in f.rules and other not in f.rules
    assert any(n.startswith("Error:" if rule == ERR else "Warning:") for n in f.notes)


def test_no_sampling_params_no_rule(tmp_path):
    root = _write(tmp_path, {"app.py": "import anthropic\nclient = anthropic.Anthropic()\n"
                                       'client.messages.create(model="claude-sonnet-4-5-20250929", max_tokens=5, messages=[])\n'})
    (f,) = _findings(root, "claude-sonnet-4-5-20250929")
    assert ERR not in f.rules and WARN not in f.rules


@pytest.mark.parametrize("version,rule", [("2026-10-21", ERR), ("2026-10-20", WARN), (None, WARN)])
def test_fixer_flags_call_on_active_model_and_never_applies(tmp_path, version, rule):
    # claude-opus-4-6 is active and not covered by the older inferred rule, so nothing may remove the params,
    # even with --include-inferred.
    src = _claude_call("claude-opus-4-6", version)
    root = _write(tmp_path, {"app.py": src})
    for include_inferred in (False, True):
        res = plan_fixes(root, load_packs(offline=True), include_inferred=include_inferred)
        items = [i for i in res.items if i.rule in (ERR, WARN)]
        assert [i.rule for i in items] == [rule]
        assert items[0].status == "manual" and "not applied automatically" in items[0].change
        assert "app.py" not in res.new_contents and res.diff == ""


def test_fixer_error_uses_file_level_version_signal(tmp_path):
    # The header is set on the client, not on the call: the file-level signal still makes it an error.
    root = _write(tmp_path, {"app.py": _claude_call("claude-sonnet-5-5", "2026-10-21")})
    res = plan_fixes(root, load_packs(offline=True))
    rules = {i.rule: i for i in res.items}
    assert ERR in rules and WARN not in rules and rules[ERR].status == "manual"
    assert "temperature=0.2" in (root / "app.py").read_text()
    assert all("temperature" not in i.change or not i.status.startswith("fixed") for i in res.items)


def test_default_sampling_value_still_flagged_for_new_version(tmp_path):
    # Removed in 2026-10-21 for every value, not only non-default ones.
    root = _write(tmp_path, {"app.py": _claude_call("claude-opus-4-6", "2026-10-21", temperature="1")})
    res = plan_fixes(root, load_packs(offline=True))
    assert [i.rule for i in res.items if i.rule in (ERR, WARN)] == [ERR]


def test_anthropic_rules_fix_is_manual_only():
    for rid in (ERR, WARN):
        fix = _rule("anthropic", rid)["fix"]
        assert fix["action"] == "manual" and "not applied automatically" in fix["note"]


# ------------------------------------------------------------------ Microsoft Foundry pack
FOUNDRY_PY = ("from azure.ai.inference import EmbeddingsClient, ChatCompletionsClient\n"
              'emb = EmbeddingsClient(endpoint="https://acme.services.ai.azure.com/models")\n'
              'vec = emb.embed(model="Cohere-embed-v3-english", input=docs)\n'
              'chat = ChatCompletionsClient(endpoint="https://acme.services.ai.azure.com/models")\n'
              'r = chat.complete(model="mistral-small-2503", messages=[])\n'
              'r2 = chat.complete(model="Llama-4-Maverick-17B-128E-Instruct-FP8", messages=[])\n'
              'r3 = chat.complete(model="Llama-3.3-70B-Instruct", messages=[])\n'
              'r4 = chat.complete(model="Phi-4", messages=[])\n')


def test_mistral_small_2503_date_is_15_feb_2027(tmp_path):
    root = _write(tmp_path, {"app.py": FOUNDRY_PY})
    (f,) = _findings(root, "mistral-small-2503")
    assert f.provider == "azure-foundry" and f.shutdown == "2027-02-15"
    assert f.suggested == "mistralai-mistral-small-4-119b-2603"
    assert not f.auto_swap and f.no_swap_reason == "flag_only"
    assert any("30 Nov 2025" in n for n in f.notes)          # Mistral's own API retired it already
    assert "2026-12-09" not in json.dumps(_pack("azure-foundry"))


def test_foundry_risk_only_with_azure_signal(tmp_path):
    late = dt.date(2027, 1, 20)                               # 26 days before 15 Feb 2027
    on = _write(tmp_path / "on", {"app.py": FOUNDRY_PY})
    off = _write(tmp_path / "off", {"app.py": 'r = client.chat(model="mistral-small-2503")\n'})
    f_on = next(f for f in scan(on, packs=load_packs(offline=True), today=late).findings if f.model == "mistral-small-2503")
    f_off = next(f for f in scan(off, packs=load_packs(offline=True), today=late).findings if f.model == "mistral-small-2503")
    assert f_on.risk == "high" and f_off.risk == "info"


def test_cohere_embed_v3_flags_retirement_and_rebuild(tmp_path):
    root = _write(tmp_path, {"app.py": FOUNDRY_PY})
    (f,) = _findings(root, "Cohere-embed-v3-english")
    assert f.shutdown == "2027-02-15" and COHERE in f.rules and f.risk == "medium"
    text = " ".join(f.notes)
    assert "must be rebuilt" in text and "re-embed" in text and "Never swap the model id on its own" in text
    assert not f.auto_swap


def test_cohere_embed_v3_multilingual_too(tmp_path):
    root = _write(tmp_path, {"cfg.yaml": "embedding_model: Cohere-embed-v3-multilingual\n"})
    (f,) = _findings(root, "Cohere-embed-v3-multilingual")
    assert f.shutdown == "2027-02-15" and COHERE in f.rules


def test_foundry_models_never_swapped(tmp_path):
    root = _write(tmp_path, {"app.py": FOUNDRY_PY})
    packs = load_packs(offline=True)
    sw = swap_plan(root, mapping_from_packs(packs), packs)
    assert not sw.changes
    for include_inferred in (False, True):
        res = plan_fixes(root, packs, include_inferred=include_inferred)
        assert res.diff == "" and not res.new_contents
        rules = {(i.rule, i.model) for i in res.items}
        assert ("flag-only", "Cohere-embed-v3-english") in rules and ("flag-only", "mistral-small-2503") in rules
        cohere = [i for i in res.items if i.rule == COHERE]
        assert cohere and all(i.status == "manual" for i in cohere)
    assert _rule("azure-foundry", COHERE)["fix"]["action"] == "manual"
    assert all(m.get("map_automatically") is False for m in _pack("azure-foundry")["models"] if m.get("replacement"))


def test_plain_rows_llama_and_phi(tmp_path):
    root = _write(tmp_path, {"app.py": FOUNDRY_PY})
    for mid in ("Llama-4-Maverick-17B-128E-Instruct-FP8", "Llama-3.3-70B-Instruct"):
        (f,) = _findings(root, mid)
        assert f.provider == "azure-foundry" and f.shutdown is None and f.suggested is None
        assert f.category == "not_listed" and f.risk == "info" and f.confidence == "confirmed"
        assert any("no retirement date when sold by Azure" in n for n in f.notes)
        assert not any("None" in n for n in f.notes)
    (phi,) = _findings(root, "Phi-4")
    assert phi.shutdown == "2027-01-17" and not phi.auto_swap


def test_phi_4_pattern_is_exact(tmp_path):
    root = _write(tmp_path, {"a.py": 'a = "Phi-4-mini-instruct"\nb = "Phi-4-something-else"\nc = "Phi-40"\n'})
    found = {f.model for f in scan(root, packs=load_packs(offline=True), today=TODAY).findings if f.provider == "azure-foundry"}
    assert found == {"Phi-4-mini-instruct"}


def test_sources_and_conventions():
    for name in ("anthropic", "azure-foundry"):
        d = _pack(name)
        ids = {s["id"] for s in d["sources"]}
        assert all(s["url"].startswith("https://") and s["checked"] <= "2026-10-23" for s in d["sources"])
        for m in d["models"] + d.get("migrations", []):
            assert m.get("source", next(iter(ids))) in ids, m["id"]
        # anthropic moved on to 2026.10.23.1 in 0.4.13 (alias, real data; see test_0413.py)
        assert d["version"] in ("2026.10.22.1", "2026.10.22.2", "2026.10.23.1") and d["updated"] in ("2026-10-22", "2026-10-23")
    for m in _pack("azure-foundry")["models"]:
        assert m["confidence"] == "confirmed" and m.get("note")


def test_older_installs_ignore_the_new_provider():
    """0.4.x only fetches providers it bundles, so the hosted Foundry pack can't change their scans."""
    idx = json.loads((ROOT / "site" / "v1" / "index.json").read_text())
    assert {e["provider"] for e in idx["packs"]} == {"anthropic", "azure-foundry", "google", "openai"}
    assert (ROOT / "site" / "v1" / "pack.schema.json").read_bytes() == \
        (ROOT / "migration_kit" / "pack_data" / "pack.schema.json").read_bytes()
