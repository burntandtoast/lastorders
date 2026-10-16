"""Automatic fixer: pack-driven edits, formatting preservation, manual flags, verification, CLI gating."""
import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import ROOT
from migration_kit import packs as pk
from migration_kit.cli import main
from migration_kit.fixer import plan_fixes
from migration_kit.fixer import jsfix, pyfix
from migration_kit.fixer.callsite import Edit
from migration_kit.fixer.verify import verify

FIX = ROOT / "tests" / "fixtures" / "fixer-repo"
SAMPLE = ROOT / "examples" / "sample-app"


def _items(res, file=None):
    return {(i.file, i.line, i.rule): i for i in res.items if file is None or i.file == file}


def _status(res, file, line, rule):
    return _items(res)[(file, line, rule)].status


@pytest.fixture(scope="module")
def fx():
    return plan_fixes(FIX, pk.load_packs(offline=True))


# ---------------------------------------------------------------- rules -> edits
def test_sample_app_fixes(tmp_path):
    res = plan_fixes(SAMPLE, pk.load_packs(offline=True))
    s = res.new_contents["app/summarise.py"]
    assert 'model="gpt-6-luna"' in s and "max_completion_tokens=400" in s and 'reasoning_effort="none"' in s
    assert "max_tokens" not in s
    assert 'tools=TOOLS, reasoning_effort="none")' in res.new_contents["app/agent.py"]
    assert 'reasoning_effort: "none",' in res.new_contents["web/src/chat.ts"]
    # fine-tune untouched and flagged; the env-var call is coupled to the model switch
    assert "ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1" in res.new_contents["app/agent.py"]
    assert _status(res, "app/agent.py", 35, "fine-tune") == "manual"
    coupled = _items(res)[("app/agent.py", 29, "luna-chat-tools-effort")]
    assert coupled.status == "fixed-coupled" and "$OPENAI_MODEL" in " ".join(coupled.notes)
    # inferred Anthropic rule is suggested, not applied
    assert _status(res, "app/claude_fallback.py", 8, "claude-sampling-deprecated") == "manual"
    assert "temperature=0.3" in res.new_contents["app/claude_fallback.py"]
    # config value the fixer can't tie to a call
    assert _status(res, "config/settings.json", 2, "luna-max-tokens") == "manual"


def test_python_variants(fx):
    v = fx.new_contents["py/variants.py"]
    assert 'max_output_tokens=200, reasoning={"effort": "none"})' in v               # Responses: nested param
    assert 'reasoning={"summary": "auto", "effort": "none"},' in v                   # merged into existing dict
    assert "max_completion_tokens=100, **extra)" in v                               # rename works next to **kwargs
    assert _items(fx)[("py/variants.py", 25, "luna-sampling")].status == "manual"     # but no insert next to **kwargs
    assert _status(fx, "py/variants.py", 30, "model-unknown") == "manual"
    assert 'temperature=1)' in v and ("py/variants.py", 43, "luna-sampling") not in _items(fx)   # temperature=1 is fine
    assert _status(fx, "py/variants.py", 47, "luna-chat-tools-effort") == "manual"   # reasoning_effort="low" conflict
    assert ("py/variants.py", 58, "luna-chat-tools-effort") not in _items(fx)         # already compliant
    # multi-line call without a trailing comma keeps its layout
    assert '        tools=TOOLS,\n        reasoning_effort="none"\n    )' in v


def test_legacy_endpoints_flagged_and_kept_on_old_model(fx):
    lg = fx.new_contents["py/legacy.py"]
    assert 'beta.assistants.create(model="gpt-4o"' in lg
    assert 'completions.create(model="gpt-4o-mini", prompt=p, max_tokens=50)' in lg
    assert 'jobs.create(model="gpt-4o-mini-2024-07-18"' in lg
    for line, rule in [(9, "luna-legacy-functions"), (14, "luna-assistants"), (18, "luna-legacy-completions"),
                       (22, "luna-fine-tuning-jobs")]:
        assert _status(fx, "py/legacy.py", line, rule) == "manual"
    assert "kept on `gpt-4o`" in _items(fx)[("py/legacy.py", 14, "luna-assistants")].change


def test_langchain_not_auto_renamed(fx):
    assert 'ChatOpenAI(model="gpt-6-luna", max_tokens=100, temperature=0.2)' in fx.new_contents["py/chains.py"]
    assert _status(fx, "py/chains.py", 3, "luna-max-tokens") == "manual"
    assert _status(fx, "py/chains.py", 3, "langchain-max-tokens") == "info"


