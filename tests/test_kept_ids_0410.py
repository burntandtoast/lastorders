"""0.4.10: when a definition or option of an old id is kept, `swap` renames no other reference to it.

From Chad's swap test of 0.4.9 (17 Oct 2026): in 4 of 6 repos a kept definition (a skipped duplicate
key / id, a catalogue, a dropdown option, a dict key, a migration / deployment / fixture hold) stayed on
the old id while a default, a recommended list or a lookup elsewhere was renamed to an id that is not
defined, so the app looked up a model it doesn't have.

Fixtures in tests/fixtures/scan_accuracy/kept_ids_0410/ are short excerpts from public repos (shallow
clones, 16 Oct 2026), named in each file's first line:
- Lapis0x0/obsidian-yolo src/constants.ts, src/settings/schema/setting.types.ts
- i-dot-ai/themefinder evals/benchmark.py
- glowingjade/obsidian-smart-composer src/constants.ts, src/utils/chat/apply.ts,
  src/utils/llm/price-calculator.ts
- Sam-Osian/PFD-toolkit tests/model_comparison.py, tests/model_comparison_vis.py and
  django_workbench/workbench/{services.py, views.py, templates/workbench/settings.html}

Every test here fails on 0.4.9, which renamed the listed references and reported nothing.
"""
import json
import shutil
import subprocess

import pytest
from conftest import ROOT, TODAY
from migration_kit import swapper
from migration_kit.fixer.engine import plan_fixes
from migration_kit.packs import load_packs
from migration_kit.scanner import scan

FIX = ROOT / "tests" / "fixtures" / "scan_accuracy" / "kept_ids_0410"


def _swap(root):
    packs = load_packs()
    return swapper.plan(root, swapper.mapping_from_packs(packs), packs)


def _line(root, rel, n, sw=None):
    text = sw.new_contents.get(rel) if sw else None
    text = text if text is not None else (root / rel).read_text()
    return text.splitlines()[n - 1]


def _kept_refs(sw):
    return {(m["file"], m["line"], m["model"]) for m in sw.must_update_together if m["kind"] == "kept_definition"}


def _groups(sw):
    return {g["model"]: g for g in sw.kept_definitions}


def _assert_unchanged(root, sw, refs):
    for rel, n, _ in refs:
        assert _line(root, rel, n, sw) == _line(root, rel, n), f"{rel}:{n} was rewritten"


# ---------------------------------------------------------------- YOLO

def test_yolo_title_default_and_recommended_lists_stay_with_the_kept_chat_models():
    """The DEFAULT_CHAT_MODELS entries are skipped duplicate ids, so DEFAULT_CHAT_TITLE_MODEL_ID and the
    recommended lists must keep pointing at them (0.4.9 renamed them to openai/gpt-6-luna, which
    `DEFAULT_CHAT_MODELS.find(v => v.id === DEFAULT_CHAT_TITLE_MODEL_ID)` no longer finds)."""
    root = FIX / "yolo"
    sw = _swap(root)
    refs = {("src/constants.ts", 3, "gpt-4.1-mini"), ("src/constants.ts", 7, "gpt-4.1"),
            ("src/constants.ts", 9, "gpt-4.1-mini")}
    assert refs <= _kept_refs(sw)
    _assert_unchanged(root, sw, refs)
    assert "src/constants.ts" not in sw.new_contents
    g = _groups(sw)
    assert {(k["file"], k["line"]) for k in g["gpt-4.1-mini"]["kept"]} == {("src/constants.ts", 21),
                                                                           ("src/constants.ts", 22)}
    assert {(r["file"], r["line"]) for r in g["gpt-4.1-mini"]["references"]} == {("src/constants.ts", 3),
                                                                                 ("src/constants.ts", 9)}
    assert g["gpt-4.1-mini"]["target"] == "gpt-6-luna"
    assert sw.summary()["kept_definitions"]


# ---------------------------------------------------------------- themefinder

def test_themefinder_quick_models_stay_with_the_kept_azure_entry():
    """`args.models = ["gpt-4.1"]` filters AZURE_MODELS by name; the AZURE_MODELS entry is a skipped
    duplicate id, so 0.4.9's rename to gpt-6-luna made `--quick` find no model."""
    root = FIX / "themefinder"
    sw = _swap(root)
    assert ("evals/benchmark.py", 13, "gpt-4.1") in _kept_refs(sw)
    assert _line(root, "evals/benchmark.py", 13, sw) == '        args.models = ["gpt-4.1"]'
    g = _groups(sw)["gpt-4.1"]
    assert ("evals/benchmark.py", 4) in {(k["file"], k["line"]) for k in g["kept"]}
    assert g["references"] == [{"file": "evals/benchmark.py", "line": 13}]
    # the deployment hold on gpt-4.1-mini is a kept definition too
    assert "deployment_name" in {k["reason"] for k in _groups(sw)["gpt-4.1-mini"]["kept"]}
    fx = plan_fixes(root)
    assert any(i.rule == "kept-definition" and (i.file, i.line) == ("evals/benchmark.py", 13) for i in fx.items)


# ---------------------------------------------------------------- Smart Composer

