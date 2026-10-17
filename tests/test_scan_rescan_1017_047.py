"""Regression fixtures from Chad's rerun of the 38 repos with 0.4.7 (17 Oct 2026, section 7).

Snippets are excerpts from public repos (shallow clones, 16 Oct 2026):
- Sam-Osian/PFD-toolkit django_workbench/workbench/views.py:3276-3278,3455-3460, services.py:73-76,
  templates/workbench/settings.html:28-37
- gexijin/RTutor vignettes/coverage_20250820_103955.html (head, covr tabset, source row 260-263; shortened,
  saved with LF line endings)
- ukhsa-collaboration/epiviz README.Rmd:105-111 and its rendered README.html:494-500
- i-dot-ai/themefinder Makefile:10-22
- AVIDS2/memorix src/store/orama-store.ts:800-812
- Dicklesworthstone/ultimate_mcp_client mcp_client_multi.py:578-584
"""
import shutil

from conftest import ROOT, TODAY
from migration_kit import swapper
from migration_kit.fixer.engine import plan_fixes
from migration_kit.packs import load_packs
from migration_kit.scanner import scan

FIX = ROOT / "tests" / "fixtures" / "scan_accuracy" / "rescan_1017_047"


def _scan(sub, **kw):
    return scan(FIX / sub, today=TODAY, **kw)


def _swap(root):
    packs = load_packs()
    return swapper.plan(root, swapper.mapping_from_packs(packs), packs)


def _at(res, file, line):
    return [f for f in res.findings if f.file == file and f.line == line]


def _write(tmp_path, files):
    for name, text in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


# ---------------------------------------------------------------- 1. allow-lists swap with their values

VIEWS = "django_workbench/workbench/views.py"
SETTINGS = "django_workbench/workbench/templates/workbench/settings.html"


def test_pfd_allow_list_and_default_stay_with_the_kept_dropdown():
    """0.4.10: the dropdown keeps both options (they would both become gpt-6-luna), so the default and the
    allow-list keep the old ids too (0.4.9 renamed the default and added gpt-6-luna to the allow-list,
    an id the dropdown never posts). The default is listed with the kept option."""
    sw = _swap(FIX / "pfd")
    assert VIEWS not in sw.new_contents and SETTINGS not in sw.new_contents
    assert not [c for c in sw.changes if c.action == "added"]
    kept = {(m["file"], m["line"], m["model"]) for m in sw.must_update_together if m["kind"] == "kept_definition"}
    assert kept == {(VIEWS, 8, "gpt-4.1-mini"), ("django_workbench/workbench/services.py", 3, "gpt-4.1-mini")}
    g = {x["model"]: x for x in sw.kept_definitions}["gpt-4.1-mini"]
    assert g["kept"] == [{"file": SETTINGS, "line": 6, "reason": "duplicate_id"}]
    # Every value the template can post still passes the (unchanged) allow-list.
    import re
    views = (FIX / "pfd" / VIEWS).read_text().splitlines()
    allowed = set(re.findall(r'"([^"]+)"', views[1]))
    posted = set(re.findall(r'<option value="([^"]+)"', (FIX / "pfd" / SETTINGS).read_text()))
    assert posted <= allowed


def test_pfd_collapsed_dropdown_and_allow_list_are_reported():
    sw = _swap(FIX / "pfd")
    got = {(c["file"], c["container"].split(" ")[0], c["target"], tuple(c["old"]), c["applied"]) for c in sw.collapsed}
    assert got == {(SETTINGS, "<select>", "gpt-6-luna", ("gpt-4.1", "gpt-4.1-mini"), False)}
    # Only gpt-4.1-mini is still renamed elsewhere (the dropdown isn't), so the list gets one new id.
    assert not sw.allow_list_merges
    assert sw.summary()["collapsed_targets"] == sw.collapsed
    assert any(w.startswith("COLLAPSED " + SETTINGS) and "not applied" in w for w in sw.warnings())
    fx = plan_fixes(FIX / "pfd")
    assert any(i.rule == "collapsed-ids" and i.file == SETTINGS for i in fx.items)
    assert any(i.rule == "duplicate-id" and i.file == SETTINGS for i in fx.items)


