"""Regression fixtures from Chad's rerun of the 38 repos with 0.4.5 (16 Oct 2026, section 5).

Snippets are excerpts from public repos (shallow clones, 16 Oct 2026):
- donvito/ai-backends src/templates/summarizeDemo.html (head + lines 179, 210-225, 559; the
  `<option>` line and `// (excerpt)` are added to check markup outside <script> is skipped),
  sample-curl.sh:1-30, idea-http-scripts/WebSearch.http
- triggerdotdev/trigger.dev docs/snippets/code/openai-retry.mdx
- plasma-umass/coz coz (shebang + lines 843-856, extensionless Python)
- 0xNyk/lacp bin/lacp-stream (shebang + lines 200-217, extensionless bash)
- Lapis0x0/obsidian-yolo src/constants.ts:640-665, src/settings/schema/migrations/1_to_2.ts:155-165,645-650,
  src/utils/model-id-utils.ts:100-125
- SpectrAI-Initiative/InnoClaw src/lib/agent/cost-tracker.ts:60-80
`notscripts/` is synthetic: extensionless files that must not be scanned.
"""
import json

from conftest import ROOT, TODAY
from migration_kit import swapper
from migration_kit.fixer.engine import plan_fixes
from migration_kit.packs import load_packs
from migration_kit.scanner import scan

FIX = ROOT / "tests" / "fixtures" / "scan_accuracy" / "rescan_1016_045"


def _scan(sub, **kw):
    return scan(FIX / sub, today=TODAY, **kw)


def _swap(root):
    packs = load_packs()
    return swapper.plan(root, swapper.mapping_from_packs(packs), packs)


# Gap 1: .html <script> blocks, .mdx code fences, .sh, .http and shebang scripts.

def test_html_scans_script_blocks_and_quoted_markup_values():
    res = _scan("donvito")
    html = [f for f in res.findings if f.file == "src/templates/summarizeDemo.html"]
    nano = [f for f in html if f.model == "gpt-4.1-nano"]
    assert [f.line for f in nano] == [14, 26, 26]                # <option value> (0.4.7) + value/label in <script>
    assert all(f.language == "html" and f.risk == "high" for f in nano)
    assert [f.column for f in html if f.line == 14] == [18]      # the attribute value, not the unquoted label
    assert any(f.model == "gpt-4o-mini" and f.line == 30 for f in html)   # openai/gpt-4o-mini


def test_html_swap_rewrites_option_value_not_label():
    res = _swap(FIX / "donvito")
    new = res.new_contents["src/templates/summarizeDemo.html"].splitlines()
    assert new[13] == '  <option value="gpt-5.6-luna">gpt-4.1-nano</option>'
    assert "gpt-5.6-luna" in new[25]


def test_shell_and_http_request_files():
    res = _scan("donvito")
    sh = [f for f in res.findings if f.file == "sample-curl.sh"]
    assert [(f.line, f.model, f.kind, f.risk, f.language) for f in sh] == [(16, "gpt-4.1-nano", "sdk_call", "high", "shell")]
    http = [f for f in res.findings if f.file == "idea-http-scripts/WebSearch.http"]
    assert [(f.line, f.model, f.risk, f.language) for f in http] == [(41, "gpt-4.1-nano", "high", "http")]


def test_mdx_code_fence_is_code_and_prose_is_doc(tmp_path):
    res = _scan("trigger")
    hit = [f for f in res.findings if f.file == "docs/snippets/code/openai-retry.mdx"]
    assert [(f.line, f.model, f.kind, f.risk) for f in hit] == [(23, "gpt-3.5-turbo", "sdk_call", "high")]
    (tmp_path / "page.mdx").write_text("# Models\n\nWe used `gpt-3.5-turbo` before.\n\n```ts\nconst m = 'gpt-3.5-turbo'\n```\n")
    res = scan(tmp_path, today=TODAY)
    assert [(f.line, f.kind, f.risk) for f in res.findings] == [(3, "doc", "low"), (6, "string_literal", "high")]
    assert not scan(tmp_path, today=TODAY, include_docs=False).findings      # .mdx is docs for --no-docs


