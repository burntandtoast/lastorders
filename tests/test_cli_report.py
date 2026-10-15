import json

from conftest import ROOT
from migration_kit.cli import main


def test_full_demo_pipeline(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert main(["demo", "--out", str(tmp_path)]) == 0
    for f in ["scan.json", "scan.md", "model-swap.diff", "swap-summary.json", "eval.json", "eval.md",
              "client-report.html", "client-report.md"]:
        assert (tmp_path / f).exists(), f
    html = (tmp_path / "client-report.html").read_text()
    assert "gpt-6-luna" in html and "14 Jan 2027" in html and "Demo run" in html
    assert "ft:gpt-4o-mini-2024-07-18" in html
    assert "<script" not in html
    scan = json.loads((tmp_path / "scan.json").read_text())
    assert scan["summary"]["fine_tuned_models"] == ["ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1"]


def test_scan_fail_on_high(tmp_path):
    rc = main(["scan", str(ROOT / "examples" / "sample-app"), "--out", str(tmp_path), "--fail-on-high"])
    assert rc == 2


def test_eval_without_key_uses_mock(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    rc = main(["eval", str(ROOT / "examples" / "evals" / "sample-suite.yaml"), "--out", str(tmp_path),
               "--fail-on-regression"])
    assert rc == 3                       # the demo suite contains one deliberate FAIL
    assert json.loads((tmp_path / "eval.json").read_text())["mode"] == "mock"
