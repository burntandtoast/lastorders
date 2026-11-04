"""0.4.11: reporting only (from Chad's 0.4.10 review, 18 Oct 2026), plus the Go duplicate-id check.

- scan.md and the Action job summary say the licensed patch can be smaller than the suggested
  replacements (the scan can't run swap's duplicate checks; swap skips docs by default).
- fix-plan.md and the client report no longer say "Automatic".
- When the CLI cuts the swap warnings short, it says where the full list is.
- One-line Go composite literals of strings get the duplicate-id check (HexmosTech/LiveReview
  internal/aiconnectors/models_test.go:38 ended up with "gpt-6-luna" twice in 0.4.10).
"""
from conftest import TODAY
from migration_kit import swapper
from migration_kit.fixer.engine import plan_fixes, to_markdown as fix_markdown
from migration_kit.packs import load_packs
from migration_kit.scanner import scan, to_markdown, to_summary_markdown


def _swap(root):
    packs = load_packs()
    return swapper.plan(root, swapper.mapping_from_packs(packs), packs)


# 0.4.13: the caveat moved into a "Next steps" block at the end of scan.md and the job summary.
NOTE = "so it can be smaller than the table above"


def test_scan_report_and_job_summary_carry_the_patch_size_note(tmp_path):
    (tmp_path / "app.py").write_text('MODEL = "gpt-4o-2024-08-06"\n')
    res = scan(tmp_path, today=TODAY)
    assert any(f.suggested and f.auto_swap for f in res.findings)
    md, summary = to_markdown(res), to_summary_markdown(res)
    assert NOTE in md and NOTE in summary
    assert "fix .` shows the real per-file count" in md
    assert "It skips docs unless you pass `--include-docs`" in md
    assert len([l for l in md.splitlines() if NOTE in l]) == 1
    assert md.rstrip().splitlines()[-5] == "## Next steps" and md.index("## Next steps") > md.rindex("| `app.py`")


def test_no_patch_size_note_without_plain_replacements(tmp_path):
    (tmp_path / "app.py").write_text('print("hello")\n')
    res = scan(tmp_path, today=TODAY)
    assert NOTE not in to_markdown(res) and NOTE not in to_summary_markdown(res)


def test_fix_plan_title_is_not_automatic(tmp_path):
    (tmp_path / "app.py").write_text(
        'from openai import OpenAI\nc = OpenAI()\nc.chat.completions.create(model="gpt-4o-2024-08-06", '
        'messages=[], max_tokens=10)\n')
    md = fix_markdown(plan_fixes(tmp_path))
    assert md.startswith("# Fix plan\n")
    assert "Automatic" not in md


def test_cli_says_where_the_full_list_is_when_it_truncates(tmp_path, capsys, monkeypatch):
    from migration_kit import cli
    repo = tmp_path / "repo"
    repo.mkdir()
    # gpt-4o -> gpt-6-luna would duplicate the existing key, so gpt-4o is kept and every
    # other reference is listed: more than the 25 lines the CLI prints.
    refs = "".join(f'M{i} = "gpt-4o"\n' for i in range(40))
    (repo / "app.py").write_text('PRICES = {"gpt-4o": 1, "gpt-6-luna": 2}\n' + refs)
    sw = _swap(repo)
    assert len(sw.warnings()) > 25
    monkeypatch.setattr(cli, "_patch_licence", lambda a, feature: True)
    assert cli.main(["swap", str(repo), "--out", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert "more lines not shown. Full list in" in out
    assert "swap-summary.json: kept_definitions" in out and "fix-plan.md" in out


def test_go_slice_collapse_is_skipped_as_duplicate_id(tmp_path):
    (tmp_path / "models_test.go").write_text(
        'package x\n\nvar rows = []driver.Value{"gpt-5.6-terra", "gpt-4o", "gpt-4.1"}\n')
    sw = _swap(tmp_path)
    assert sw.new_contents == {}
    assert {d["model"] for d in sw.skipped_duplicate_id} == {"gpt-4o", "gpt-4.1"}
    assert sw.collapsed and sw.collapsed[0]["applied"] is False


def test_go_slice_with_unique_results_is_still_renamed(tmp_path):
    (tmp_path / "models.go").write_text('package x\n\nvar ids = []string{"gpt-4o", "o1"}\n')
    sw = _swap(tmp_path)
    assert sw.skipped_duplicate_id == []
    assert '"o1"' not in sw.new_contents["models.go"]


def test_go_call_arguments_are_not_treated_as_a_list(tmp_path):
    (tmp_path / "main.go").write_text('package x\n\nvar s = fmt.Sprintf("%s %s", "gpt-4o", "gpt-4.1")\n')
    sw = _swap(tmp_path)
    assert sw.skipped_duplicate_id == []
    assert sw.new_contents["main.go"].count("gpt-6-luna") == 2
