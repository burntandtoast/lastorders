"""Regression fixtures extracted from public repos, not full checkouts.

- ukhsa-collaboration/epiviz R/llm_interpret.R (roxygen gpt-4.1-nano on the lines that 0.4.2 missed)
- AVIDS2/memorix packages/ai/src/models.generated.ts (generated catalogue)
- TheWidlarzGroup/react-native-voice-agent .yarn/plugins/*.cjs (minified o1/o3 false positives)
"""
from conftest import ROOT, TODAY
from migration_kit.cli import main
from migration_kit.scanner import scan, to_markdown

FIX = ROOT / "tests" / "fixtures" / "scan_accuracy"
SHORT = {"o1", "o3", "o4", "o5", "o9"}


def _scan(path, **kw):
    return scan(path, today=TODAY, **kw)


def test_r_roxygen_comments_and_strings_are_reported():
    res = _scan(FIX / "epiviz")
    r = [f for f in res.findings if f.file == "R/llm_interpret.R" and f.model == "gpt-4.1-nano"]
    comments = [f for f in r if f.kind == "comment"]
    code = [f for f in r if f.kind != "comment"]
    assert {f.line for f in comments} >= {5, 13}
    assert all(f.risk == "low" for f in comments)
    assert any("documentation/comment" in n for f in comments for n in f.notes)
    assert len(code) == 1 and code[0].risk == "high" and code[0].line == 19

    rmd = {f.kind: f for f in res.findings if f.file == "notes.Rmd" and f.model == "gpt-4.1-nano"}
    assert rmd["doc"].risk == "low"
    assert rmd["sdk_call"].risk == "high"
    qmd = [f for f in res.findings if f.file == "report.qmd" and f.model == "gpt-4.1-nano"]
    assert len(qmd) == 1 and qmd[0].kind == "comment" and qmd[0].risk == "low"


def test_generated_and_vendored_collapse_and_do_not_fail_ci(tmp_path, capsys):
    root = FIX / "memorix"
    res = _scan(root)
    assert {f.file for f in res.findings} == {"src/keep.ts"}
    assert res.findings[0].risk != "high"
    by_file = {s.file: s for s in res.skipped}
    assert by_file["packages/ai/src/models.generated.ts"].reason == "generated"
    assert by_file["packages/ai/src/models.generated.ts"].count == 4
    assert by_file["src/client.gen.ts"].reason == "generated"
    assert by_file["gen/service_pb2.py"].reason == "generated"
    assert by_file["src/header_generated.ts"].reason == "generated"
    assert by_file["web/app.min.js"].reason == "minified"
    assert by_file["vendor/lib.py"].reason == "vendored"
    assert by_file["third_party/sdk.py"].reason == "vendored"
    assert by_file["dist/bundle.js"].reason == "vendored"
    line = by_file["packages/ai/src/models.generated.ts"].line()
    assert line == ("packages/ai/src/models.generated.ts: 4 model IDs in a generated file, "
                    "skipped; use --include-generated to scan it")
    assert "skipped_generated" in res.to_dict()
    assert "## Generated and vendored files" in to_markdown(res)

    out = tmp_path / "out"
    assert main(["scan", str(root), "--out", str(out), "--fail-on-high", "--offline"]) == 0
    text = capsys.readouterr().out
    assert "packages/ai/src/models.generated.ts: 4 model IDs in a generated file, skipped" in text
    assert "--include-generated" in text


def test_include_generated_scans_and_can_fail(tmp_path):
    root = FIX / "memorix"
    res = _scan(root, include_generated=True)
    assert any(f.file == "packages/ai/src/models.generated.ts" and f.model == "gpt-4.1-nano" and f.risk == "high"
               for f in res.findings)
    assert res.skipped == []
    assert main(["scan", str(root), "--out", str(tmp_path), "--include-generated", "--fail-on-high", "--offline"]) == 2


def test_short_ids_need_model_context_yarn_plugin_shapes():
    res = _scan(FIX / "voice")
    assert not any(f.model in SHORT for f in res.findings if "minified-snippet" in f.file or ".yarn/" in f.file)
    assert not any(f.file.startswith(".yarn/") for f in res.findings)
    yarn = next(s for s in res.skipped if s.file.startswith(".yarn/"))
    assert yarn.reason == "vendored" and yarn.count == 1
    assert "vendored file, skipped" in yarn.line()

    found = {(f.file, f.line, f.model) for f in res.findings}
    assert ("src/types/index.ts", 3, "o3-mini") in found
    assert ("src/types/index.ts", 6, "o3-mini") in found
    assert ("src/types/index.ts", 10, "o1") in found
    assert ("models.yaml", 1, "o3") in found
    assert ("models.yaml", 3, "o1") in found
    assert ("models.yaml", 4, "o3-mini") in found
    assert all(f.model not in SHORT or f.file != "src/minified-snippet.cjs" for f in res.findings)


def test_sample_node_modules_is_a_skip_line_not_a_finding():
    res = _scan(ROOT / "examples" / "sample-app")
    assert not any("node_modules" in f.file for f in res.findings)
    skipped = [s for s in res.skipped if s.file == "node_modules/openai/index.js"]
    assert len(skipped) == 1 and skipped[0].reason == "vendored" and skipped[0].count == 1
