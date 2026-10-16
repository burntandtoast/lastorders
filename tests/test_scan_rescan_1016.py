"""Regression fixtures from Chad's 16 Oct 2026 rescan of 38 repos with 0.4.3.

Snippets are excerpts from public repos (shallow clones, 16 Oct 2026):
- pressidium/pressidium-cookie-consent includes/AI/GPT.php:105-122, includes/Migrator.php:266
- raine/anki-llm src/doctor/command.rs:137, src/llm/pricing.rs:13
- Virendra-Vyas/contractoriq ContractorIQ.API/Services/Ir35ScreenerService.cs:95
- clusterzx/paperless-ai views/setup.ejs:238
- HexmosTech/LiveReview internal/ai/langchain/provider_temperature_test.go:10
- triggerdotdev/trigger.dev apps/webapp/test/mollifierGate.test.ts:94,
  apps/webapp/test/queueMetricsMapping.test.ts:12,99 (`orgId: "o1"` false positives)
- glowingjade/obsidian-smart-composer src/constants.ts:379 (`id: 'o4-mini'` stays a hit)
- ukhsa-collaboration/epiviz docs/search.json (pkgdown search index, was 6 high findings)
"""
from conftest import ROOT, TODAY
from migration_kit.scanner import scan

FIX = ROOT / "tests" / "fixtures" / "scan_accuracy" / "rescan_1016"


def _scan(sub, **kw):
    return scan(FIX / sub, today=TODAY, **kw)


def _hits(res, file):
    return {(f.line, f.model): f for f in res.findings if f.file == file}


# Gap 1: .php, .rs, .cs, .go and .ejs are scanned.

def test_php_allowed_list_and_migrator_default():
    res = _scan("pressidium")
    gpt = {f.model for f in res.findings if f.file == "includes/AI/GPT.php"}
    assert {"gpt-4-turbo", "gpt-4", "gpt-4.1-nano", "o1-pro", "o1", "o3-mini", "gpt-3.5-turbo", "o4-mini"} <= gpt
    assert all(f.language == "php" for f in res.findings)
    mig = [f for f in res.findings if f.file == "includes/Migrator.php" and f.model == "gpt-3.5-turbo"]
    assert len(mig) == 1 and mig[0].kind == "sdk_call" and mig[0].risk == "high"   # 'model' => 'gpt-3.5-turbo'
    comments = {f.model: f for f in res.findings if f.file == "includes/Migrator.php" and f.kind == "comment"}
    assert comments["gpt-4"].risk == "low" and comments["gpt-4-turbo"].risk == "low"   # // and # comments
    attr = [f for f in res.findings if f.file == "includes/Migrator.php" and "#[Deprecated" in f.snippet]
    assert attr and attr[0].kind != "comment"   # PHP 8 attribute, not a comment


def test_rust_probe_model_and_pricing():
    res = _scan("anki")
    probe = [f for f in res.findings if f.file == "src/doctor/command.rs" and f.model == "gpt-4.1-nano"]
    assert len(probe) == 1 and probe[0].risk == "high" and probe[0].language == "rust"
    price = [f for f in res.findings if f.file == "src/llm/pricing.rs" and f.model == "gpt-4.1-nano"]
    assert len(price) == 1 and price[0].kind == "string_literal"


def test_csharp_model_assignment():
    res = _scan("contractoriq")
    h = [f for f in res.findings if f.model == "gpt-4o"]
    assert len(h) == 1 and h[0].kind == "sdk_call" and h[0].language == "csharp"
    c = [f for f in res.findings if f.model == "gpt-4-turbo"]
    assert len(c) == 1 and c[0].kind == "comment" and c[0].risk == "low"


def test_ejs_option_values_and_comments():
    res = _scan("paperless")
    o3 = [f for f in res.findings if f.model == "o3-mini" and f.kind != "comment"]
    assert o3 and all(f.risk == "high" and f.language == "ejs" for f in o3)
    comments = {f.model for f in res.findings if f.kind == "comment"}
    assert {"o3-mini", "gpt-4"} <= comments


def test_go_struct_field_and_comment():
    res = _scan("livereview")
    h = [f for f in res.findings if f.model == "o4-mini" and f.kind == "sdk_call"]
    assert h and h[0].language == "go" and h[0].risk == "high"
    assert any(f.model == "o4-mini" and f.kind == "comment" and f.risk == "low" for f in res.findings)


# Gap 2: short IDs under a non-model *Id / *_id key are not hits.

def test_trigger_org_ids_are_not_model_hits():
    res = _scan("trigger")
    for file in ("apps/webapp/test/mollifierGate.test.ts", "apps/webapp/test/queueMetricsMapping.test.ts"):
        assert not [f for f in res.findings if f.file == file and f.model == "o1"], file


def test_real_short_id_hits_are_kept():
    res = _scan("trigger")
    cat = {(f.line, f.model) for f in res.findings if f.file == "catalog/models.json"}
    assert {(2, "o1"), (3, "o1"), (6, "o1-pro"), (7, "o1-pro")} <= cat
    ids = {f.line for f in res.findings if f.file == "catalog/ids.ts"}
    assert ids == {3, 4, 8}   # modelId, model_id, deploymentId; not projectId, user_id, rowId
    composer = _scan("composer")
    lines = {(f.snippet, f.model) for f in composer.findings}
    assert ("id: 'o4-mini',", "o4-mini") in lines and ("model: 'o4-mini',", "o4-mini") in lines


# Gap 3: docs search indexes are generated.

def test_docs_search_indexes_collapse_to_one_line():
    for sub, rel in (("epiviz", "docs/search.json"), ("mkdocs", "site/search/search_index.json"),
                     ("sphinx", "docs/_build/html/searchindex.js")):
        res = _scan(sub)
        assert not [f for f in res.findings if f.file == rel], rel
        sk = {s.file: s for s in res.skipped}
        assert sk[rel].reason == "generated" and sk[rel].count >= 1
    epi = {s.file: s for s in _scan("epiviz").skipped}["docs/search.json"]
    assert epi.line().startswith("docs/search.json: ") and "in a generated file, skipped" in epi.line()
    included = _scan("epiviz", include_generated=True)
    assert any(f.file == "docs/search.json" and f.model == "gpt-4.1-nano" for f in included.findings)


def test_search_json_outside_docs_output_is_scanned():
    res = _scan("app")
    assert any(f.file == "src/search.json" and f.model == "gpt-4.1-nano" for f in res.findings)
    assert not res.skipped
