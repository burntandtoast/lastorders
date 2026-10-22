"""Next CLI release (agreed with Chad, 22 Oct 2026): Anthropic sampling rules are suggest-only, the free scan
flags temperature/top_p/top_k wherever Anthropic code sets them, and the azure-foundry pack is fetched."""
import datetime as dt
import hashlib
import json
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler

import pytest

from conftest import ROOT
from migration_kit import packs as pk
from migration_kit.fixer import plan_fixes
from migration_kit.packs import load_packs
from migration_kit.scanner import github_annotations, model_independent_rules, scan, to_markdown, to_summary_markdown
from migration_kit.site import build_site

TODAY = dt.date(2026, 10, 22)
ERR = "claude-sampling-removed-api-2026-10-21"
WARN = "claude-sampling-api-2026-10-21-warning"
OLD = "claude-sampling-deprecated"
WORDING = "This will fail once you move to the 2026-10-21 version"


def _write(tmp_path, files):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


def _call(model="claude-sonnet-5-5", version=None, extra=""):
    h = f'default_headers={{"anthropic-version": "{version}"}}' if version else ""
    return ("import anthropic\n"
            f"client = anthropic.Anthropic({h})\n"
            "\n"
            f'r = client.messages.create(model="{model}", max_tokens=50, temperature=0.2{extra}, messages=[])\n')


def _rules(name):
    return {r["id"]: r for r in json.loads((ROOT / "migration_kit" / "pack_data" / f"{name}.json").read_text())["rules"]}


def _scan(root):
    return scan(root, packs=load_packs(offline=True), today=TODAY)


# ------------------------------------------------------------------ (3) older rule is suggest-only
def test_old_rule_is_suggest_only():
    fix = _rules("anthropic")[OLD]["fix"]
    assert fix["action"] == "manual" and "not applied automatically" in fix["note"]


@pytest.mark.parametrize("model", ["claude-sonnet-5-5", "claude-sonnet-4-5-20250929", "claude-opus-4-6"])
def test_include_inferred_never_strips_sampling_params(tmp_path, model):
    root = _write(tmp_path, {"app.py": _call(model, extra=", top_p=0.9, top_k=5")})
    res = plan_fixes(root, load_packs(offline=True), include_inferred=True)
    after = res.new_contents.get("app.py", (root / "app.py").read_text())
    assert "temperature=0.2" in after and "top_p=0.9" in after and "top_k=5" in after
    for i in res.items:
        if i.rule in (OLD, ERR, WARN):
            assert i.status == "manual"
    assert not any(i.status.startswith("fixed") and "temperature" in i.change for i in res.items)


def test_all_anthropic_rules_manual():
    assert all(r["fix"]["action"] == "manual" for r in _rules("anthropic").values())


# ------------------------------------------------------------------ (2) free scan flags the parameters
@pytest.mark.parametrize("version,rule,risk", [(None, WARN, "medium"), ("2026-10-20", WARN, "medium"),
                                               ("2026-10-21", ERR, "high"), ("2027-03-01", ERR, "high")])
def test_scan_flags_params_on_active_model(tmp_path, version, rule, risk):
    root = _write(tmp_path, {"app.py": _call("claude-sonnet-5-5", version)})
    res = _scan(root)
    (p,) = [f for f in res.findings if f.category == "param_rule"]
    assert p.rules == [rule] and p.risk == risk and p.model == "temperature" and p.line == 4
    assert p.provider == "anthropic" and p.kind == "param" and not p.auto_swap
    assert WORDING in p.notes[0]
    assert p.notes[0].startswith("Error:" if risk == "high" else "Warning:")


def test_scan_flag_with_model_from_env(tmp_path):
    root = _write(tmp_path, {"app.ts": "import Anthropic from '@anthropic-ai/sdk';\nconst c = new Anthropic();\n"
                                       "await c.messages.create({ model: process.env.CLAUDE_MODEL, top_k: 5, messages });\n"})
    (p,) = [f for f in _scan(root).findings if f.category == "param_rule"]
    assert p.model == "top_k" and p.rules == [WARN] and p.line == 3


def test_scan_message_has_no_step_by_step_fix(tmp_path):
    for rid in (ERR, WARN):
        r = _rules("anthropic")[rid]
        assert WORDING in r["message"]
        assert "1." not in r["message"] and "Suggested fix" not in r["message"] and "prompt" not in r["message"]
        assert "1. Remove temperature" in r["fix"]["note"]      # the steps live in the paid fix plan
    root = _write(tmp_path, {"app.py": _call()})
    md = to_markdown(_scan(root))
    assert "API parameter change" in md and WORDING in md and "1. Remove" not in md


def test_fix_plan_has_the_steps(tmp_path):
    root = _write(tmp_path, {"app.py": _call("claude-opus-4-6", "2026-10-21")})
    res = plan_fixes(root, load_packs(offline=True))
    (it,) = [i for i in res.items if i.rule == ERR]
    assert it.status == "manual" and "1. Remove temperature" in it.change and res.diff == ""


