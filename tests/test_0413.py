"""0.4.13: Claude Sonnet 4.5 alias and risk window, per-call sampling signals, plain scan summary,
pricing pointer (never /buy in passive output), copy in messages.py."""
import datetime as dt
import json
from pathlib import Path

from conftest import ROOT, TODAY
from migration_kit import messages
from migration_kit.cli import main
from migration_kit.packs import load_packs
from migration_kit.scanner import scan, terminal_summary, to_markdown, to_summary_markdown

ANTHROPIC = ROOT / "migration_kit" / "pack_data" / "anthropic.json"
MIXED = '''import anthropic, openai
a = anthropic.Anthropic()
r = a.messages.create(
    model="claude-sonnet-4-5-20250929",
    max_tokens=100,
    messages=[],
)
o = openai.OpenAI()
o.chat.completions.create(model="gpt-4o", max_tokens=10, temperature=0, messages=[])
'''


def _scan(tmp_path, files, today=TODAY):
    for name, text in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return scan(tmp_path, packs=load_packs(offline=True), today=today)


def test_anthropic_pack_is_not_a_stub_and_cites_official_docs():
    d = json.loads(ANTHROPIC.read_text())
    assert d["status"] == "stable" and "stub" not in d["name"].lower()
    assert not any("stub" in n.lower() for n in d["notes"])
    assert all(s["url"].startswith("https://platform.claude.com/docs/") for s in d["sources"])
    assert d["risk_policy"]["urgent_days"] == 60


def test_undated_alias_and_dated_id_both_retire_on_30_nov(tmp_path):
    res = _scan(tmp_path, {"config.yaml": "default_model: claude-sonnet-4-5\nother: claude-sonnet-4-5-20250929\n"})
    by = {f.model: f for f in res.findings}
    for mid in ("claude-sonnet-4-5", "claude-sonnet-4-5-20250929"):
        f = by[mid]
        assert f.category == "in_scope" and f.shutdown == "2026-11-30" and f.suggested == "claude-sonnet-5-5"
        assert f.risk == "high", mid           # 46 days before shutdown, inside the 60-day window
    assert "claude-sonnet-5-5" not in by


def test_fail_on_high_trips_for_the_alias_alone(tmp_path):
    (tmp_path / "config.yaml").write_text("model: claude-sonnet-4-5\n")
    assert main(["scan", str(tmp_path), "--out", str(tmp_path / "out"), "--offline", "--fail-on-high"]) == 2


def test_openai_temperature_does_not_flag_the_claude_call(tmp_path):
    res = _scan(tmp_path, {"app.py": MIXED})
    claude = next(f for f in res.findings if f.model == "claude-sonnet-4-5-20250929")
    assert not [r for r in claude.rules if "sampling" in r]
    assert not any("temperature" in n for n in claude.notes)
    assert not [f for f in res.findings if f.category == "param_rule" and f.provider == "anthropic"]
    gpt = next(f for f in res.findings if f.model == "gpt-4o")
    assert any("temperature" in n for n in gpt.notes)           # still flagged on the call that sets it


def test_claude_call_that_sets_temperature_is_still_flagged(tmp_path):
    src = MIXED.replace("    max_tokens=100,\n", "    max_tokens=100,\n    temperature=0.2,\n")
    res = _scan(tmp_path, {"app.py": src})
    claude = next(f for f in res.findings if f.model == "claude-sonnet-4-5-20250929")
    assert any("sampling" in r for r in claude.rules)


def test_model_constant_outside_a_call_ignores_other_providers_calls(tmp_path):
    src = ('import anthropic, openai\nMODEL = "claude-sonnet-4-5-20250929"\n'
           'anthropic.Anthropic().messages.create(model=MODEL, max_tokens=5, messages=[])\n'
           'openai.OpenAI().chat.completions.create(model="gpt-4o", temperature=0, messages=[])\n')
    claude = next(f for f in _scan(tmp_path, {"app.py": src}).findings if f.model == "claude-sonnet-4-5-20250929")
    assert not [r for r in claude.rules if "sampling" in r]


