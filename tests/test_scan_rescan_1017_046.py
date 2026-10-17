"""Regression fixtures from Chad's rerun of the 38 repos with 0.4.6 (17 Oct 2026, section 6).

Snippets are excerpts from public repos (shallow clones, 16 Oct 2026):
- triggerdotdev/trigger.dev internal-packages/llm-model-catalog/scripts/research-model.sh:1-20,36-54,
  .cursor/rules/writing-tasks.mdc (frontmatter + 760-770 in a fence), src/default-model-prices.json:897-903,2015-2020,
  docs/guides/example-projects/vercel-ai-sdk-deep-research.mdx:26-31, packages/trigger-sdk/src/v3/ai.ts:4760-4765
- cognesy/instructor-php docs/release-notes/v1.17.0.mdx:84-95
- Lapis0x0/obsidian-yolo src/settings/schema/migrations/5_to_6.ts:24-40, src/constants.ts:752-760
- docmancer/docmancer docmancer/cli/memory_commands.py:1931, docmancer/memory/context_engine.py:37-41
- zh-plus/openlrc tests/test_config.py:39-41 (saved as tests/config_checks.py so pytest does not collect it)
- donvito/ai-backends src/templates/projectPlannerDemo.html:214-222 (plus a synthetic commented-out <option>),
  src/templates/landing.html:640-643,663
- Sam-Osian/PFD-toolkit django_workbench/.../settings.html:30-36; tutorials/getting_started.ipynb (first markdown
  cell, shortened, plus one added line; the code cell with model="gpt-4.1", with a synthetic stream output)
- i-dot-ai/themefinder Makefile:10-22
- ukhsa-collaboration/epiviz man/llm_interpret.Rd:1-3,25-31
- HexmosTech/LiveReview config/livereview.toml.example:44-49
- 0xNyk/lacp scripts/ci/test-claude-hooks.sh:9,80 (plus a synthetic MODEL= line)
"""
import json
from pathlib import Path

from conftest import ROOT, TODAY
from migration_kit import swapper
from migration_kit.fixer.engine import plan_fixes
from migration_kit.packs import load_packs
from migration_kit.scanner import scan

FIX = ROOT / "tests" / "fixtures" / "scan_accuracy" / "rescan_1017_046"


def _scan(sub, **kw):
    return scan(FIX / sub, today=TODAY, **kw)


def _swap(root):
    packs = load_packs()
    return swapper.plan(root, swapper.mapping_from_packs(packs), packs)


def _at(res, file, line):
    return [f for f in res.findings if f.file == file and f.line == line]


def _scan_text(tmp_path, name, text, **kw):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return scan(tmp_path, today=TODAY, **kw)


# ---------------------------------------------------------------- A. swap safety

def test_name_checks_are_not_auto_swap_in_json(tmp_path):
    res = _scan_text(tmp_path, "a.ts", 'if (m.startsWith("o1")) {}\nif (s.includes(\'gpt-4\')) {}\n')
    assert [(f.model, f.kind, f.risk) for f in res.findings] == [("o1", "name_check", "low"), ("gpt-4", "name_check", "low")]
    assert all(f.auto_swap is False for f in res.findings)
    assert all(f["auto_swap"] is False for f in res.to_dict()["findings"])


def test_array_membership_is_a_name_check():
    # 0.4.8: an exact-match list is an `allow_list`. 0.4.9: this one sits in a settings migration
    # (`migrations/`), which describes data written by past versions, so swap never rewrites it.
    res = _scan("yolo")
    row = _at(res, "src/settings/schema/migrations/5_to_6.ts", 9)
    assert [(f.model, f.kind, f.risk, f.auto_swap) for f in row] == [
        ("o1", "allow_list", "low", False), ("o1-mini", "allow_list", "info", False), ("o3-mini", "allow_list", "low", False)]
    assert row[2].no_swap_reason == "migration"
    sw = _swap(FIX / "yolo")
    assert "src/settings/schema/migrations/5_to_6.ts" not in sw.new_contents
    assert [m["file"] for m in sw.skipped_migration] == ["src/settings/schema/migrations/5_to_6.ts"]


