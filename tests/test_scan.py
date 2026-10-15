from conftest import ROOT
from migration_kit import catalogue as cat
from migration_kit.scanner import scan

SAMPLE = ROOT / "examples" / "sample-app"


def _by_model(res):
    out = {}
    for f in res.findings:
        out.setdefault(f.model, []).append(f)
    return out


def test_finds_all_in_scope_ids_and_skips_node_modules():
    res = scan(SAMPLE)
    models = _by_model(res)
    for m in ["gpt-4o-2024-08-06", "gpt-4o-2024-11-20", "gpt-4o-mini-2024-07-18", "gpt-4.1-2025-04-14",
              "gpt-4.1-mini-2025-04-14", "gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"]:
        assert m in models, m
        assert all(f.category == "in_scope" and f.suggested == "gpt-6-luna" for f in models[m])
    assert not any("node_modules" in f.file for f in res.findings)


def test_fine_tunes_flagged_separately_without_replacement():
    res = scan(SAMPLE)
    ft = [f for f in res.findings if f.model.startswith("ft:")]
    assert len(ft) == 2
    assert all(f.category == "fine_tune" and f.suggested is None and f.risk == "high" for f in ft)
    assert all(f.shutdown == "2027-01-14" for f in ft)


def test_transcription_and_nano_not_mapped_to_luna():
    models = _by_model(scan(SAMPLE))
    assert all(f.suggested != "gpt-6-luna" for f in models["gpt-4o-transcribe"])
    nano = models["gpt-4.1-nano"][0]
    assert nano.shutdown == "2026-10-23" and nano.suggested == "gpt-5.6-luna" and nano.risk == "high"


def test_unrelated_models_are_info_only():
    models = _by_model(scan(SAMPLE))
    assert models["gpt-5.6-sol"][0].category == "not_listed"
    assert "text-embedding-3-small" not in models


def test_chat_tools_raise_risk_and_mention_reasoning_effort():
    f = [f for f in scan(SAMPLE).findings if f.file == "web/src/chat.ts" and f.model == "gpt-4.1"][0]
    assert f.risk == "high"
    assert any("reasoning_effort" in n for n in f.notes)


def test_env_var_refs_and_kinds():
    res = scan(SAMPLE)
    assert {e.variable for e in res.env_refs} == {"OPENAI_MODEL", "CLASSIFIER_MODEL"}
    kinds = {(f.file, f.model): f.kind for f in res.findings}
    assert kinds[(".env.example", "gpt-4o-mini")] == "env"
    assert kinds[("config/models.yaml", "gpt-4o")] == "config"
    assert kinds[("app/summarise.py", "gpt-4o-2024-08-06")] == "sdk_call"
    assert kinds[("README.md", "gpt-4o")] == "doc"


def test_regex_boundaries(tmp_path):
    (tmp_path / "a.py").write_text(
        'x = "gpt-4o-2024-08-06"\ny = "my-gpt-4o-wrapper"\nz = "gpt-4o.json"\n'
        'w = "o3-mini"\n# we use o3 in prose\nv = "gpt-4o-mini-tts-2025-12-15"\n')
    res = scan(tmp_path)
    found = {f.model: f for f in res.findings}
    assert "gpt-4o-2024-08-06" in found and "o3-mini" in found
    assert "gpt-4o" not in found          # never matched inside other identifiers / filenames
    assert found["gpt-4o.json"].category == "not_listed"
    assert "o3" not in found              # o-series only trusted when quoted/assigned
    tts = found["gpt-4o-mini-tts-2025-12-15"]
    assert tts.suggested == "gpt-realtime-2.1-mini" and tts.category == "other_deprecated"


def test_catalogue_facts():
    assert cat.PRIMARY_REPLACEMENT == "gpt-6-luna" and cat.PRIMARY_SHUTDOWN == "2027-01-14"
    confirmed = {e.model for e in cat.ENTRIES if e.in_scope and e.confidence == "confirmed"}
    assert confirmed == {"gpt-4o-2024-08-06", "gpt-4o-2024-11-20", "gpt-4o-mini-2024-07-18",
                         "gpt-4.1-2025-04-14", "gpt-4.1-mini-2025-04-14"}
    assert cat.lookup("gpt-4o-realtime-preview-2024-12-17").replacement == "gpt-realtime-2.1"
    assert cat.base_of_fine_tune("ft:gpt-4.1-2025-04-14:org::abc") == "gpt-4.1-2025-04-14"
