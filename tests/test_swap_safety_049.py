"""0.4.9: swap safety, from Chad's swap test of 0.4.8 (17 Oct 2026, section 8 of the rescan write-up).

Fixtures in tests/fixtures/scan_accuracy/rescan_1017_048/ are short excerpts from public repos
(shallow clones, 16 Oct 2026), named in each file's first line:
- Lapis0x0/obsidian-yolo src/constants.ts, src/utils/llm/openrouter-model-capabilities.ts,
  src/settings/schema/migrations/{0_to_1,5_to_6,7_to_8}.ts
- glowingjade/obsidian-smart-composer src/utils/chat/apply.ts
- triggerdotdev/trigger.dev llm-model-catalog model-catalog.json, default-model-prices.json, sync.test.ts,
  scripts/generate-model-catalog.sh, apps/webapp/test/otlpExporter.test.ts
- Sam-Osian/PFD-toolkit tests/model_comparison.py
- i-dot-ai/themefinder evals/benchmark.py, src/themefinder/llm_batch_processor.py
- donvito/ai-backends src/config/models.json, src/templates/landing.html
- yaml/: synthetic
"""
import ast
import json
import re
import shutil
import subprocess

import pytest
from conftest import ROOT, TODAY
from migration_kit import swapper
from migration_kit.fixer.engine import plan_fixes
from migration_kit.packs import load_packs
from migration_kit.scanner import scan
from migration_kit.swapsafe import extend_equality, parse_structure, token_hold

FIX = ROOT / "tests" / "fixtures" / "scan_accuracy" / "rescan_1017_048"


def _swap(root):
    packs = load_packs()
    return swapper.plan(root, swapper.mapping_from_packs(packs), packs)


def _kept_refs(sw, file=None):
    """0.4.10: references left on an old id because a definition of it is kept."""
    return {(m["file"], m["line"], m["model"]) for m in sw.must_update_together
            if m["kind"] == "kept_definition" and (file is None or m["file"] == file)}


def _text(sw, root, rel):
    return sw.new_contents.get(rel, (root / rel).read_text())


def _write(tmp_path, files):
    for name, text in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


def _ts_dup_keys(src):
    """Duplicate quoted keys per object literal, line-based (enough for the fixtures)."""
    out = []
    for block in re.findall(r"=\s*\{(.*?)\n\}", src, re.S):
        keys = re.findall(r"^\s*'([^']+)'\s*:", block, re.M)
        out += [k for k in set(keys) if keys.count(k) > 1]
    return out


# ---------------------------------------------------------------- 1. duplicate keys