def test_js_ts(fx):
    js = fx.new_contents["web/chat.js"]
    assert 'max_completion_tokens: 256, temperature: 0.3, reasoning_effort: "none" });' in js
    assert "'max_completion_tokens': 64," in js                                     # quoted key keeps its quotes
    assert "// a comment with braces { ( [ and a fake call: openai.chat.completions.create({ max_tokens: 1 })" in js
    assert 'const note = "string with }) inside";' in js
    ts = fx.new_contents["web/resp.ts"]
    assert 'reasoning: { summary: "auto", effort: "none" }' in ts
    assert _status(fx, "web/resp.ts", 6, "luna-sampling") == "manual"                # ...spread
    assert jsfix.syntax_ok(js, "javascript") is None and jsfix.syntax_ok(ts, "typescript") is None


def test_only_edited_lines_change(fx):
    import difflib
    keys = ("gpt-", "max_tokens", "tools", "reasoning", "temperature", "top_p", "function_call", "max_output_tokens", "max_completion_tokens")
    for rel, new in fx.new_contents.items():
        old = (FIX / rel).read_text().splitlines()
        for ln in difflib.unified_diff(old, new.splitlines(), lineterm="", n=0):
            if ln[:1] in "+-" and not ln.startswith(("+++", "---")):
                assert not ln[1:].strip() or any(k in ln for k in keys) or ln[1:].strip() in (")", "});"), (rel, ln)


