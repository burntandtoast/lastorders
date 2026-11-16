"""16 Nov 2026: Anthropic sampling-parameter wording, earlier-version note, and Vercel AI SDK coverage.

Fixtures live in tests/fixtures/anthropic_sampling/. Positive cases must flag temperature/top_p/top_k
on clearly Anthropic calls; negative cases must not flag OpenAI or other providers in the same file.
"""
import datetime as dt
from pathlib import Path

from conftest import ROOT
from migration_kit.packs import load_packs
from migration_kit.scanner import scan

TODAY = dt.date(2026, 11, 16)
FIXTURES = ROOT / "tests" / "fixtures" / "anthropic_sampling"
ERR = "claude-sampling-removed-api-2026-10-21"
WARN = "claude-sampling-api-2026-10-21-warning"
WORDING = "will return a 400 on API version 2026-10-21 or later"

POSITIVES = {
    "positive_python_sdk.py": ("temperature", WARN),
    "positive_js_sdk.ts": ("top_p", WARN),
    "positive_http.js": ("top_k", WARN),
    "positive_langchain.py": ("temperature", WARN),
    "positive_vercel_ai.ts": ("temperature", WARN),
    "positive_version_2026_10_21.py": ("temperature", ERR),
    "positive_earlier_version.py": ("temperature", WARN),
}


def _scan_file(tmp_path, src: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    dest = tmp_path / src.name
    dest.write_text(src.read_text())
    return scan(tmp_path, packs=load_packs(offline=True), today=TODAY)


def _param_findings(res):
    return [f for f in res.findings if f.category == "param_rule" or ERR in f.rules or WARN in f.rules]


def test_positive_fixtures_flag_sampling_params(tmp_path):
    for name, (param, rule) in POSITIVES.items():
        res = _scan_file(tmp_path / name, FIXTURES / name)
        found = _param_findings(res)
        assert found, f"{name}: expected a sampling finding"
        # One flag per file (param_rule, or carried on a retiring model).
        assert len(found) == 1, (name, [(f.category, f.model, f.rules) for f in found])
        f = found[0]
        assert rule in f.rules and (ERR if rule == WARN else WARN) not in f.rules, name
        assert WORDING in " ".join(f.notes), (name, f.notes)
        assert "will fail" not in " ".join(f.notes).lower()
        assert "is broken" not in " ".join(f.notes).lower()
        if f.category == "param_rule":
            assert f.model == param
        if name == "positive_earlier_version.py":
            assert "This file sets anthropic-version to 2023-06-01, which is earlier than 2026-10-21." in f.notes
        if name == "positive_http.js":
            assert "This file sets anthropic-version to 2023-06-01, which is earlier than 2026-10-21." in f.notes
        if name == "positive_version_2026_10_21.py":
            assert "already sets anthropic-version to 2026-10-21 or later" in f.notes[0]
            assert not any("earlier than 2026-10-21" in n for n in f.notes)


def test_negative_fixtures_do_not_flag_other_providers(tmp_path):
    for name in (
        "negative_openai.py",
        "negative_openai_in_anthropic_file.py",
        "negative_no_params.py",
        "negative_vercel_openai.ts",
    ):
        res = _scan_file(tmp_path / name, FIXTURES / name)
        assert not [f for f in res.findings if f.category == "param_rule"], name
        assert not [f for f in res.findings if ERR in f.rules or WARN in f.rules], name


def test_pack_cites_16_nov_2026_and_keeps_official_urls():
    import json
    d = json.loads((ROOT / "migration_kit" / "pack_data" / "anthropic.json").read_text())
    assert d["version"] == "2026.11.16.1" and d["updated"] == "2026-11-16"
    assert all(s["url"].startswith("https://platform.claude.com/docs/") for s in d["sources"])
    checked = {s["id"]: s["checked"] for s in d["sources"]}
    assert checked["deprecations"] == "2026-11-16"
    notes = " ".join(d["notes"])
    assert "16 Nov 2026" in notes and "https://docs.anthropic.com/en/docs/about-claude/model-deprecations" in notes
    assert "will return a 400 on API version 2026-10-21 or later" in notes
    assert {s["id"] for s in d["signals"]} >= {"vercel_ai_anthropic", "anthropic_version_earlier"}
    warn = next(r for r in d["rules"] if r["id"] == WARN)
    assert "vercel_ai_anthropic" in warn["when_any"]
    assert WORDING in warn["message"]
    assert "prompt" not in warn["message"]
    assert "omit the parameters and use prompting" in notes
