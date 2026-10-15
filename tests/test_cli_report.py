import json

from conftest import ROOT, TEST_LICENCE
from migration_kit.cli import main

SAMPLE = str(ROOT / "examples" / "sample-app")
SUITE = str(ROOT / "examples" / "evals" / "sample-suite.yaml")


def test_full_demo_pipeline(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert main(["demo", "--out", str(tmp_path)]) == 0       # demo needs no licence
    for f in ["scan.json", "scan.md", "model-swap.diff", "swap-summary.json", "eval.json", "eval.md",
              "client-report.html", "client-report.md"]:
        assert (tmp_path / f).exists(), f
    html = (tmp_path / "client-report.html").read_text()
    assert "gpt-6-luna" in html and "14 Jan 2027" in html and "Demo run" in html
    assert "ft:gpt-4o-mini-2024-07-18" in html and "claude-sonnet-4-5-20250929" in html
    assert "Anthropic Claude API (stub)" in html and "<script" not in html
    scan = json.loads((tmp_path / "scan.json").read_text())
    assert scan["summary"]["fine_tuned_models"] == ["ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1"]
    assert {p["provider"] for p in scan["packs"]} == {"openai", "anthropic"}


def test_scan_free_no_key_no_licence(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert main(["scan", SAMPLE, "--out", str(tmp_path)]) == 0
    assert main(["scan", SAMPLE, "--out", str(tmp_path), "--fail-on-high"]) == 2


def test_scan_ci_outputs(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(ROOT)
    summ = tmp_path / "summary.md"
    main(["scan", SAMPLE, "--out", str(tmp_path), "--summary-file", str(summ), "--annotations"])
    out = capsys.readouterr().out
    assert "::error file=examples/sample-app/app/summarise.py,line=" in out
    text = summ.read_text()
    assert "Model retirement scan" in text and "| high |" in text


def test_paid_commands_gated(tmp_path, capsys):
    scan_dir = tmp_path / "s"
    main(["scan", SAMPLE, "--out", str(scan_dir)])
    assert main(["eval", SUITE, "--dry-run", "--out", str(tmp_path)]) == 4
    assert main(["report", "--client", "X", "--scan", str(scan_dir / "scan.json"), "--out", str(tmp_path)]) == 4
    assert main(["swap", SAMPLE, "--out", str(tmp_path), "--apply"]) == 4
    assert main(["swap", SAMPLE, "--out", str(tmp_path)]) == 0           # diff only stays free
    assert main(["report", "--client", "X", "--scan", str(scan_dir / "scan.json"), "--out", str(tmp_path),
                 "--licence", "nope"]) == 4
    assert "licence" in capsys.readouterr().err
    assert main(["report", "--client", "X", "--scan", str(scan_dir / "scan.json"), "--out", str(tmp_path),
                 "--licence", TEST_LICENCE]) == 0


def test_eval_without_key_uses_mock(tmp_path, monkeypatch, licensed):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert main(["eval", SUITE, "--out", str(tmp_path), "--fail-on-regression"]) == 3   # one deliberate FAIL
    assert json.loads((tmp_path / "eval.json").read_text())["mode"] == "mock"


def test_mapping_command(tmp_path):
    out = tmp_path / "m.yaml"
    assert main(["mapping", "--out", str(out)]) == 0
    assert "gpt-4o-2024-08-06: gpt-6-luna" in out.read_text()