def test_array_membership_forms(tmp_path):
    src = ('if model in ("o1", "o3-mini"):\n    pass\n'
           'if model not in ["gpt-4"]:\n    pass\n'
           'for m in ["gpt-4o", "o1"]:\n    client.chat(model=m)\n')
    res = _scan_text(tmp_path, "a.py", src)
    kinds = {(f.line, f.model): f.kind for f in res.findings}
    assert kinds[(1, "o1")] == kinds[(1, "o3-mini")] == kinds[(3, "gpt-4")] == "allow_list"
    assert kinds[(5, "gpt-4o")] not in ("name_check", "allow_list") and kinds[(5, "o1")] not in ("name_check", "allow_list")
    res = _scan_text(tmp_path, "b.php", "<?php\nif (in_array($m, ['o1', 'gpt-4'])) {}\n")
    assert {f.kind for f in res.findings if f.file == "b.php"} == {"allow_list"}
    res = _scan_text(tmp_path, "c.ts", "const fam = new Set(['o1', 'o3-mini']).has(model)\n")
    assert {f.kind for f in res.findings if f.file == "c.ts"} == {"allow_list"}


def test_prompt_prose_is_low_and_not_swapped():
    res = _scan("trigger")
    sh = "internal-packages/llm-model-catalog/scripts/research-model.sh"
    l29, l30 = _at(res, sh, 29), _at(res, sh, 30)        # lines 43 and 44 of the real file
    assert [f.model for f in l29] == ["gpt-4o-2024-08-06"]
    assert "gpt-3.5-turbo" in [f.model for f in l30]
    for f in l29 + l30:
        assert (f.kind, f.auto_swap) == ("prose", False)
        assert f.risk in ("low", "info")
        assert any("running text" in n for n in f.notes)
    sw = _swap(FIX / "trigger")
    new = sw.new_contents.get(sh, (FIX / "trigger" / sh).read_text()).splitlines()
    assert new[29 - 1] == (FIX / "trigger" / sh).read_text().splitlines()[29 - 1]
    assert new[30 - 1] == (FIX / "trigger" / sh).read_text().splitlines()[30 - 1]
    assert (sh, 30, "gpt-3.5-turbo", "prose") in sw.skipped_unsafe
    # the usage comment on line 8 is still a normal (low) comment finding
    assert [(f.model, f.kind) for f in _at(res, sh, 8)] == [("gpt-4o", "comment")]


def test_prose_heuristic_keeps_values_args_and_assignments(tmp_path):
    src = "\n".join([
        'client.chat.completions.create(model="gpt-4", messages=messages, temperature=0, stream=False)',
        'MODEL = "gpt-4o"  # the default model we use for all of the summaries in this app today',
        'cmd = f"uv run python benchmark.py --dataset housing --runs 5 --provider all --judge-model gpt-4.1"',
        'parser.add_argument("--model", default="gpt-4o-mini", help="Which model to use for the whole run of this job")',
        'PROMPT = "You are a helpful assistant. Compare the answers and explain which is better, for example gpt-4 or a newer model."',
        'url = "https://api.openai.com/v1/engines/gpt-4/completions"',
    ]) + "\n"
    res = _scan_text(tmp_path, "a.py", src)
    by_line = {}
    for f in res.findings:
        by_line.setdefault(f.line, []).append(f)
    assert by_line[1][0].kind == "sdk_call" and by_line[1][0].auto_swap
    assert by_line[2][0].kind != "prose" and by_line[2][0].auto_swap
    assert by_line[3][0].kind != "prose" and by_line[3][0].auto_swap         # CLI flag argument
    assert by_line[4][0].kind != "prose" and by_line[4][0].auto_swap
    assert (by_line[5][0].kind, by_line[5][0].auto_swap) == ("prose", False)
    assert by_line[6][0].model == "gpt-4"                                     # API URL still counts