def test_terminal_summary_is_readable_and_points_at_pricing(tmp_path):
    res = _scan(tmp_path, {"app.py": MIXED, "config.yaml": "default_model: claude-sonnet-4-5\n"},
                today=dt.date(2026, 10, 23))
    text = terminal_summary(res, Path("out/scan.md"), Path("out/scan.json"))
    assert text.startswith("Found 3 retiring model IDs in 2 files (3 high risk). Fine-tunes: 0.")
    assert "Soonest shutdown: claude-sonnet-4-5" in text and "in 38 days" in text
    assert "{'" not in text and "packs:" not in text
    assert messages.PRICE in text and "lastorders.burntandtoast.com/#pricing" in text and "/buy" not in text


def test_terminal_summary_caps_rows(tmp_path):
    src = "".join(f'm{i} = "gpt-4o-2024-08-06"\n' for i in range(8))
    text = terminal_summary(_scan(tmp_path, {"a.py": src}), Path("scan.md"), Path("scan.json"))
    assert "  and 3 more in scan.md" in text


def test_clean_and_empty_scans(tmp_path):
    clean = _scan(tmp_path / "c", {"a.py": 'M = "claude-sonnet-5-5"\n'}, today=dt.date(2026, 10, 23))
    text = terminal_summary(clean, Path("scan.md"), Path("scan.json"))
    assert text.startswith("Scanned 1 file: no retiring model IDs found. Nothing to do today.")
    assert "(claude-sonnet-5-5)" in text and text.endswith(messages.REMIND_SHORT)
    md = to_markdown(clean)
    assert "**No retiring model IDs found.**" in md and "30 November 2026" in md and "## Next steps" not in md
    empty = _scan(tmp_path / "e", {"a.py": "print(1)\n"})
    text = terminal_summary(empty, Path("scan.md"), Path("scan.json"))
    assert text.startswith("Scanned 1 file: no AI model IDs found") and "built at runtime" in text


def test_scan_md_and_job_summary_end_with_next_steps(tmp_path):
    res = _scan(tmp_path, {"app.py": MIXED})
    md, summary = to_markdown(res), to_summary_markdown(res)
    assert "## Next steps" in md and "### Next steps" in summary
    for text in (md, summary):
        assert "£179" in text and "/#pricing" in text and "/buy" not in text
    assert "Reviewable patch plus must-review list for this repo, £179" in summary.splitlines()[-1]


def test_passive_copy_never_links_to_buy():
    for name in ("SCAN_NEXT_STEPS", "MD_NEXT_STEPS", "SUMMARY_FOOTER", "PREVIEW_PITCH", "MD_CLEAN", "SCAN_REMIND"):
        assert "/buy" not in str(getattr(messages, name)), name
    assert "/buy" in messages.NEEDS_LICENCE_TAIL and "£179" in messages.NEEDS_LICENCE_TAIL


def test_model_default_in_getenv_keeps_the_files_tool_signal(tmp_path):
    # examples/sample-app/app/agent.py: the id sits in os.getenv(...), the tools are on a later call
    src = ('from openai import OpenAI\nclient = OpenAI()\nMODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")\n'
           'client.chat.completions.create(model=MODEL, tools=[{"type": "function"}], messages=[])\n')
    f = next(f for f in _scan(tmp_path, {"agent.py": src}).findings if f.model == "gpt-4o-mini")
    assert "luna-chat-tools-effort" in f.rules and f.risk == "high"


def test_model_kwarg_through_getenv_uses_that_call(tmp_path):
    src = MIXED.replace('model="claude-sonnet-4-5-20250929"', 'model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")')
    claude = next(f for f in _scan(tmp_path, {"app.py": src}).findings if f.model == "claude-sonnet-4-5-20250929")
    assert not [r for r in claude.rules if "sampling" in r]
