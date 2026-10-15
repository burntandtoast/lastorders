from conftest import ROOT, TODAY
from migration_kit.packs import load_packs
from migration_kit.scanner import scan

SAMPLE = ROOT / "examples" / "sample-app"


def _scan(path=SAMPLE, **kw):
    return scan(path, today=TODAY, **kw)


def _by_model(res):
    out = {}
    for f in res.findings:
        out.setdefault(f.model, []).append(f)
    return out


def test_finds_all_in_scope_ids_and_skips_node_modules():
    res = _scan()
    models = _by_model(res)
    for m in ["gpt-4o-2024-08-06", "gpt-4o-2024-11-20", "gpt-4o-mini-2024-07-18", "gpt-4.1-2025-04-14",
              "gpt-4.1-mini-2025-04-14", "gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"]:
        assert m in models, m
        assert all(f.category == "in_scope" and f.suggested == "gpt-6-luna" and f.provider == "openai" for f in models[m])
    assert not any("node_modules" in f.file for f in res.findings)


def test_fine_tunes_flagged_separately_without_replacement():
    ft = [f for f in _scan().findings if f.model.startswith("ft:")]
    assert len(ft) == 2
    assert all(f.category == "fine_tune" and f.suggested is None and f.risk == "high" for f in ft)
    assert all(f.shutdown == "2027-01-14" for f in ft)


def test_transcription_and_nano_not_mapped_to_luna():
    models = _by_model(_scan())
    assert all(f.suggested != "gpt-6-luna" for f in models["gpt-4o-transcribe"])
    nano = models["gpt-4.1-nano"][0]
    assert nano.shutdown == "2026-10-23" and nano.suggested == "gpt-5.6-luna" and nano.risk == "high"


def test_unrelated_models_are_info_only():
    models = _by_model(_scan())
    assert models["gpt-5.6-sol"][0].category == "not_listed"
    assert "text-embedding-3-small" not in models


def test_rules_fire_from_pack_data():
    fs = {(f.file, f.model): f for f in _scan().findings}
    chat = fs[("web/src/chat.ts", "gpt-4.1")]
    assert chat.risk == "high" and "luna-chat-tools-effort" in chat.rules
    s = fs[("app/summarise.py", "gpt-4o-2024-08-06")]
    assert {"luna-max-tokens", "luna-sampling", "luna-structured"} <= set(s.rules)


def test_env_var_refs_kinds_and_sdks():
    res = _scan()
    assert {e.variable for e in res.env_refs} == {"OPENAI_MODEL", "CLASSIFIER_MODEL"}
    kinds = {(f.file, f.model): f.kind for f in res.findings}
    assert kinds[(".env.example", "gpt-4o-mini")] == "env"
    assert kinds[("config/models.yaml", "gpt-4o")] == "config"
    assert kinds[("app/summarise.py", "gpt-4o-2024-08-06")] == "sdk_call"
    assert kinds[("README.md", "gpt-4o")] == "doc"
    assert "openai:openai" in res.file_sdks["web/src/chat.ts"]
    assert "anthropic:anthropic" in res.file_sdks["app/claude_fallback.py"]


def test_regex_boundaries(tmp_path):
    (tmp_path / "a.py").write_text(
        'x = "gpt-4o-2024-08-06"\ny = "my-gpt-4o-wrapper"\nz = "gpt-4o.json"\n'
        'w = "o3-mini"\n# we use o3 in prose\nv = "gpt-4o-mini-tts-2025-12-15"\nr = "gpt-4o-realtime-preview-2024-12-17"\n')
    found = {f.model: f for f in _scan(tmp_path).findings}
    assert "gpt-4o-2024-08-06" in found and "o3-mini" in found
    assert "gpt-4o" not in found
    assert found["gpt-4o.json"].category == "not_listed"
    assert "o3" not in found
    assert found["gpt-4o-mini-tts-2025-12-15"].suggested == "gpt-realtime-2.1-mini"
    rt = found["gpt-4o-realtime-preview-2024-12-17"]          # family prefix match
    assert rt.suggested == "gpt-realtime-2.1" and rt.confidence == "inferred"


def test_second_provider_pack_is_used_by_the_same_engine():
    f = [f for f in _scan().findings if f.provider == "anthropic"]
    assert len(f) == 1
    c = f[0]
    assert c.model == "claude-sonnet-4-5-20250929" and c.suggested == "claude-sonnet-5-5" and c.shutdown == "2026-11-30"
    assert c.category == "in_scope" and "claude-sampling-deprecated" in c.rules and c.risk == "high"
    # openai rules never apply to anthropic findings
    assert not any(r.startswith("luna-") for r in c.rules)


def test_pack_selection_restricts_providers():
    res = _scan(packs=load_packs(["anthropic"]))
    assert {f.provider for f in res.findings} == {"anthropic"}


def test_already_retired_is_high(tmp_path):
    (tmp_path / "a.py").write_text('model = "claude-3-5-sonnet-20241022"\nm2 = "chatgpt-4o-latest"\n')
    fs = {f.model: f for f in _scan(tmp_path).findings}
    assert all(f.risk == "high" for f in fs.values())
    assert any("has passed" in n for n in fs["chatgpt-4o-latest"].notes)


def test_oct_2026_fine_tunes_pro_and_image_models(tmp_path):
    (tmp_path / "app.py").write_text(
        'A = "ft:gpt-3.5-turbo-1106:acme::abc123"\n'
        'B = "ft:davinci-002:acme::def456"\n'
        'C = "ft:gpt-4-0613:acme::ghi789"\n'
        'D = "ft:gpt-4o-mini-2024-07-18:acme::jkl012"\n'
        'E = "o3-pro-2025-06-10"\nF = "gpt-5-pro-2025-10-06"\nG = "gpt-image-1.5"\nH = "chatgpt-image-latest"\n'
        'I = "gpt-4-1106-preview"\nJ = "gpt-image-1-mini"\n')
    m = _by_model(_scan(tmp_path))
    for ft, rep in [("ft:gpt-3.5-turbo-1106:acme::abc123", "gpt-5.6-terra"), ("ft:davinci-002:acme::def456", "gpt-5.6-terra"),
                    ("ft:gpt-4-0613:acme::ghi789", "gpt-5.6-sol")]:
        f = m[ft][0]
        assert f.category == "fine_tune" and f.suggested is None and f.shutdown == "2026-10-23" and f.risk == "high"
        assert any(rep in n for n in f.notes) and any(n.startswith("No direct successor") for n in f.notes)
    assert m["ft:gpt-4o-mini-2024-07-18:acme::jkl012"][0].shutdown == "2027-01-14"   # headline fine-tunes unchanged
    for x in ("o3-pro-2025-06-10", "gpt-5-pro-2025-10-06"):
        assert m[x][0].shutdown == "2026-12-11" and any("reasoning.mode: pro" in n for n in m[x][0].notes)
    for x in ("gpt-image-1.5", "chatgpt-image-latest", "gpt-image-1-mini"):
        assert m[x][0].shutdown == "2026-12-01"
    assert m["gpt-4-1106-preview"][0].shutdown == "2026-10-23"
    mapping = load_packs().get("openai").default_mapping(None)
    assert not {"o3-pro-2025-06-10", "gpt-5-pro-2025-10-06", "gpt-image-1.5", "o1-pro", "gpt-image-1"} & set(mapping)