def test_patch_applies_and_is_idempotent(fx, tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(FIX, repo)
    (tmp_path / "fix.diff").write_text(fx.diff)
    r = subprocess.run(["git", "apply", str(tmp_path / "fix.diff")], cwd=repo, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    for rel in fx.new_contents:
        if rel.endswith(".py"):
            compile((repo / rel).read_text(), rel, "exec")
    again = plan_fixes(repo, pk.load_packs(offline=True))
    assert again.diff == ""


def test_no_model_swap_only_applies_safe_fixes(tmp_path):
    res = plan_fixes(SAMPLE, pk.load_packs(offline=True), model_swap=False)
    s = res.new_contents["app/summarise.py"]
    assert 'model="gpt-4o-2024-08-06"' in s and "max_completion_tokens=400" in s     # rename is safe on the old model
    assert "reasoning_effort" not in s                                              # old models reject it
    it = _items(res)[("app/summarise.py", 19, "luna-sampling")]
    assert it.status == "manual" and "current model would reject it" in it.change


def test_assume_model_and_include_inferred(tmp_path):
    res = plan_fixes(FIX, pk.load_packs(offline=True), assume_model="gpt-6-luna")
    assert _status(res, "py/variants.py", 30, "luna-chat-tools-effort") == "fixed-coupled"
    res = plan_fixes(SAMPLE, pk.load_packs(offline=True), include_inferred=True)
    c = res.new_contents["app/claude_fallback.py"]
    assert "temperature" not in c and "max_tokens=400," in c


def test_engine_is_pack_driven(tmp_path):
    """A made-up provider works with no code change: endpoints, params and fixes are all pack data."""
    data = json.loads((ROOT / "migration_kit" / "pack_data" / "anthropic.json").read_text())
    p = copy.deepcopy(data)
    p.update(provider="acme", name="Acme AI", version="2026.01.01", status="example")
    p["id_patterns"] = [{"pattern": "acme-[a-z0-9-]+"}]
    p["fine_tune"] = None
    p.pop("fine_tune")
    p["migrations"] = [{"id": "m1", "title": "Acme retires acme-old", "shutdown": "2027-01-01",
                        "replacement": "acme-new", "headline": True, "announced": "2026-01-01", "source": data["migrations"][0]["source"]}]
    p["models"] = [{"id": "acme-old", "shutdown": "2027-01-01", "replacement": "acme-new", "migration": "m1"},
                   {"id": "acme-new"}]
    p["signals"] = [{"id": "gen", "pattern": r"\.generate\(", "call": {"callees": ["acme.generate"]}},
                    {"id": "len", "pattern": r"\blength\b", "call": {"params": ["length"]}}]
    p["rules"] = [{"id": "acme-length", "type": "param_renamed", "applies_to": {"replacements": ["acme-new"]},
                   "when_all": ["gen", "len"], "risk": "high", "confidence": "confirmed", "message": "renamed",
                   "fix": {"action": "rename_param", "from": "length", "to": "max_len"}}]
    pk.validate(p)
    f = tmp_path / "acme.json"
    f.write_text(json.dumps(p))
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "a.py").write_text('import acme\nacme.generate(model="acme-old", length=5)\n')
    res = plan_fixes(repo, pk.load_packs(["acme"], offline=True, extra_files=[str(f)]))
    assert res.new_contents["a.py"] == 'import acme\nacme.generate(model="acme-new", max_len=5)\n'


# ---------------------------------------------------------------- adapters
@pytest.mark.parametrize("src,expect", [
    ('c.chat.completions.create(model="m")\n', 'c.chat.completions.create(model="m", x="none")\n'),
    ('c.chat.completions.create(\n    model="m",\n)\n', 'c.chat.completions.create(\n    model="m",\n    x="none",\n)\n'),
    ('c.chat.completions.create(\n    model="m"\n)\n', 'c.chat.completions.create(\n    model="m",\n    x="none"\n)\n'),
    ("c.chat.completions.create(model='m')  # keep\n", "c.chat.completions.create(model='m', x='none')  # keep\n"),
])
def test_python_insert_formatting(src, expect):
    cs = pyfix.find_calls(src, "f.py", ["chat.completions.create"])
    out, applied = pyfix.apply_edits(src, {cs[0].key: [Edit("set", "x", value="none")]})
    assert out == expect and applied


@pytest.mark.parametrize("src,expect", [
    ('o.chat.completions.create({ model: "m" });', 'o.chat.completions.create({ model: "m", x: "none" });'),
    ('o.chat.completions.create({\n  model: "m",\n});', 'o.chat.completions.create({\n  model: "m",\n  x: "none",\n});'),
    ('o.chat.completions.create({\n  model: "m"\n});', 'o.chat.completions.create({\n  model: "m",\n  x: "none"\n});'),
    ("o?.chat.completions.create({ model: 'm', y: 1 });", "o?.chat.completions.create({ model: 'm', y: 1, x: 'none' });"),
])
def test_js_insert_formatting(src, expect):
    cs = jsfix.find_calls(src, "f.js", ["chat.completions.create"])
    out, applied = jsfix.apply_edits(src, {cs[0].key: [Edit("set", "x", value="none")]}, ["chat.completions.create"])
    assert out == expect and applied


def test_js_remove_property_on_own_line():
    src = 'o.messages.create({\n  model: "m",\n  temperature: 0.3,\n  max: 1,\n});'
    cs = jsfix.find_calls(src, "f.js", ["messages.create"])
    out, _ = jsfix.apply_edits(src, {cs[0].key: [Edit("remove", "temperature")]}, ["messages.create"])
    assert out == 'o.messages.create({\n  model: "m",\n  max: 1,\n});'


def test_js_mask_handles_literals():
    src = 'const a = "})"; const r = /[(]/; const t = `${x}{`; // {(\nf({ k: 1 });'
    m = jsfix.mask(src)
    assert len(m) == len(src) and m.count("{") == m.count("}") and m.count("(") == m.count(")")


# ---------------------------------------------------------------- verify + CLI
def test_verify_mock(tmp_path):
    packs = pk.load_packs(offline=True)
    res = plan_fixes(SAMPLE, packs)
    rep = verify(SAMPLE, res, packs, tmp_path / "v")
    assert rep["ok"] and rep["steps"]["patch_applies"] and rep["steps"]["idempotent"]["ok"]
    runs = {r["api"]: r for r in rep["steps"]["eval"]["runs"]}
    assert runs["chat"]["acceptance"]["cases"] == 3 and runs["responses"]["acceptance"]["cases"] == 1
    chat = json.loads((tmp_path / "v" / "fix-verify-chat.json").read_text())
    assert (tmp_path / "v" / "verify.md").exists() and chat["mode"] == "mock"
    # each case replays the call's own arguments, old vs patched
    from migration_kit.fixer.verify import build_cases
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d) / "r"
        shutil.copytree(SAMPLE, repo, ignore=shutil.ignore_patterns("node_modules"))
        for rel, t in res.new_contents.items():
            (repo / rel).write_text(t)
        cases, skipped = build_cases(repo, res)
    summ = next(c for c in cases["chat"] if c["source"] == "app/summarise.py:19")
    assert summ["model_params"]["old"] == {"temperature": 0.2, "max_tokens": 400}
    assert summ["model_params"]["new"] == {"temperature": 0.2, "max_completion_tokens": 400, "reasoning_effort": "none"}
    assert summ["models"] == {"old": "gpt-4o-2024-08-06", "new": "gpt-6-luna"} and summ["type"] == "structured"
    assert any("anthropic" in s for s in skipped)


