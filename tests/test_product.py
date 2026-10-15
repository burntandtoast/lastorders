"""Product decisions: network policy, per-repo licence, init-evals, configurable brand."""
import re
import subprocess
import urllib.request

import pytest
import yaml
from conftest import ROOT, TEST_LICENCE
from migration_kit import brand, licence
from migration_kit.cli import main
from migration_kit.initevals import build_suite

SAMPLE = ROOT / "examples" / "sample-app"


def test_only_pack_fetch_talks_to_us():
    """urllib may only appear in packs.py (pack download), licence.py (key + repo check) and evaluator.py
    (the customer's own provider key)."""
    for f in (ROOT / "migration_kit").rglob("*.py"):
        src = f.read_text()
        if re.search(r"\burllib\b|\brequests\b|\bhttp\.client\b|\bsocket\b", src):
            assert f.name in {"packs.py", "licence.py", "evaluator.py"}, f"network code in {f.name}"
    assert brand.LICENCE_URL.startswith(brand.SERVICE_URL) and brand.PACKS_URL.startswith(brand.SERVICE_URL)


def test_offline_makes_no_network_calls(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.delenv("MODELMIGRATE_OFFLINE", raising=False)
    assert main(["scan", str(SAMPLE), "--out", str(tmp_path), "--offline"]) == 0
    assert main(["swap", str(SAMPLE), "--out", str(tmp_path), "--offline"]) == 0


def test_offline_env_var(tmp_path, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("net")))
    monkeypatch.setenv("MODELMIGRATE_OFFLINE", "1")
    assert main(["scan", str(SAMPLE), "--out", str(tmp_path)]) == 0


@pytest.mark.parametrize("url,expected", [
    ("git@github.com:BurntToast/Shop.git", "github.com/burnttoast/shop"),
    ("https://github.com/burnttoast/shop.git", "github.com/burnttoast/shop"),
    ("https://token@github.com/burnttoast/shop", "github.com/burnttoast/shop"),
    ("ssh://git@github.com/burnttoast/shop.git", "github.com/burnttoast/shop"),
])
def test_remote_normalisation(url, expected):
    assert licence._normalise_remote(url) == expected


def test_licence_is_per_repo_including_monorepo_subfolders(tmp_path, monkeypatch):
    repo = tmp_path / "mono"
    (repo / "packages" / "api").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:acme/mono.git"], cwd=repo, check=True)
    a = licence.resolve(TEST_LICENCE, repo)
    b = licence.resolve(TEST_LICENCE, repo / "packages" / "api")
    assert a.valid and a.repo_id == b.repo_id == "github.com/acme/mono"
    monkeypatch.setenv("GITHUB_REPOSITORY", "Acme/Mono")
    assert licence.resolve(TEST_LICENCE, tmp_path).repo_id == "github.com/acme/mono"
    assert "placeholder" not in licence.__doc__.lower()


def test_init_evals_from_call_sites():
    suite, skipped = build_suite(SAMPLE)
    cases = {c["source"]: c for c in suite["cases"]}
    assert suite["models"] == {"old": "gpt-4o-mini", "new": "gpt-6-luna"}
    assert suite["model_params"]["new"] == {"reasoning_effort": "none"}          # from the pack
    s = cases["app/summarise.py:19"]
    assert s["type"] == "structured" and s["schema"]["properties"]["priority"]["enum"] == ["low", "medium", "high"]
    t = cases["app/agent.py:29"]
    assert t["type"] == "tool_call" and t["tools"][0]["name"] == "book_table"
    ft = cases["app/agent.py:35"]
    assert ft["models"]["old"].startswith("ft:")
    assert cases["web/src/classify.js:7"]["models"]["old"] == "gpt-4.1-mini-2025-04-14"
    assert any("anthropic" in x for x in skipped)


def test_init_evals_cli_gated_and_eval_refuses_todo_live(tmp_path, monkeypatch):
    out = tmp_path / "evals.yaml"
    assert main(["init-evals", str(SAMPLE), "--out", str(out)]) == 4
    assert main(["init-evals", str(SAMPLE), "--out", str(out), "--licence", TEST_LICENCE]) == 0
    y = yaml.safe_load(out.read_text())
    assert len(y["cases"]) == 5 and "NEXT STEPS" in out.read_text()
    assert main(["eval", str(out), "--dry-run", "--out", str(tmp_path), "--licence", TEST_LICENCE]) == 0
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert main(["eval", str(out), "--out", str(tmp_path), "--licence", TEST_LICENCE]) == 5    # TODOs block live run


def test_brand_is_single_source():
    import migration_kit.cli as cli
    assert cli.build_parser().prog == brand.CLI_NAME
    py = (ROOT / "pyproject.toml").read_text()
    assert f'name = "{brand.CLI_NAME}"' in py and f'{brand.CLI_NAME} = "migration_kit.cli:main"' in py