def test_ids_in_web_page_links_are_skipped(tmp_path):
    res = _scan("trigger")
    assert not [f for f in res.findings if f.file.endswith("vercel-ai-sdk-deep-research.mdx")]
    src = ('const DOCS = "https://platform.openai.com/docs/models/gpt-4o";\n'
           'const API = "https://api.openai.com/v1/models/gpt-4o";\n'
           'const AZ = `https://${resource}.openai.azure.com/openai/deployments/gpt-4o/chat/completions`;\n')
    res = _scan_text(tmp_path, "u.ts", src)
    assert sorted(f.line for f in res.findings) == [2, 3]


def test_release_notes_are_info_and_not_swapped():
    res = _scan("instructor")
    f, = res.findings
    assert (f.file, f.line, f.model, f.risk, f.auto_swap) == ("docs/release-notes/v1.17.0.mdx", 7, "gpt-4", "info", False)
    assert any("changelog" in n for n in f.notes)
    packs = load_packs()
    m = swapper.mapping_from_packs(packs)
    m.include_docs = True
    sw = swapper.plan(FIX / "instructor", m, packs)
    assert not sw.new_contents and sw.skipped_unsafe == [("docs/release-notes/v1.17.0.mdx", 7, "gpt-4", "changelog")]


def test_changelog_paths(tmp_path):
    from migration_kit.scanner import is_changelog
    for rel in ["CHANGELOG.md", "packages/core/CHANGELOG.md", "HISTORY.rst", "docs/release-notes/v1.18.0.mdx",
                "release-notes/2024-04-15-v0.12.0.md", "docs/changelog.md", "docs/v2.6.0.mdx", "RELEASE_NOTES"]:
        assert is_changelog(rel), rel
    for rel in ["src/releases.ts", "src/history.py", "docs/1.4.3-CONTROLLED-AUDIO-TRANSCRIPTS.md", "README.md",
                "docs/guide.mdx"]:
        assert not is_changelog(rel), rel


# ---------------------------------------------------------------- B. coverage

def test_colon_prefixed_ids():
    res = _scan("openlrc")
    assert [(f.line, f.model, f.risk) for f in res.findings] == [(6, "gpt-4", "high"), (7, "gpt-4", "high")]
    res = _scan("trigger")
    row = _at(res, "packages/trigger-sdk/src/v3/ai.ts", 4)
    assert [(f.model, f.kind) for f in row] == [("gpt-4o", "comment"), ("claude-sonnet-4-6", "comment")]
    sw = _swap(FIX / "openlrc")
    assert '"openai:gpt-5.6-sol"' in sw.new_contents["tests/config_checks.py"]


def test_colon_prefix_short_ids_and_non_providers(tmp_path):
    res = _scan_text(tmp_path, "c.ts", 'const a = "openai:o3-mini";\nconst q = "{org:o1}:proj:p1";\nconst k = "key:gpt-4";\n')
    assert [(f.line, f.model) for f in res.findings] == [(1, "o3-mini")]


def test_trailing_full_stop(tmp_path):
    res = _scan("docmancer")
    assert [(f.file, f.line, f.model) for f in res.findings] == [
        ("docmancer/cli/memory_commands.py", 3, "gpt-4.1-nano"), ("docmancer/memory/context_engine.py", 4, "gpt-4.1-nano")]
    res = _scan_text(tmp_path, "v.py", 'A = "gpt-4.1"\nB = "gpt-3.5-turbo"\nC = "gpt-4.5x"\n# use gpt-4.\n')
    assert [(f.line, f.model) for f in res.findings] == [(1, "gpt-4.1"), (2, "gpt-3.5-turbo"), (3, "gpt-4.5x"), (4, "gpt-4")]