def test_verify_detects_broken_patch(tmp_path):
    packs = pk.load_packs(offline=True)
    res = plan_fixes(SAMPLE, packs)
    res.new_contents["app/summarise.py"] += "\ndef broken(:\n"
    rep = verify(SAMPLE, res, packs, tmp_path / "v")
    assert not rep["ok"]


def test_cli_fix_gating_and_apply(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    shutil.copytree(SAMPLE, repo, ignore=shutil.ignore_patterns("node_modules"))
    out = tmp_path / "out"
    preview = main(["fix", str(repo), "--out", str(out)])
    assert preview == 0
    text = capsys.readouterr().out
    assert "app/summarise.py:" in text and "->" in text
    assert "--- a/" not in text and "+++" not in text and "@@" not in text
    assert not (out / "fix.diff").exists() and not (out / "fix-plan.json").exists()
    assert "max_tokens=400" in (repo / "app" / "summarise.py").read_text()          # nothing touched
    assert main(["fix", str(repo), "--out", str(out), "--verify"]) == 4            # patch + verify need a licence
    assert main(["fix", str(repo), "--out", str(out), "--apply"]) == 4             # licence needed
    assert main(["fix", str(repo), "--out", str(out), "--verify", "--live"]) == 4  # live eval needs a licence too
    assert not (out / "fix.diff").exists() and not (out / "verify").exists()
    monkeypatch.setenv("LASTORDERS_LICENCE", "BTM-TEST-0000-0000")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"], cwd=repo, check=True)
    (repo / "app" / "summarise.py").write_text((repo / "app" / "summarise.py").read_text() + "# local edit\n")
    assert main(["fix", str(repo), "--out", str(out), "--apply"]) == 7             # uncommitted change in a touched file
    subprocess.run(["git", "checkout", "--", "."], cwd=repo, check=True)
    assert main(["fix", str(repo), "--out", str(out), "--apply", "--verify"]) == 0
    assert (out / "fix.diff").read_text().startswith("--- ") or "--- a/" in (out / "fix.diff").read_text()
    assert (out / "verify" / "verify.md").exists()
    assert "max_completion_tokens=400" in (repo / "app" / "summarise.py").read_text()


def test_verify_merges_customer_suite(tmp_path):
    """Cases from init-evals carry `source: file:line`; verify replays them with the fixed arguments."""
    from migration_kit import initevals
    packs = pk.load_packs(offline=True)
    suite, skipped = initevals.build_suite(SAMPLE, packs=packs)
    for c in suite["cases"]:
        c["prompt"] = "A real example input."
    sp = initevals.write_suite(suite, skipped, tmp_path / "regression.yaml")
    res = plan_fixes(SAMPLE, packs)
    rep = verify(SAMPLE, res, packs, tmp_path / "v", suite_path=str(sp))
    assert rep["ok"]
    user = json.loads((tmp_path / "v" / f"{suite['name']}.json").read_text())
    assert user["cases"] and rep["steps"]["eval"]["runs"][0]["suite"] == suite["name"]
    from migration_kit.fixer.verify import _merge_user_suite
    merged = _merge_user_suite(str(sp), res)
    s = next(c for c in merged["cases"] if c["source"] == "app/summarise.py:19")
    assert s["model_params"]["new"]["reasoning_effort"] == "none" and s["model_params"]["new"]["max_completion_tokens"] == 400
    assert "max_tokens" in s["model_params"]["old"] and s["max_output_tokens"] is None


def test_outputs_inside_repo_are_skipped(tmp_path, monkeypatch, licensed):
    repo = tmp_path / "repo"
    shutil.copytree(SAMPLE, repo, ignore=shutil.ignore_patterns("node_modules"))
    monkeypatch.chdir(repo)
    assert main(["fix", ".", "--verify"]) == 0               # licensed: default out dir lands inside the repo
    assert main(["scan", "."]) == 0
    assert main(["fix", ".", "--verify"]) == 0               # and is ignored on the next runs
    plan = json.loads((repo / "lastorders-out" / "fix-plan.json").read_text())
    assert not any(i["file"].startswith("lastorders-out") for i in plan["items"])
    assert "lastorders-out" not in (repo / "lastorders-out" / "fix.diff").read_text()