def test_extensionless_shebang_scripts():
    coz = _scan("coz")
    py = {f.model: f for f in coz.findings if f.file == "coz"}
    assert {"gpt-4o", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo", "o1", "o3-mini", "o4-mini"} <= set(py)
    assert py["gpt-3.5-turbo"].language == "python" and py["gpt-3.5-turbo"].line == 9
    lacp = _scan("lacp")
    sh = {(f.line, f.model): f for f in lacp.findings if f.file == "bin/lacp-stream"}
    assert (12, "o4-mini") in sh and sh[(12, "o4-mini")].risk == "high" and sh[(12, "o4-mini")].language == "shell"
    assert (12, "o3") in sh and (13, "o3") in sh                  # MODELS=("o3" ...), DEFAULT_MODEL="o3"


def test_extensionless_files_without_a_known_shebang_are_skipped(tmp_path):
    res = _scan("notscripts")
    assert res.files_scanned == 0 and not res.findings           # no shebang, ruby shebang, vendored
    assert [s.file for s in res.skipped] == ["vendor/tool"]      # vendored shebang script: one summary line
    (tmp_path / "blob").write_bytes(b"#!/bin/sh\n\x00\x01binary gpt-4.1-nano\n")   # NUL bytes: binary
    (tmp_path / "tool").write_bytes(b"#!/usr/bin/env -S node --no-warnings\nconst m = 'gpt-4.1-nano'\n")
    res = scan(tmp_path, today=TODAY)
    assert [(f.file, f.language) for f in res.findings] == [("tool", "javascript")]


# Gap 2: router / provider-prefixed short ids.

def test_openai_prefixed_short_ids_are_hits():
    res = _scan("yolo")
    const = {(f.line, f.model) for f in res.findings if f.file == "src/constants.ts"}
    assert (13, "o4-mini") in const and (14, "o4-mini") in const   # id: 'openai/o4-mini' and model: 'o4-mini'
    assert (20, "o3") in const
    mig = {(f.line, f.model) for f in res.findings if f.file == "src/settings/schema/migrations/1_to_2.ts"}
    assert {(6, "o1"), (10, "o1"), (16, "o1")} <= mig
    assert sum(1 for f in res.findings if f.file.endswith("1_to_2.ts") and f.line == 16 and f.model == "o1") == 2


def test_router_prefix_variants(tmp_path):
    (tmp_path / "models.ts").write_text(
        'a = "openrouter/openai/o1"\n'
        "b = 'azure/o3-mini'\n"
        'c = "assets/o1"\n'                   # not a provider prefix
        'd = "openai/o1/extra"\n'             # id does not end the string
        'e = "see openai/o1 docs"\n')         # prose inside a string
    (tmp_path / "cfg.yaml").write_text("model: litellm/openai/o4-mini\npath: openai/o1/x\n")
    res = scan(tmp_path, today=TODAY)
    got = {(f.file, f.line, f.model) for f in res.findings}
    assert got == {("models.ts", 1, "o1"), ("models.ts", 2, "o3-mini"), ("cfg.yaml", 1, "o4-mini")}


def test_prefixed_short_id_swaps_like_long_ids(tmp_path):
    (tmp_path / "m.ts").write_text("const x = { id: 'openai/o4-mini' }\n")
    res = _swap(tmp_path)
    assert res.new_contents["m.ts"] == "const x = { id: 'openai/gpt-5.6-terra' }\n"


# Gap 3: model-name checks are low, never rewritten.

def test_name_checks_are_low_not_high():
    res = _scan("innoclaw")
    o1 = [f for f in res.findings if f.model == "o1"]
    assert len(o1) == 1 and o1[0].kind == "name_check" and o1[0].risk == "low"
    yolo = [f for f in _scan("yolo").findings if f.file == "src/utils/model-id-utils.ts" and f.model == "o1"]
    assert len(yolo) == 1 and yolo[0].kind == "name_check" and yolo[0].risk == "low"
    assert any("not a pinned model" in n for n in yolo[0].notes)


def test_name_check_forms(tmp_path):
    (tmp_path / "a.py").write_text(
        'if m.startswith(("o3-mini", "gpt-4")): pass\n'
        'if "gpt-3.5-turbo" in model_name: pass\n'
        'client.chat.completions.create(model="gpt-4")\n')
    (tmp_path / "b.go").write_text('if strings.HasPrefix(m, "o1") { }\n')
    (tmp_path / "c.php").write_text("<?php if (str_contains($m, 'gpt-4')) {}\n")
    (tmp_path / "d.rs").write_text('if self.model.starts_with("o1") {}\n')
    res = scan(tmp_path, today=TODAY)
    kinds = {(f.file, f.line, f.model): (f.kind, f.risk) for f in res.findings}
    assert kinds[("a.py", 1, "o3-mini")] == ("name_check", "low")
    assert kinds[("a.py", 1, "gpt-4")] == ("name_check", "low")
    assert kinds[("a.py", 2, "gpt-3.5-turbo")] == ("name_check", "low")
    assert kinds[("a.py", 3, "gpt-4")] == ("sdk_call", "high")
    assert kinds[("b.go", 1, "o1")] == ("name_check", "low")
    assert kinds[("c.php", 1, "gpt-4")] == ("name_check", "low")
    assert kinds[("d.rs", 1, "o1")] == ("name_check", "low")


def test_name_checks_do_not_fail_ci(tmp_path):
    from migration_kit.cli import main
    (tmp_path / "f.ts").write_text('export const isO = (s: string) => s.includes("o1") || s.startsWith("o3-mini")\n')
    assert main(["scan", str(tmp_path), "--fail-on-high", "--out", str(tmp_path / "out")]) == 0


def test_swap_and_fix_leave_name_checks_alone():
    for sub, rel in (("innoclaw", "src/lib/agent/cost-tracker.ts"), ("yolo", "src/utils/model-id-utils.ts")):
        res = _swap(FIX / sub)
        assert rel not in res.new_contents, rel
        assert any(f == rel and m == "o1" for f, _l, m in res.skipped_name_checks)
        fx = plan_fixes(FIX / sub)
        assert rel not in fx.new_contents, rel


# Gap 4: o1-pro is flag-only and says why.

def test_o1_pro_scan_note():
    res = scan(ROOT / "tests" / "fixtures" / "scan_accuracy" / "rescan_1016" / "pressidium", today=TODAY)
    pro = [f for f in res.findings if f.model == "o1-pro"]
    assert pro and all(not f.auto_swap for f in pro)
    notes = " ".join(pro[0].notes)
    assert "gpt-5.6-sol with reasoning.mode set to pro" in notes and "drop pro mode" in notes
    assert "Flag-only" in notes and "2026-10-23" in notes
    assert pro[0].suggested == "gpt-5.6-sol" and pro[0].shutdown == "2026-10-23"
    from migration_kit.scanner import to_markdown
    assert "`gpt-5.6-sol` (by hand; not auto-swapped)" in to_markdown(res)


def test_o1_pro_in_mapping_as_flag_only(tmp_path, capsys):
    import yaml
    from migration_kit.cli import main
    out = tmp_path / "m.yaml"
    assert main(["mapping", "--out", str(out)]) == 0
    data = yaml.safe_load(out.read_text())
    assert "o1-pro" not in data["mappings"] and "o1-pro-2025-03-19" not in data["mappings"]
    fo = data["flag_only"]["o1-pro"]
    assert fo["shutdown"] == "2026-10-23" and fo["replacement"] == "gpt-5.6-sol"
    assert "reasoning.mode set to pro" in fo["why"] and "not rewritten" in fo["why"]
    assert "o1-pro-2025-03-19" in data["flag_only"]
    m = swapper.load_mapping(out)                     # the printed mapping still loads for --mapping
    assert "o1-pro" not in m.replacements and m.replacements["o1"] == "gpt-5.6-sol"


def test_o1_pro_fix_item(tmp_path):
    (tmp_path / "app.py").write_text(
        "from openai import OpenAI\nclient = OpenAI()\n"
        'r = client.responses.create(model="o1-pro", input="hi")\n')
    (tmp_path / "models.json").write_text(json.dumps({"model": "o1-pro-2025-03-19"}) + "\n")
    fx = plan_fixes(tmp_path)
    assert not fx.new_contents
    flag = {(i.file, i.model): i for i in fx.items if i.rule == "flag-only"}
    assert set(flag) == {("app.py", "o1-pro"), ("models.json", "o1-pro-2025-03-19")}
    it = flag[("app.py", "o1-pro")]
    assert it.status == "manual" and it.target == "gpt-5.6-sol" and "2026-10-23" in it.message
    assert "reasoning.mode set to pro" in it.message and "Not switched automatically" in it.message


def test_html_script_tag_in_comment_or_markup(tmp_path):
    (tmp_path / "p.html").write_text(
        "<!-- old <script> block removed -->\n"
        '<p>Default model: gpt-4.1-nano</p>\n'
        '<script>const m = "gpt-4.1-nano"; </script> <b>gpt-4.1-nano</b>\n'
        "<script type=\"module\">\n"
        "  // gpt-4.1-nano in a comment\n"
        "  run('gpt-4.1-nano')\n"
        "</script>\n"
        "<footer>gpt-4.1-nano</footer>\n")
    res = scan(tmp_path, today=TODAY)
    got = [(f.line, f.kind, f.risk) for f in res.findings]
    assert got[0][0] == 3 and got[0][2] == "high"
    assert (5, "comment", "low") in got and (6, "string_literal", "high") in got
    assert not [g for g in got if g[0] in (1, 2, 8)]