def test_pfd_scan_marks_allow_list_swappable():
    row = _at(_scan("pfd"), VIEWS, 2)
    assert [(f.model, f.kind, f.risk, f.auto_swap, f.no_swap_reason) for f in row] == [
        ("gpt-4.1-mini", "allow_list", "low", True, None), ("gpt-4.1", "allow_list", "low", True, None)]
    assert any("adds the replacement id" in n for n in row[0].notes)


def test_allow_list_forms_get_the_new_id(tmp_path):
    _write(tmp_path, {
        "a.py": ('MODEL = "gpt-4.1-nano"\n'
                 'if m in ("gpt-4.1-nano",):\n    pass\n'
                 'if m not in ["gpt-4.1-nano", "custom"]:\n    pass\n'),
        "b.ts": ("const model = 'o3-mini'\n"
                 "if (['o1-mini', 'o3-mini'].includes(m)) {}\n"
                 "const fam = new Set([\"o3-mini\"]).has(m)\n"),
        "c.php": "<?php\n$model = 'gpt-4-turbo';\nif (in_array($m, array('gpt-4-turbo', 'x'), true)) {}\n",
    })
    sw = _swap(tmp_path)
    a = sw.new_contents["a.py"].splitlines()
    assert a[1] == 'if m in ("gpt-4.1-nano", "gpt-5.6-luna",):'
    assert a[3] == 'if m not in ["gpt-4.1-nano", "custom", "gpt-5.6-luna"]:'
    b = sw.new_contents["b.ts"].splitlines()
    assert b[1] == "if (['o1-mini', 'o3-mini', 'gpt-5.6-sol'].includes(m)) {}"
    assert b[2] == 'const fam = new Set(["o3-mini", "gpt-5.6-sol"]).has(m)'
    c = sw.new_contents["c.php"].splitlines()
    assert c[2] == "if (in_array($m, array('gpt-4-turbo', 'x', 'gpt-5.6-sol'), true)) {}"
    compile(sw.new_contents["a.py"], "a.py", "exec")      # still valid Python


def test_allow_list_left_alone_when_nothing_else_is_swapped(tmp_path):
    _write(tmp_path, {"a.py": 'if m in {"gpt-4.1", "gpt-4.1-mini"}:\n    pass\n'})
    sw = _swap(tmp_path)
    assert not sw.new_contents
    assert ("a.py", 1, "gpt-4.1") in sw.skipped_name_checks
    f = scan(tmp_path, today=TODAY).findings
    assert {(x.kind, x.auto_swap, x.no_swap_reason) for x in f} == {("allow_list", False, "allow_list")}


def test_multiline_allow_list_and_prefix_checks_must_update_together(tmp_path):
    _write(tmp_path, {
        "a.py": ('DEFAULT = "gpt-4o"\n'
                 'if m in ("gpt-4o", other):\n    pass\n'          # not only quoted ids: can't extend safely
                 'if m.startswith("gpt-4o"):\n    pass\n'          # prefix check: renaming changes the logic
                 'assert "gpt-4o" in names\n'),                     # needle: substring or membership
    })
    sw = _swap(tmp_path)
    must = {(w["line"], w["model"], w["kind"]) for w in sw.must_update_together}
    assert must == {(2, "gpt-4o", "allow_list"), (4, "gpt-4o", "name_check"), (6, "gpt-4o", "name_check")}
    assert sw.new_contents["a.py"].splitlines()[3] == 'if m.startswith("gpt-4o"):'
    assert all(w.startswith("MUST UPDATE TOGETHER a.py:") for w in sw.warnings())
    assert sw.summary()["must_update_together"][0]["related"] == ["gpt-4o"]
    res = scan(tmp_path, today=TODAY)
    pre = _at(res, "a.py", 4)[0]
    assert (pre.kind, pre.auto_swap, pre.no_swap_reason) == ("name_check", False, "must_update_together")
    assert any(n.startswith("Must update together") for n in pre.notes)
    fx = plan_fixes(tmp_path)
    assert {i.line for i in fx.items if i.rule == "must-update-together"} == {2, 4, 6}


def test_family_check_on_an_unmapped_id_must_update_together(tmp_path):
    # o3 itself isn't in the mapping, but o3-mini is renamed, so `startsWith("o3")` stops matching it.
    _write(tmp_path, {"a.ts": "const model = 'o3-mini'\nif (m.startsWith('o3')) {}\n"})
    sw = _swap(tmp_path)
    assert [(w["line"], w["model"], w["related"]) for w in sw.must_update_together] == [(2, "o3", ["o3-mini"])]
    f = _at(scan(tmp_path, today=TODAY), "a.ts", 2)[0]
    assert (f.kind, f.no_swap_reason) == ("name_check", "must_update_together")