def test_smart_composer_apply_default_stays_with_kept_price_key_and_predicted_list():
    """OPENAI_PRICES keys and PREDICTED_OUTPUTS_SUPPORTED_MODELS keep gpt-4.1-mini (duplicate key / id), so
    DEFAULT_APPLY_MODEL_ID, RECOMMENDED_MODELS_FOR_APPLY and the DEFAULT_CHAT_MODELS entry stay too
    (0.4.9 renamed them, so the price lookup returned null and predicted outputs were switched off)."""
    root = FIX / "smart-composer"
    sw = _swap(root)
    refs = {("src/constants.ts", n, "gpt-4.1-mini") for n in (2, 3, 8, 9)}
    assert refs <= _kept_refs(sw)
    _assert_unchanged(root, sw, refs)
    kept = {(k["file"], k["line"], k["reason"]) for k in _groups(sw)["gpt-4.1-mini"]["kept"]}
    assert kept == {("src/constants.ts", 15, "duplicate_key"), ("src/utils/chat/apply.ts", 6, "duplicate_id")}
    # ids with no kept definition are still renamed
    assert "gpt-4.1-nano" not in _line(root, "src/utils/chat/apply.ts", 7, sw)
    assert "gpt-4.1-nano" not in {g["model"] for g in sw.kept_definitions}
    manual = [m for m in sw.manual() if m["kind"] == "kept-definition"]
    assert {(m["file"], m["line"]) for m in manual} == {("src/constants.ts", n) for n in (2, 3, 8, 9)}


# ---------------------------------------------------------------- PFD

def test_pfd_default_and_dict_key_stay_with_kept_dropdown_and_list():
    """The settings <select> options and the model_comparison list entries are skipped duplicate ids, so
    the services.py default, the FRONTIER_NAMES dict key and the views.py allow-list stay on the old ids
    (0.4.9 renamed the default to gpt-6-luna, which the dropdown doesn't offer, and added it to the
    allow-list)."""
    root = FIX / "pfd"
    sw = _swap(root)
    refs = {("workbench/services.py", 3, "gpt-4.1-mini"), ("tests/model_comparison_vis.py", 3, "gpt-4.1")}
    assert refs <= _kept_refs(sw)
    _assert_unchanged(root, sw, refs)
    assert "workbench/views.py" not in sw.new_contents          # allow-list not extended
    assert "workbench/services.py" not in sw.new_contents
    assert "tests/model_comparison_vis.py" not in sw.new_contents
    g = _groups(sw)
    assert ("workbench/templates/settings.html", 3) in {(k["file"], k["line"]) for k in g["gpt-4.1-mini"]["kept"]}
    fx = plan_fixes(root)
    kd = {(i.file, i.line) for i in fx.items if i.rule == "kept-definition"}
    assert kd == {("workbench/services.py", 3), ("tests/model_comparison_vis.py", 3)}
    # listed once in fix, not also as a generic must-update-together item
    assert not [i for i in fx.items if i.rule == "must-update-together" and (i.file, i.line) in kd]


# ---------------------------------------------------------------- CLI, API and git apply agree

@pytest.mark.parametrize("case", ["yolo", "themefinder", "smart-composer", "pfd"])
def test_cli_api_and_git_apply_agree(tmp_path, capsys, monkeypatch, case):
    from migration_kit import cli
    repo = tmp_path / "repo"
    shutil.copytree(FIX / case, repo)
    sw = _swap(repo)
    monkeypatch.setattr(cli, "_patch_licence", lambda a, feature: True)
    assert cli.main(["swap", str(repo), "--out", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    summary = json.loads((tmp_path / "out" / "swap-summary.json").read_text())
    assert summary["kept_definitions"] == sw.kept_definitions
    for rel, n, model in _kept_refs(sw):
        assert f"MUST UPDATE TOGETHER {rel}:{n} {model}" in out
    assert "KEPT " in out
    diff = (tmp_path / "out" / "model-swap.diff").read_text()
    if not sw.new_contents:
        assert diff == "" and "nothing to apply" in out
        return
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "apply", str(tmp_path / "out" / "model-swap.diff")], cwd=repo, check=True)
    for rel, text in sw.new_contents.items():
        assert (repo / rel).read_text() == text


# ---------------------------------------------------------------- scan agrees on hold-based kept ids

def test_scan_marks_references_of_held_ids_as_kept_definition(tmp_path):
    (tmp_path / "pricing.json").write_text('{"gpt-4o": {"input": 2.5}}\n')
    (tmp_path / "app.py").write_text('MODEL = "gpt-4o"\nOTHER = "gpt-4o-mini"\n')
    res = scan(tmp_path, today=TODAY)
    f = {(x.file, x.model): x for x in res.findings}
    assert f[("app.py", "gpt-4o")].auto_swap is False
    assert f[("app.py", "gpt-4o")].no_swap_reason == "kept_definition"
    assert f[("app.py", "gpt-4o-mini")].auto_swap is True
    sw = _swap(tmp_path)
    assert ("app.py", 1, "gpt-4o") in _kept_refs(sw)
    assert sw.new_contents["app.py"].splitlines()[0] == 'MODEL = "gpt-4o"'
    assert "gpt-4o-mini" not in sw.new_contents["app.py"]