def test_fix_plan_call_with_unknown_model(tmp_path):
    root = _write(tmp_path, {"app.py": "import anthropic, os\nc = anthropic.Anthropic()\n"
                                       'c.messages.create(model=os.environ["M"], temperature=0.1, messages=[])\n'})
    res = plan_fixes(root, load_packs(offline=True))
    (it,) = [i for i in res.items if i.rule == WARN]
    assert it.status == "manual" and "1. Remove temperature" in it.change
    assert not any(i.rule == "model-unknown" and WARN in i.message for i in res.items)


def test_retiring_id_line_carries_the_rule_once(tmp_path):
    root = _write(tmp_path, {"app.py": _call("claude-sonnet-4-5-20250929", "2026-10-21")})
    res = _scan(root)
    model = [f for f in res.findings if f.model == "claude-sonnet-4-5-20250929"]
    assert len(model) == 1 and ERR in model[0].rules
    assert not [f for f in res.findings if f.category == "param_rule"]        # no duplicate flag


@pytest.mark.parametrize("src", [
    # OpenAI code that sets temperature: not an Anthropic call
    "from openai import OpenAI\nc = OpenAI()\nc.chat.completions.create(model='gpt-6-luna', temperature=0.2, messages=[])\n",
    # OpenAI Assistants: threads.messages.create is not the Anthropic Messages API
    "from openai import OpenAI\nc = OpenAI()\nc.beta.threads.messages.create(t, role='user', content='x')\n"
    "c.beta.threads.runs.create(t, assistant_id=a, temperature=0.2)\n",
    # Anthropic SDK, but the word only appears in a comment
    "import anthropic\n# temperature is set by the gateway\nc = anthropic.Anthropic()\n",
    # Anthropic SDK, a longer identifier that merely contains the word
    "import anthropic\nmax_temperature_c = 30\nc = anthropic.Anthropic()\n",
])
def test_no_param_flag_outside_anthropic_code(tmp_path, src):
    root = _write(tmp_path, {"app.py": src})
    assert not [f for f in _scan(root).findings if f.category == "param_rule"]


def test_param_flag_reports_other_lines(tmp_path):
    root = _write(tmp_path, {"app.py": _call() + 'r2 = client.messages.create(model="claude-opus-5", top_p=0.5, messages=[])\n'})
    (p,) = [f for f in _scan(root).findings if f.category == "param_rule"]
    assert "Also set on line(s) 5" in " ".join(p.notes)


def test_param_flag_outputs(tmp_path):
    root = _write(tmp_path, {"app.py": _call(version="2026-10-21")})
    res = _scan(root)
    ann = github_annotations(res, base=root)
    assert any(a.startswith("::error ") and "title=API parameter temperature" in a and WORDING in a for a in ann)
    summ = to_summary_markdown(res)
    assert "| high | `app.py:4` | `temperature` |" in summ
    d = res.to_dict()
    assert d["summary"]["by_category"].get("param_rule") == 1


def test_model_independent_rules_are_anthropic_only():
    """The free-scan file flag and the model-independent fixer path only touch rules with no `applies_to`.
    Every OpenAI, Google and Foundry rule has one, so their findings are unchanged."""
    ps = load_packs(offline=True)
    assert {r["id"] for r in model_independent_rules(ps.get("anthropic"))} == {ERR, WARN}
    for prov in ("openai", "google", "azure-foundry"):
        assert model_independent_rules(ps.get(prov)) == []


# ------------------------------------------------------------------ azure-foundry is fetched by this build
class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def test_this_build_bundles_and_fetches_azure_foundry(tmp_path):
    assert "azure-foundry" in pk.bundled_providers()
    site = build_site(tmp_path / "site")
    p = site / "v1" / "packs" / "azure-foundry.json"
    d = json.loads(p.read_text())
    d["version"] = "2099.01.01"
    p.write_text(json.dumps(d))
    idx = json.loads((site / "v1" / "index.json").read_text())
    for e in idx["packs"]:
        if e["provider"] == "azure-foundry":
            e["version"], e["sha256"] = "2099.01.01", hashlib.sha256(p.read_bytes()).hexdigest()
    (site / "v1" / "index.json").write_text(json.dumps(idx))
    srv = HTTPServer(("127.0.0.1", 0), partial(_Quiet, directory=str(site)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        ps = load_packs(offline=False, url=f"http://127.0.0.1:{srv.server_port}/v1")
        a = ps.get("azure-foundry")
        assert a.source == "remote" and a.version == "2099.01.01"
    finally:
        srv.shutdown()


def test_wheel_package_data_includes_all_packs():
    toml = (ROOT / "pyproject.toml").read_text()
    assert '"migration_kit.pack_data" = ["*.json"]' in toml
    assert "recursive-include migration_kit/pack_data *.json" in (ROOT / "MANIFEST.in").read_text()