def test_yolo_price_table_keys_that_would_collide_are_skipped():
    sw = _swap(FIX / "yolo")
    new = sw.new_contents["src/constants.ts"]
    assert not _ts_dup_keys(new)
    assert "  'gpt-4.1': { input: 2.0, output: 8.0 }," in new          # kept: 4 keys would become gpt-6-luna
    assert "  'gpt-4o-mini': { input: 0.15, output: 0.6 }," in new
    assert "  'gpt-5.6-luna': { input: 0.1, output: 0.4 }," in new     # gpt-4.1-nano: unique target, renamed
    keys = {(d["file"], d["line"], d["model"], d["key"]) for d in sw.skipped_duplicate_key}
    assert {("src/constants.ts", n, m, "gpt-6-luna") for n, m in
            ((37, "gpt-4.1"), (38, "gpt-4.1-mini"), (40, "gpt-4o"), (41, "gpt-4o-mini"))} <= keys
    assert all("TS1117" in d["reason"] for d in sw.skipped_duplicate_key)
    c = [x for x in sw.collapsed if x["file"] == "src/constants.ts" and x["container"] == "object/dict keys"]
    assert c == [{"file": "src/constants.ts", "line": 35, "container": "object/dict keys", "target": "gpt-6-luna",
                  "old": ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"], "applied": False}]


def test_openrouter_capabilities_keys_including_batch_variants():
    sw = _swap(FIX / "yolo")
    f = "src/utils/llm/openrouter-model-capabilities.ts"
    new = sw.new_contents[f]
    assert not _ts_dup_keys(new)
    skipped = {(d["line"], d["model"], d["key"]) for d in sw.skipped_duplicate_key if d["file"] == f}
    # gpt-4.1 and gpt-4.1-mini (and their :batch keys) would all become gpt-6-luna[:batch];
    # gpt-3.5-turbo and o4-mini would both become gpt-5.6-terra.
    assert {(8, "gpt-4.1", "gpt-6-luna"), (9, "gpt-4.1-mini", "gpt-6-luna"), (10, "gpt-4.1-mini", "gpt-6-luna:batch"),
            (12, "gpt-4.1", "gpt-6-luna:batch"), (6, "gpt-3.5-turbo", "gpt-5.6-terra"), (15, "o4-mini", "gpt-5.6-terra")} == skipped
    assert "  'gpt-5.6-sol': { context: 200000, modalities: ['text'] }," in new      # o3-mini: unique, renamed


def test_existing_key_blocks_a_rename_and_the_fix_lists_it(tmp_path):
    _write(tmp_path, {"p.py": 'PRICES = {\n    "gpt-6-luna": 1.0,\n    "gpt-4o": 2.5,\n}\nMODEL = "gpt-4o"\n',
                      "c.json": '{"gpt-4o": {"in": 2.5}, "gpt-4o-mini": {"in": 0.15}, "x": "gpt-4o"}\n'})
    sw = _swap(tmp_path)
    p = _text(sw, tmp_path, "p.py")
    assert ast.literal_eval(p.split("=", 1)[1].split("\n}")[0] + "\n}") == {"gpt-6-luna": 1.0, "gpt-4o": 2.5}
    d = [x for x in sw.skipped_duplicate_key if x["file"] == "p.py"]
    assert [(x["line"], x["model"], x["target"]) for x in d] == [(3, "gpt-4o", "gpt-6-luna")]
    assert "one already uses it" in d[0]["reason"]
    # 0.4.10: the gpt-4o key is kept, so MODEL (which looks it up) and "x" keep gpt-4o too and are listed.
    assert not sw.new_contents
    assert 'MODEL = "gpt-4o"' in p
    assert _kept_refs(sw) == {("p.py", 5, "gpt-4o"), ("c.json", 1, "gpt-4o")}
    data = json.loads(_text(sw, tmp_path, "c.json"))
    assert set(data) == {"gpt-4o", "gpt-4o-mini", "x"} and data["x"] == "gpt-4o"
    fx = plan_fixes(tmp_path)
    assert {(i.file, i.line) for i in fx.items if i.rule == "duplicate-key"} == {("p.py", 3), ("c.json", 1)}
    assert {(i.file, i.line) for i in fx.items if i.rule == "kept-definition"} == {("p.py", 5), ("c.json", 1)}


def test_trigger_model_catalog_json_is_not_swapped():
    sw = _swap(FIX / "trigger")
    f = "internal-packages/llm-model-catalog/src/model-catalog.json"
    assert f not in sw.new_contents
    cat = {c["file"]: c for c in sw.skipped_catalog}
    assert cat[f]["models"] == ["gpt-4o", "gpt-4o-mini"] and cat[f]["count"] == 2


def test_yaml_mapping_keys_and_list_items():
    sw = _swap(FIX / "yaml")
    new = sw.new_contents["config/models.yaml"]
    import yaml
    assert yaml.safe_load(new)["pricing"] == {"gpt-4o": 2.5, "gpt-4o-mini": 0.15, "gpt-5": 1.25}
    names = [m["name"] for m in yaml.safe_load(new)["models"]]
    assert names == ["gpt-4.1", "gpt-4.1-mini", "gpt-5.6-luna"] and len(set(names)) == 3
    assert {(d["line"], d["model"]) for d in sw.skipped_duplicate_key} == {(3, "gpt-4o"), (4, "gpt-4o-mini")}
    assert {(d["line"], d["model"]) for d in sw.skipped_duplicate_id} == {(7, "gpt-4.1"), (9, "gpt-4.1-mini")}


# ---------------------------------------------------------------- 2. duplicate ids in lists

def test_yolo_default_chat_models_keep_unique_ids():
    sw = _swap(FIX / "yolo")
    new = sw.new_contents["src/constants.ts"]
    ids = re.findall(r"id: '([^']+)'", new)
    assert len(ids) == len(set(ids)), ids
    assert ids == ["openai/gpt-4.1", "openai/gpt-4.1-mini", "openai/gpt-5.6-luna", "openai/gpt-4o", "openai/gpt-4o-mini"]
    # The whole entry is left as it was, so id and model stay consistent.
    assert "    id: 'openai/gpt-4o',\n    model: 'gpt-4o'," in new
    assert "    id: 'openai/gpt-5.6-luna',\n    model: 'gpt-5.6-luna'," in new
    got = {(d["line"], d["field"]) for d in sw.skipped_duplicate_id if d["file"] == "src/constants.ts"}
    assert {(5, "id"), (6, "id"), (23, "id"), (24, "id")} <= got
    c = [x for x in sw.collapsed if x["container"] == "list of objects"]
    assert [(x["line"], x["target"], x["applied"]) for x in c] == [(2, "openai/gpt-6-luna", False)]


@pytest.mark.parametrize("sub,file,field,unique", [
    ("pfd", "tests/model_comparison.py", "name", True),
    # 0.4.10: themefinder's one unique id (gpt-4.1-nano) is also an Azure deployment name (kept), so it stays.
    ("themefinder", "evals/benchmark.py", "name", False),
    ("donvito", "src/config/models.json", "name", True),
])
def test_lists_of_objects_never_get_the_same_id_twice(sub, file, field, unique):
    sw = _swap(FIX / sub)
    src = _text(sw, FIX / sub, file)
    vals = re.findall(r"""["']?%s["']?\s*[:=]\s*["']([^"']+)["']""" % field, src)
    assert len(vals) == len(set(vals)), vals
    assert ("gpt-5.6-luna" in vals) is unique                        # the one unique rename still happens
    assert any(d["file"] == file for d in sw.skipped_duplicate_id)
    assert all(not c.get("applied", True) for c in sw.collapsed)


def test_plain_list_collapse_is_skipped_not_applied():
    sw = _swap(FIX / "smart-composer")
    new = sw.new_contents["src/utils/chat/apply.ts"]
    items = re.findall(r"^  '([^']+)',$", new, re.M)
    assert items == ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-5.6-luna"]
    assert sorted(d["model"] for d in sw.skipped_duplicate_id) == ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"]


def test_collapsed_select_options_are_skipped_with_their_template_conditions(tmp_path):
    _write(tmp_path, {"t.html": (
        '<select name="model_name">\n'
        '  <option value="gpt-4.1-mini" {% if model_name == \'gpt-4.1-mini\' %}selected{% endif %}>Mini</option>\n'
        '  <option value="gpt-4.1" {% if model_name == \'gpt-4.1\' %}selected{% endif %}>Full</option>\n'
        '  <option value="gpt-4.1-nano" {% if model_name == \'gpt-4.1-nano\' %}selected{% endif %}>Nano</option>\n'
        '</select>\n')})
    sw = _swap(tmp_path)
    new = sw.new_contents["t.html"].splitlines()
    assert new[1].count("gpt-4.1-mini") == 2 and new[2].count("gpt-4.1") == 2
    assert new[3].count("gpt-5.6-luna") == 2                          # unique: value and condition together
    assert {(d["line"], d["model"]) for d in sw.skipped_duplicate_id} == {(2, "gpt-4.1-mini"), (3, "gpt-4.1")}
    assert [(c["container"], c["applied"]) for c in sw.collapsed] == [("<select> dropdown", False)]


def test_chained_skip_reaches_a_fixed_point(tmp_path):
    # gpt-4.1 -> gpt-6-luna is blocked by an existing key; keeping gpt-4.1 then blocks nothing else,
    # but a rename *to* a kept key must also be caught on the next round.
    _write(tmp_path, {"a.json": '{"gpt-6-luna": 1, "gpt-4.1": 2, "gpt-4.1-nano": 3, "gpt-5.6-luna": 4}\n'})
    sw = _swap(tmp_path)
    assert "a.json" not in sw.new_contents
    assert {d["model"] for d in sw.skipped_duplicate_key} == {"gpt-4.1", "gpt-4.1-nano"}


# ---------------------------------------------------------------- 3. equality checks and migrations

def test_migrations_are_never_rewritten_and_reported_as_info():
    sw = _swap(FIX / "yolo")
    assert not [f for f in sw.new_contents if "/migrations/" in f]
    mig = {m["file"]: m for m in sw.skipped_migration}
    assert set(mig) == {"src/settings/schema/migrations/0_to_1.ts", "src/settings/schema/migrations/5_to_6.ts",
                        "src/settings/schema/migrations/7_to_8.ts"}
    assert mig["src/settings/schema/migrations/5_to_6.ts"]["models"] == ["o1"]
    assert "past versions" in mig["src/settings/schema/migrations/0_to_1.ts"]["note"]
    fx = plan_fixes(FIX / "yolo")
    assert {i.file for i in fx.items if i.rule == "migration-file" and i.status == "info"} == set(mig)
    res = scan(FIX / "yolo", today=TODAY)
    m = [f for f in res.findings if "/migrations/" in f.file and f.category != "not_listed"]
    assert m and all(not f.auto_swap for f in m)
    assert {f.no_swap_reason for f in m} <= {"migration", "allow_list", "flag_only", "name_check", "object_key"}


def test_migration_folder_name_variants(tmp_path):
    _write(tmp_path, {"db/migration/V2__models.py": 'DEFAULT = "gpt-4o"\n',
                      "app/migrations_helper.py": 'DEFAULT = "gpt-4o"\n',
                      "alembic/versions/x.py": 'DEFAULT = "gpt-4o"\n'})
    sw = _swap(tmp_path)
    assert [m["file"] for m in sw.skipped_migration] == ["db/migration/V2__models.py"]
    # 0.4.10: the migration keeps gpt-4o, so the other two files (not migrations) keep it too and are listed.
    assert not sw.new_contents
    assert _kept_refs(sw) == {("app/migrations_helper.py", 1, "gpt-4o"), ("alembic/versions/x.py", 1, "gpt-4o")}
    g, = [x for x in sw.kept_definitions if x["model"] == "gpt-4o"]
    assert g["kept"] == [{"file": "db/migration/V2__models.py", "line": 1, "reason": "migration"}]


def test_equality_checks_are_extended_when_the_id_is_renamed_elsewhere(tmp_path):
    _write(tmp_path, {
        "a.ts": ("const model = 'o1'\n"
                 "if (m.id === 'o1') {}\n"
                 "if (cfg.model !== 'o1') {}\n"
                 "const x = (m) => m.modelName === 'o1' ? 1 : 2\n"
                 "if ('o1' === m.id) {}\n"
                 "const y = a + b === 'o1'\n"
                 "switch (m) { case 'o1': break }\n"),
        "b.py": ('MODEL = "gpt-4o"\n'
                 'if model == "gpt-4o":\n    pass\n'
                 'if model != "gpt-4o" and other:\n    pass\n'),
    })
    sw = _swap(tmp_path)
    a = sw.new_contents["a.ts"].splitlines()
    assert a[0] == "const model = 'gpt-5.6-sol'"
    assert a[1] == "if ((m.id === 'o1' || m.id === 'gpt-5.6-sol')) {}"
    assert a[2] == "if ((cfg.model !== 'o1' && cfg.model !== 'gpt-5.6-sol')) {}"
    assert a[3] == "const x = (m) => (m.modelName === 'o1' || m.modelName === 'gpt-5.6-sol') ? 1 : 2"
    assert a[4:] == ["if ('o1' === m.id) {}", "const y = a + b === 'o1'", "switch (m) { case 'o1': break }"]
    b = sw.new_contents["b.py"].splitlines()
    assert b[1] == 'if (model == "gpt-4o" or model == "gpt-6-luna"):'
    assert b[3] == 'if (model != "gpt-4o" and model != "gpt-6-luna") and other:'
    compile(sw.new_contents["b.py"], "b.py", "exec")
    must = {(w["file"], w["line"], w["kind"]) for w in sw.must_update_together}
    assert must == {("a.ts", 5, "equality"), ("a.ts", 6, "equality"), ("a.ts", 7, "equality")}
    assert [c.action for c in sw.changes if c.file == "a.ts" and c.line == 2] == ["added"]


def test_extend_equality_refuses_unsafe_forms():
    line = "x = a.b + c.id === 'o1'"
    s = line.index("o1")
    assert extend_equality(line, s, s + 2, "n", "typescript") is None
    line = "ok = m.id === 'o1' && y"
    s = line.index("o1")
    assert extend_equality(line, s, s + 2, "n", "typescript")[2] == "(m.id === 'o1' || m.id === 'n')"


# ---------------------------------------------------------------- 4-5. deployment names and tokenisers

def test_azure_deployment_names_are_manual():
    sw = _swap(FIX / "themefinder")
    new = _text(sw, FIX / "themefinder", "evals/benchmark.py")
    # 0.4.10: the deployment keeps gpt-4.1-nano, so the name next to it is not renamed either (listed).
    assert 'JUDGE = ModelConfig(name="gpt-4.1-nano", deployment="gpt-4.1-nano")' in new
    assert ("evals/benchmark.py", 15, "gpt-4.1-nano") in _kept_refs(sw)
    assert 'ModelConfig(name="gpt-4.1-mini", deployment="gpt-4.1-mini")' in new
    held = {(f, l, m, r) for f, l, m, r in sw.skipped_unsafe}
    assert ("evals/benchmark.py", 15, "gpt-4.1-nano", "deployment_name") in held
    assert ("evals/benchmark.py", 12, "gpt-4.1-mini", "deployment_name") in held
    assert any(m["kind"] == "deployment-name" for m in sw.manual())
    fx = plan_fixes(FIX / "themefinder")
    assert any(i.rule == "deployment-name" and i.line == 15 for i in fx.items)


@pytest.mark.parametrize("line", [
    'client = AzureOpenAI(azure_deployment="gpt-4o")',
    'deployment_name = "gpt-4o"',
    'AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o"',
    "const deploymentName = 'gpt-4o'",
    'openai.ChatCompletion.create(engine="gpt-4o", messages=m)',
    '  "deployment": "gpt-4o",',
])
def test_deployment_forms(line):
    s = line.index("gpt-4o")
    assert token_hold(line, s, s + 6, "python", "a.py", "", "sdk_call") == "deployment_name"


def test_tokeniser_arguments_are_manual():
    sw = _swap(FIX / "themefinder")
    f = "src/themefinder/llm_batch_processor.py"
    new = _text(sw, FIX / "themefinder", f)
    assert 'model = model or os.environ.get("MODEL_NAME", "gpt-4o")' in new            # flows into encoding_for_model
    assert 'tiktoken.encoding_for_model("gpt-4o-mini")' in new
    # not a tokeniser argument, but 0.4.10 keeps it with the held gpt-4o (and lists it)
    assert 'def other(model="gpt-4o"):' in new
    assert (f, 20, "gpt-4o") in _kept_refs(sw)
    held = {(l, m, r) for ff, l, m, r in sw.skipped_unsafe if ff == f}
    assert {(15, "gpt-4o", "tokeniser"), (21, "gpt-4o-mini", "tokeniser")} <= held
    msg = [m["message"] for m in sw.manual() if m["kind"] == "tokeniser"]
    assert msg and "o200k_base" in msg[0]


@pytest.mark.parametrize("line,lang", [
    ('enc = tiktoken.encoding_for_model("gpt-4o")', "python"),
    ("const enc = encodingForModel('gpt-4o')", "typescript"),
    ('  "tokenizerModel": "gpt-4o",', "json"),
    ("tokenizer_model: gpt-4o", "yaml"),
])
def test_tokeniser_forms(line, lang):
    s = line.index("gpt-4o")
    assert token_hold(line, s, s + 6, lang, "a", "", "sdk_call") == "tokeniser"


# ---------------------------------------------------------------- 6. price and catalogue files

def test_price_catalogue_is_skipped_and_scan_agrees():
    sw = _swap(FIX / "trigger")
    f = "internal-packages/llm-model-catalog/src/default-model-prices.json"
    assert f not in sw.new_contents
    assert {c["file"] for c in sw.skipped_catalog} == {f, "internal-packages/llm-model-catalog/src/model-catalog.json"}
    res = scan(FIX / "trigger", today=TODAY)
    rows = [x for x in res.findings if x.file == f and x.category != "not_listed"]
    assert rows and not any(x.auto_swap for x in rows)
    assert {x.no_swap_reason for x in rows} <= {"catalog", "regex"}


def test_catalogue_detection(tmp_path):
    _write(tmp_path, {"data/model_pricing.yaml": "gpt-4o: 2.5\n",
                      "src/prices.ts": "export const P = { 'gpt-4o': 2.5 }\n",
                      "cfg/llm.json": '[{"modelName": "gpt-4o", "matchPattern": "^gpt-4o$"}]\n',
                      "cfg/app.json": '{"model": "gpt-4o"}\n'})
    sw = _swap(tmp_path)
    assert {c["file"] for c in sw.skipped_catalog} == {"data/model_pricing.yaml", "cfg/llm.json"}
    # 0.4.10: the catalogues keep gpt-4o, so the two files that aren't catalogues keep it too (listed).
    assert not sw.new_contents
    assert _kept_refs(sw) == {("src/prices.ts", 1, "gpt-4o"), ("cfg/app.json", 1, "gpt-4o")}


def test_match_pattern_next_to_a_swapped_name_must_update_together(tmp_path):
    _write(tmp_path, {"src/models.ts": ("export const M = [{\n  modelName: 'gpt-4o',\n"
                                        "  matchPattern: /^(openai\\/)?(gpt-4o)$/,\n}]\n")})
    sw = _swap(tmp_path)
    assert "modelName: 'gpt-6-luna'" in sw.new_contents["src/models.ts"]
    assert [(w["line"], w["kind"]) for w in sw.must_update_together] == [(3, "regex")]


# ---------------------------------------------------------------- 7. comments, help text, fixtures

def test_comments_docstrings_and_help_text_are_left_alone():
    sw = _swap(FIX / "themefinder")
    new = _text(sw, FIX / "themefinder", "evals/benchmark.py").splitlines()
    assert new[4] == "    uv run python benchmark.py --models gpt-4o gemini-2.5-flash claude-haiku-4.5"
    assert new[16] == '    None  # Azure deployment name for judge LLM (e.g. "gpt-4o-2024-08-06")'
    assert new[25] == "  uv run python benchmark.py --models gpt-4o gemini-2.5-flash --runs 2"
    assert "azure provider, gpt-4.1 only." in new[31]
    # code after the epilog is still code: 0.4.10 keeps it with the kept AZURE_MODELS entry and lists it
    assert new[35] == '        args.models = ["gpt-4.1"]'
    assert ("evals/benchmark.py", 36, "gpt-4.1") in _kept_refs(sw)
    reasons = {(l, r) for f, l, m, r in sw.skipped_unsafe if f == "evals/benchmark.py"}
    assert {(5, "docstring"), (17, "comment"), (26, "help_text"), (32, "help_text")} <= reasons
    lb = _text(sw, FIX / "themefinder", "src/themefinder/llm_batch_processor.py")
    assert 'Defaults to MODEL_NAME env var or "gpt-4o".' in lb
    assert 'otherwise default to "gpt-4o"' in lb


def test_comment_lists_in_jsdoc_and_shell_are_left_alone(tmp_path):
    shutil.copytree(FIX / "trigger", tmp_path / "t")
    (tmp_path / "t" / "src").mkdir()
    (tmp_path / "t" / "src" / "a.ts").write_text(
        "/*\n gpt-4.1, gpt-4.1-mini\n*/\nconst m = 'gpt-4.1' // was gpt-4o\n")
    sw = _swap(tmp_path / "t")
    f = "internal-packages/llm-model-catalog/scripts/generate-model-catalog.sh"
    sh = _text(sw, tmp_path / "t", f).splitlines()
    # 0.4.10: the catalogues keep gpt-4o, so MODEL= keeps it too (listed); the comment is left as before.
    assert '(e.g. "gpt-4o|claude")' in sh[4] and sh[5].startswith('MODEL="gpt-4o"')
    assert (f, 6, "gpt-4o") in _kept_refs(sw)
    assert sw.new_contents["src/a.ts"] == "/*\n gpt-4.1, gpt-4.1-mini\n*/\nconst m = 'gpt-6-luna' // was gpt-4o\n"


def test_recorded_fixture_payload_in_a_test_is_left_alone():
    sw = _swap(FIX / "trigger")
    f = "apps/webapp/test/otlpExporter.test.ts"
    new = _text(sw, FIX / "trigger", f).splitlines()
    assert '"model":"gpt-4o-2024-08-06"' in new[5]
    assert (f, 6, "gpt-4o-2024-08-06", "fixture") in sw.skipped_unsafe
    # 0.4.10: gpt-4o is kept by the catalogues and gpt-4o-2024-08-06 by the fixture, so the request
    # attributes keep them too and are listed with them.
    assert f not in sw.new_contents
    assert new[3].strip() == '"gen_ai.request.model": "gpt-4o",'
    assert sorted((w["line"], w["kind"]) for w in sw.must_update_together if w["file"] == f) == [
        (4, "kept_definition"), (7, "kept_definition")]     # line 6 itself: no longer renamed elsewhere


def test_visible_page_text_is_info_and_not_auto_swap():
    res = scan(FIX / "donvito", today=TODAY)
    rows = [f for f in res.findings if f.file == "src/templates/landing.html"]
    assert [(f.model, f.kind, f.risk, f.auto_swap, f.no_swap_reason) for f in rows] == [
        ("gpt-4", "doc", "info", False, "visible_text"), ("gpt-3.5-turbo", "doc", "info", False, "visible_text")]
    assert all(r["auto_swap"] is False for r in res.to_dict()["findings"] if r["file"] == "src/templates/landing.html")
    assert "src/templates/landing.html" not in _swap(FIX / "donvito").new_contents


def test_scan_auto_swap_matches_swap_holds():
    res = scan(FIX / "themefinder", today=TODAY)
    by = {(f.file, f.line, f.model): f for f in res.findings}
    assert by[("evals/benchmark.py", 12, "gpt-4.1-mini")] and not any(
        f.auto_swap for k, f in by.items() if k[1] == 12 and f.column > 40)
    assert by[("src/themefinder/llm_batch_processor.py", 15, "gpt-4o")].no_swap_reason == "tokeniser"
    assert by[("evals/benchmark.py", 5, "gpt-4o")].no_swap_reason == "docstring"


# ---------------------------------------------------------------- structure parser, summary, CLI, git apply

def test_parse_structure_roles():
    rows = list(enumerate("x = [{'id': 'a', 'n': f(1)}, 'b', ('c', 'd')]\nd = {'k': 'v'}\n".splitlines()))
    lits, conts = parse_structure(rows, "python")
    roles = {(l.text, l.role, l.key) for l in lits}
    assert {("id", "key", None), ("a", "value", "id"), ("b", "item", None), ("c", "item", None),
            ("k", "key", None), ("v", "value", "k")} <= roles
    lits, _ = parse_structure([(0, "const r = /['\"]/g; const o = { 'a': 1 }")], "typescript")
    assert [(l.text, l.role) for l in lits] == [("a", "key")]


def test_summary_has_every_new_section():
    sw = _swap(FIX / "yolo")
    s = sw.summary()
    for k in ("skipped_duplicate_key", "skipped_duplicate_id", "skipped_migration", "skipped_catalog",
              "allow_list_merges", "collapsed_targets", "must_update_together"):
        assert k in s
    assert all(c["applied"] is False for c in s["collapsed_targets"])
    assert any(w.startswith("SKIPPED DUPLICATE KEY src/constants.ts:37") for w in sw.warnings())


def test_cli_swap_and_git_apply(tmp_path, capsys, monkeypatch):
    from migration_kit import cli
    repo = tmp_path / "repo"
    shutil.copytree(FIX / "themefinder", repo)
    monkeypatch.setattr(cli, "_patch_licence", lambda a, feature: True)
    assert cli.main(["swap", str(repo), "--out", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert "rename(s) skipped (duplicate key or id)" in out and "MANUAL evals/benchmark.py:12" in out
    summary = json.loads((tmp_path / "out" / "swap-summary.json").read_text())
    assert summary["skipped_duplicate_id"] and summary["collapsed_targets"][0]["applied"] is False
    # 0.4.10: every id with a rename in this fixture also has a kept definition, so the patch is empty
    # and the CLI says so instead of suggesting `git apply` (git rejects an empty patch).
    assert (tmp_path / "out" / "model-swap.diff").read_text() == ""
    assert "nothing to apply" in out and "git -C" not in out
    assert "MUST UPDATE TOGETHER evals/benchmark.py:36 gpt-4.1" in out
    assert summary["kept_definitions"]
    # git apply on a fixture that still has renames
    repo = tmp_path / "repo2"
    shutil.copytree(FIX / "donvito", repo)
    assert cli.main(["swap", str(repo), "--out", str(tmp_path / "out2")]) == 0
    capsys.readouterr()
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "apply", str(tmp_path / "out2" / "model-swap.diff")], cwd=repo, check=True)
    json.loads((repo / "src" / "config" / "models.json").read_text())


def test_ejs_dropdown_options_and_conditions():
    """clusterzx/paperless-ai views/settings.ejs: 0.4.8 gave two `<option value="gpt-6-luna">`."""
    sw = _swap(FIX / "paperless")
    new = sw.new_contents["views/settings.ejs"].splitlines()
    values = re.findall(r'<option value="([^"]+)"', "\n".join(new))
    assert values == ["gpt-5.6-terra", "gpt-4o", "gpt-5.6-sol", "gpt-4o-mini"]
    # EJS tags are JavaScript, so the selected-condition is extended rather than left behind.
    assert "<%= (config.OPENAI_MODEL === 'o3-mini' || config.OPENAI_MODEL === 'gpt-5.6-sol') ? 'selected' : '' %>" in new[7]
    # Skipped options keep their condition as it was (0.4.9 before this check extended one of them with
    # `|| ... 'gpt-6-luna'`; since 0.4.10 gpt-4o / gpt-4o-mini aren't renamed anywhere else either).
    assert new[6] == ("        <option value=\"gpt-4o\" <%= config.OPENAI_MODEL === 'gpt-4o' ? 'selected' : '' %>>"
                      "GPT-4o</option>")
    assert new[8] == ("        <option value=\"gpt-4o-mini\" <%= config.OPENAI_MODEL === 'gpt-4o-mini' ? 'selected' : '' %>>"
                      "GPT-4o-mini (Best value)</option>")
    # 0.4.10: the skipped options keep gpt-4o / gpt-4o-mini, so config/defaults.js keeps them too (listed).
    assert "config/defaults.js" not in sw.new_contents
    assert {(d["line"], d["model"]) for d in sw.skipped_duplicate_id} == {(7, "gpt-4o"), (9, "gpt-4o-mini")}
    assert {(w["file"], w["line"], w["model"], w["kind"]) for w in sw.must_update_together} == {
        ("config/defaults.js", 2, "gpt-4o", "kept_definition"), ("config/defaults.js", 2, "gpt-4o-mini", "kept_definition")}


def test_jsx_dropdown_options():
    sw = _swap(FIX / "jsx")
    new = sw.new_contents["src/ModelPicker.tsx"]
    assert re.findall(r'<option value="([^"]+)"', new) == ["gpt-4o", "gpt-4o-mini", "gpt-5.6-luna"]
    assert [(c["container"], c["applied"]) for c in sw.collapsed] == [("<select> dropdown", False)]
