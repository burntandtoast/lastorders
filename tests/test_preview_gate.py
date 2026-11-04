"""Unlicensed swap/fix print a per-file model summary and never a patch."""
import re

import pytest

from conftest import ROOT, TEST_LICENCE
from migration_kit.cli import main
from migration_kit.swapper import format_preview

SAMPLE = str(ROOT / "examples" / "sample-app")
PATCH_MARKERS = ("--- a/", "+++ b/", "+++ ", "@@", "diff --git", "\\ No newline")
SUMMARY_LINE = re.compile(r".+: \d+ changes? \(.+ -> .+\)")


def test_format_preview_groups_ids_without_locations():
    text = format_preview([
        ("src/app.py", "gpt-4-turbo", "gpt-4.1"),
        ("src/app.py", "gpt-4-turbo", "gpt-4.1"),
        ("src/app.py", "gpt-4o", "gpt-4.1"),
        ("lib/other.py", "gpt-4o-mini", "gpt-4.1-mini"),
    ])
    assert text == (
        "src/app.py: 3 changes (gpt-4-turbo -> gpt-4.1, gpt-4o -> gpt-4.1)\n"
        "lib/other.py: 1 change (gpt-4o-mini -> gpt-4.1-mini)"
    )
    assert format_preview([]) == "No model IDs would change."
    assert ":1" not in text and "@@" not in text


COUNT_LINE = re.compile(r"\d+ changes? in \d+ files?\. ")


def _assert_summary(text: str) -> None:
    assert "To get the reviewable patch plus the must-review list for this repo" in text
    assert "/#pricing" in text and "/buy" not in text
    for marker in PATCH_MARKERS:
        assert marker not in text
    lines = text.splitlines()
    end = next(i for i, ln in enumerate(lines) if COUNT_LINE.match(ln))
    body = [ln for ln in lines[:end] if ln and not ln.endswith("left alone.") and not ln.startswith("Warnings:")]
    assert body, text
    for ln in body:
        assert SUMMARY_LINE.fullmatch(ln), ln
        assert not re.search(r":\d", ln)


def _no_patch_files(out):
    if not out.exists():
        return
    names = [p.name for p in out.rglob("*") if p.is_file()]
    assert names == [], names


def test_unlicensed_swap_and_fix_are_summaries(tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["swap", SAMPLE, "--out", str(out)]) == 0
    swap_out = capsys.readouterr().out
    _assert_summary(swap_out)
    assert "left alone." in swap_out
    _no_patch_files(out)

    assert main(["fix", SAMPLE, "--out", str(out)]) == 0
    _assert_summary(capsys.readouterr().out)
    _no_patch_files(out)


def test_patch_routes_without_a_licence_write_nothing(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    repo = SAMPLE
    blocked = [
        ["swap", repo, "--out", str(out), "--apply"],
        ["swap", repo, "--out", str(out), "--licence", "nope"],
        ["swap", repo, "--out", str(out), "--licence", "BTM-NOPE-0000-0000"],
        ["fix", repo, "--out", str(out), "--apply"],
        ["fix", repo, "--out", str(out), "--verify"],
        ["fix", repo, "--out", str(out), "--verify", "--live"],
        ["fix", repo, "--out", str(out), "--apply", "--verify"],
        ["fix", repo, "--out", str(out), "--licence", "BTM-NOPE-0000-0000"],
        ["eval", str(ROOT / "examples" / "evals" / "sample-suite.yaml"), "--dry-run", "--out", str(out)],
    ]
    for args in blocked:
        assert main(args) == 4, args
    # internal demo bypass must not unlock the patch either
    assert main(["fix", repo, "--out", str(out), "--verify"], _demo=True) == 4
    monkeypatch.setenv("LASTORDERS_LICENCE", "BTM-NOPE-0000-0000")
    assert main(["swap", repo, "--out", str(out)]) == 4
    assert main(["fix", repo, "--out", str(out)]) == 4
    _no_patch_files(out)
    capsys.readouterr()

    for extra in (["--diff", str(out / "leak.diff")], ["--dry-run"], ["--format", "json"], ["--output", str(out)]):
        with pytest.raises(SystemExit) as ei:
            main(["swap", repo, "--out", str(out), *extra])
        assert ei.value.code == 2
        with pytest.raises(SystemExit) as ei:
            main(["fix", repo, "--out", str(out), *extra])
        assert ei.value.code == 2
    _no_patch_files(out)


def test_decoy_env_does_not_unlock_the_patch(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    for name in ("GATE_SWAP_PATCH", "GATE_FIX_PATCH", "LASTORDERS_FREE_PATCH", "LASTORDERS_WRITE_DIFF"):
        monkeypatch.setenv(name, "1")
    assert main(["fix", SAMPLE, "--out", str(out)]) == 0
    _assert_summary(capsys.readouterr().out)
    _no_patch_files(out)


def test_licensed_swap_and_fix_still_write_the_patch(tmp_path, licensed, capsys):
    out = tmp_path / "out"
    assert main(["swap", SAMPLE, "--out", str(out), "--licence", TEST_LICENCE]) == 0
    diff = (out / "model-swap.diff").read_text()
    assert "--- a/" in diff and "@@" in diff
    assert (out / "swap-summary.json").is_file()
    capsys.readouterr()

    assert main(["fix", SAMPLE, "--out", str(out), "--licence", TEST_LICENCE]) == 0
    fix = (out / "fix.diff").read_text()
    assert "--- a/" in fix and (out / "fix-plan.json").is_file() and (out / "fix-plan.md").is_file()
    shown = capsys.readouterr().out
    assert "patch:" in shown and "To get the reviewable patch" not in shown