def test_equality_and_prefix_list_forms(tmp_path):
    _write(tmp_path, {
        "a.py": ('if m == "gpt-4.1-nano":\n    pass\n'
                 'if m in ("gpt-4.1-nano"):\n    pass\n'),       # a string, so a substring test
        "b.ts": "const r = ['o3-mini'].some(p => m.startsWith(p))\n",
    })
    res = scan(tmp_path, today=TODAY)
    kinds = {(f.file, f.line): f.kind for f in res.findings}
    assert kinds[("a.py", 1)] not in ("name_check", "allow_list")    # `==` is swapped in place
    assert kinds[("a.py", 3)] == "name_check"
    assert kinds[("b.ts", 1)] == "name_check"
    sw = _swap(tmp_path)
    # 0.4.9: `==` is allow-list-like. Nothing else renames gpt-4.1-nano here, so it is left alone.
    assert "a.py" not in sw.new_contents
    assert ("a.py", 1, "gpt-4.1-nano") in sw.skipped_name_checks


def test_collapsed_ids_in_a_dict_are_reported(tmp_path):
    _write(tmp_path, {"p.py": 'PRICES = {\n    "gpt-4.1": 2.0,\n    "gpt-4.1-mini": 0.4,\n}\nX = ["gpt-4", "o1"]\n'})
    sw = _swap(tmp_path)
    got = {(c["line"], c["target"], tuple(c["old"])) for c in sw.collapsed}
    assert got == {(1, "gpt-6-luna", ("gpt-4.1", "gpt-4.1-mini")), (5, "gpt-5.6-sol", ("gpt-4", "o1"))}
    assert not sw.new_contents          # 0.4.9: collapsed means not applied


# ---------------------------------------------------------------- 2-3. generated HTML

def test_covr_coverage_report_is_generated():
    res = _scan("rtutor")
    assert not res.findings
    assert [(s.file, s.reason) for s in res.skipped] == [("vignettes/coverage_20250820_103955.html", "generated")]
    assert _scan("rtutor", include_generated=True).findings


def test_coverage_heuristics(tmp_path):
    body = '<pre>model = "gpt-4o"</pre>\n'
    _write(tmp_path, {"htmlcov/index.html": f"<html>{body}",
                      "cov/coverage.html": f"<html><h1>covr report</h1>{body}",
                      "pages/plain.html": f'<html><select><option value="gpt-4o">x</option></select>\n'})
    res = scan(tmp_path, today=TODAY)
    assert {s.file for s in res.skipped} == {"htmlcov/index.html", "cov/coverage.html"}
    assert {f.file for f in res.findings} == {"pages/plain.html"}


def test_rendered_readme_html_is_generated():
    res = _scan("epiviz")
    assert {f.file for f in res.findings} == {"README.Rmd"}
    assert [(s.file, s.reason) for s in res.skipped] == [("README.html", "generated")]


def test_html_with_same_stem_source_is_generated(tmp_path):
    page = '<option value="gpt-4o">x</option>\n'
    _write(tmp_path, {"a/guide.html": page, "a/guide.qmd": "text\n", "b/notes.htm": page, "b/notes.md": "text\n",
                      "c/index.html": page, "c/other.md": "text\n"})
    res = scan(tmp_path, today=TODAY)
    assert {s.file for s in res.skipped} == {"a/guide.html", "b/notes.htm"}
    assert {f.file for f in res.findings} == {"c/index.html"}


# ---------------------------------------------------------------- 4. echo / printf messages are prose

def test_makefile_echo_is_prose():
    res = _scan("themefinder")
    l4 = _at(res, "Makefile", 4)          # Makefile:13
    assert [(f.model, f.kind, f.risk, f.auto_swap, f.no_swap_reason) for f in l4] == [
        ("gpt-4.1-mini", "prose", "low", False, "prose")]
    l8 = _at(res, "Makefile", 9)          # --judge-model gpt-4.1 is a real argument
    assert l8 and l8[0].auto_swap
    sw = _swap(FIX / "themefinder")
    assert "gpt-4.1-mini" in sw.new_contents["Makefile"].splitlines()[3]
    assert ("Makefile", 4, "gpt-4.1-mini", "prose") in sw.skipped_unsafe