def test_unquoted_object_keys():
    res = _scan("yolo")
    o1, = [f for f in res.findings if f.file == "src/constants.ts" and f.model == "o1"]
    assert (o1.line, o1.risk, o1.auto_swap) == (7, "high", False)
    assert any("Unquoted object key" in n for n in o1.notes)
    sw = _swap(FIX / "yolo")
    new = sw.new_contents["src/constants.ts"].splitlines()
    assert new[6] == "  o1: { input: 15, output: 60 },"              # a bare gpt-5.6-sol key would not parse
    assert "'gpt-5.6-terra': { input: 1.1" in new[7]
    assert ("src/constants.ts", 7, "o1", "object_key") in sw.skipped_unsafe


def test_object_key_needs_object_value(tmp_path):
    res = _scan_text(tmp_path, "k.ts", "const p = { o1: 3, o2: 4 };\nconst r = cond ? o1 : o2;\n")
    assert not res.findings


def test_fine_tune_is_flag_only():
    res = _scan("trigger")
    ft, = [f for f in res.findings if f.category == "fine_tune"]
    assert (ft.model, ft.shutdown, ft.auto_swap) == ("ft:gpt-3.5-turbo-1106", "2026-10-23", False)
    assert any("Fine-tune of gpt-3.5-turbo-1106" in n for n in ft.notes)
    assert res.to_dict()["summary"]["fine_tuned_models"] == ["ft:gpt-3.5-turbo-1106"]


def test_regex_pattern_strings_are_flag_only():
    res = _scan("trigger")
    f = "internal-packages/llm-model-catalog/src/default-model-prices.json"
    pat, = _at(res, f, 13)
    name, = _at(res, f, 12)
    assert (pat.model, pat.risk, pat.auto_swap) == ("o1", "low", False)
    assert any("regex pattern" in n for n in pat.notes)
    # 0.4.9: a price catalogue (modelName + matchPattern) is never swapped, so the name stays too.
    assert (name.model, name.risk, name.auto_swap, name.no_swap_reason) == ("o1", "high", False, "catalog")
    sw = _swap(FIX / "trigger")
    assert f not in sw.new_contents
    assert [c["file"] for c in sw.skipped_catalog] == [f]


def test_html_option_values_and_code_samples():
    res = _scan("donvito")
    plan = [(f.line, f.model, f.kind) for f in res.findings if f.file == "src/templates/projectPlannerDemo.html"]
    assert plan == [(5, "gpt-4o-mini", "string_literal"), (6, "gpt-4o", "string_literal"),
                    (7, "gpt-4-turbo", "string_literal"), (8, "gpt-3.5-turbo", "string_literal")]   # not the <!-- --> one
    landing = [(f.line, f.model, f.kind, f.risk) for f in res.findings if f.file == "src/templates/landing.html"]
    # The quoted sample (low), and since 0.4.8 the visible "Models: gpt-4, gpt-3.5-turbo" list (doc, info).
    assert landing == [(4, "gpt-4", "doc", "low"), (6, "gpt-4", "doc", "info"), (6, "gpt-3.5-turbo", "doc", "info")]
    sw = _swap(FIX / "donvito")
    new = sw.new_contents["src/templates/projectPlannerDemo.html"].splitlines()
    assert new[6].strip() == '<option value="gpt-5.6-sol">GPT-4 Turbo</option>'
    assert "src/templates/landing.html" not in sw.new_contents   # code samples are docs


def test_django_template_conditions():
    res = _scan("pfd")
    row = _at(res, "django_workbench/workbench/templates/workbench/settings.html", 4)
    assert [f.model for f in row] == ["gpt-4.1-mini", "gpt-4.1-mini"]       # value="..." and {% if ... == '...' %}
    sw = _swap(FIX / "pfd")
    # 0.4.9: both options would become gpt-6-luna, so neither is renamed (value nor its {% if %}).
    assert "django_workbench/workbench/templates/workbench/settings.html" not in sw.new_contents
    assert {(d["line"], d["model"]) for d in sw.skipped_duplicate_id} == {(4, "gpt-4.1-mini"), (5, "gpt-4.1")}