def test_echo_forms(tmp_path):
    _write(tmp_path, {"s.sh": ('echo "Using gpt-4o"\n'
                               'printf "model %s\\n" gpt-4o\n'
                               'echo gpt-4o > model.txt\n'
                               'MODEL=$(echo gpt-4o)\n'
                               'echo "MODEL=gpt-4o" >> .env\n'
                               'echo "done" && run --model gpt-4o\n'
                               'echo "warn: gpt-4o" >&2\n')})
    res = scan(tmp_path, today=TODAY)
    prose = {f.line for f in res.findings if f.kind == "prose"}
    assert prose == {1, 2, 7}


# ---------------------------------------------------------------- 5. full stop after a non-model word

def test_full_stop_after_non_model_word_is_not_a_finding(tmp_path):
    assert not [f for f in _scan("memorix").findings if f.model.startswith("claude-mem")]
    _write(tmp_path, {"a.ts": "// adopted from claude-mem.\n// use claude-3-haiku.\n// or gpt-4o.\n// see claude-code\n"})
    got = {(f.line, f.model) for f in scan(tmp_path, today=TODAY).findings}
    assert (1, "claude-mem") not in got
    assert {(2, "claude-3-haiku"), (3, "gpt-4o"), (4, "claude-code")} <= got


# ---------------------------------------------------------------- 6. visible HTML text listing models

def test_visible_model_list_is_info_doc(tmp_path):
    _write(tmp_path, {"p.html": ('<div class="x">Models: gpt-4, gpt-3.5-turbo</div>\n'
                                 '<p>Default model: gpt-4.1-nano</p>\n'
                                 '<option value="gpt-4o">gpt-4o</option>\n')})
    res = scan(tmp_path, today=TODAY)
    got = [(f.line, f.model, f.kind) + ((f.risk,) if f.line == 1 else ()) for f in res.findings]
    assert got == [(1, "gpt-4", "doc", "info"), (1, "gpt-3.5-turbo", "doc", "info"), (3, "gpt-4o", "string_literal")]
    assert "p.html" not in _swap(tmp_path).new_contents or "Models: gpt-4," in _swap(tmp_path).new_contents["p.html"]


# ---------------------------------------------------------------- 7. startsWith("o1-")

def test_prefix_check_with_dash_is_a_name_check():
    res = _scan("ultimate")
    row = _at(res, "mcp_client_multi.py", 5)       # :582
    assert [(f.model, f.kind, f.auto_swap) for f in row] == [("o1", "name_check", False), ("o3", "name_check", False)]
    assert row[0].risk == "low" and any("Prefix check" in n for n in row[0].notes)
    assert not _swap(FIX / "ultimate").new_contents


def test_dash_prefix_check_must_update_together_when_family_is_swapped(tmp_path):
    _write(tmp_path, {"a.py": 'MODEL = "o3-mini"\nif m.startswith("o3-"):\n    pass\n'})
    sw = _swap(tmp_path)
    assert [(w["line"], w["model"], w["related"]) for w in sw.must_update_together] == [(2, "o3", ["o3-mini"])]


def test_prefix_check_with_dot_is_not_swapped(tmp_path):
    _write(tmp_path, {"a.ts": "const m = 'gpt-4'\nif (m.startsWith('gpt-4.')) {}\nconst k = \"o1-\"\n"})
    res = scan(tmp_path, today=TODAY)
    assert [(f.line, f.kind) for f in res.findings if f.line > 1] == [(2, "name_check")]
    assert _swap(tmp_path).new_contents["a.ts"].splitlines()[1] == "if (m.startsWith('gpt-4.')) {}"


def test_cli_swap_prints_warnings(tmp_path, capsys, monkeypatch):
    from migration_kit import cli
    repo = tmp_path / "repo"
    shutil.copytree(FIX / "pfd", repo)
    monkeypatch.setattr(cli, "_patch_licence", lambda a, feature: True)
    assert cli.main(["swap", str(repo), "--out", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert "WARNING: 2 check(s) must be updated together" in out and "COLLAPSED" in out
    assert "KEPT gpt-4.1-mini (not renamed to gpt-6-luna anywhere)" in out
    assert "MUST UPDATE TOGETHER django_workbench/workbench/views.py:8 gpt-4.1-mini" in out