def test_notebooks_cell_and_line():
    res = _scan("pfd")
    nb = [f for f in res.findings if f.file == "tutorials/getting_started.ipynb"]
    assert [(f.line, f.model, f.kind, f.language) for f in nb] == [(10, "gpt-4.1", "doc", "markdown"),
                                                                   (37, "gpt-4.1", "sdk_call", "python")]
    assert "Notebook cell 2, line 11." in nb[1].notes
    assert nb[1].risk == "high" and nb[1].snippet == 'model="gpt-4.1",'
    # 0.4.10: the settings dropdown keeps gpt-4.1 (both options would become gpt-6-luna), so the notebook
    # reference is not renamed either; it is listed under must_update_together with the kept option.
    sw = _swap(FIX / "pfd")
    assert "tutorials/getting_started.ipynb" not in sw.new_contents
    assert ("tutorials/getting_started.ipynb", 37, "gpt-4.1") in {
        (m["file"], m["line"], m["model"]) for m in sw.must_update_together if m["kind"] == "kept_definition"}
    # Without the dropdown the notebook cell is rewritten in place.
    import shutil
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copytree(FIX / "pfd" / "tutorials", Path(tmp) / "tutorials")
        sw = _swap(Path(tmp))
    text = sw.new_contents["tutorials/getting_started.ipynb"]
    data = json.loads(text)                                   # still valid JSON
    code = [c for c in data["cells"] if c["cell_type"] == "code"][0]
    assert any('model="gpt-6-luna"' in l for l in code["source"])
    assert code["outputs"][0]["text"] == ['model="gpt-4.1" printed in an output\n']   # outputs untouched
    assert "Uses gpt-4.1 in the example below." in text                             # markdown is docs


def test_notebook_that_is_not_json_is_ignored(tmp_path):
    res = _scan_text(tmp_path, "broken.ipynb", '{"cells": [ model="gpt-4" \n')
    assert not res.findings


def test_new_file_types():
    res = _scan("trigger")
    mdc, = [f for f in res.findings if f.file == ".cursor/rules/writing-tasks.mdc"]
    assert (mdc.line, mdc.model, mdc.kind, mdc.risk) == (15, "gpt-3.5-turbo", "sdk_call", "high")
    res = _scan("themefinder")
    assert [(f.line, f.model, f.language) for f in res.findings][:2] == [(4, "gpt-4.1-mini", "make"), (9, "gpt-4.1", "make")]
    res = _scan("livereview")
    assert [(f.line, f.model, f.kind, f.language) for f in res.findings] == [
        (4, "gemini-2.5-pro", "comment", "toml"), (5, "gpt-4", "comment", "toml"), (5, "gpt-3.5-turbo", "comment", "toml")]
    # roxygen output: one generated-file line by default, documentation findings with --include-generated
    res = _scan("epiviz")
    assert not res.findings and [(s.file, s.reason) for s in res.skipped] == [("man/llm_interpret.Rd", "generated")]
    res = _scan("epiviz", include_generated=True)
    assert [(f.line, f.model, f.kind) for f in res.findings] == [(8, "gpt-4.1-nano", "doc")]


def test_shell_claude_words_are_not_findings():
    res = _scan("lacp")
    assert [f.model for f in res.findings] == ["claude-3-5-haiku-20241022"]


def test_fix_does_not_report_prose_or_regex_as_flag_only():
    packs = load_packs()
    res = plan_fixes(FIX / "trigger", packs=packs)
    assert not [i for i in res.items if i.rule == "flag-only"]
    res = scan(FIX / "trigger", today=TODAY)
    reasons = {(f.line, f.model): f.no_swap_reason for f in res.findings
               if f.file.endswith("default-model-prices.json") or f.file.endswith("research-model.sh")}
    assert reasons[(4, "ft:gpt-3.5-turbo-1106")] == "fine_tune"
    assert reasons[(5, "gpt-3.5-turbo-1106")] == "regex" and reasons[(13, "o1")] == "regex"
    assert reasons[(12, "o1")] == "catalog" and reasons[(30, "gpt-3.5-turbo")] == "prose"
