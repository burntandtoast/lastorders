"""Real licence check: online verify, signed-token cache, offline grace, --offline, error paths."""
import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from conftest import ROOT, TEST_LICENCE, TEST_REPO
from migration_kit import licence
from migration_kit.cli import main

KEY = "BTM-ABCD-EFGH-JK23"
REPO = "github.com/acme/shop"
SAMPLE = ROOT / "examples" / "sample-app"


@pytest.fixture
def online(monkeypatch, licence_server):
    monkeypatch.delenv("LASTORDERS_OFFLINE", raising=False)
    monkeypatch.setenv("LASTORDERS_REPO", REPO)
    licence_server.add(KEY)
    return licence_server


def test_first_use_binds_and_sends_only_key_and_repo(online):
    lic = licence.require("fix-apply", KEY, ".")
    assert lic.verified and lic.mode == "online" and lic.repo_id == REPO
    assert online.calls == [{"url": "https://licence.invalid/api/licence/verify", "payload": {"key": KEY, "repo": REPO}}]
    assert online.keys[KEY]["repo"] == REPO
    assert "verified online" in licence.describe(lic) and "TEST-MODE" in licence.describe(lic)


def test_cached_token_means_no_request_then_refreshes_after_a_day(online):
    licence.require("eval", KEY, ".")
    licence.require("eval", KEY, ".")
    assert len(online.calls) == 1
    lic = licence.resolve(KEY, ".")
    licence.check(lic, now=time.time() + licence.REFRESH_AFTER + 60)
    assert len(online.calls) == 2 and lic.mode == "online"


def test_server_down_uses_cache_then_grace_then_fails(online):
    licence.require("eval", KEY, ".")
    online.down = True
    t0 = time.time()
    lic = licence.check(licence.resolve(KEY, "."), now=t0 + 2 * 86400)
    assert lic.mode == "cached"
    lic = licence.check(licence.resolve(KEY, "."), now=t0 + 10 * 86400)          # token expired, within grace
    assert lic.mode == "grace" and "grace" in licence.describe(lic)
    with pytest.raises(licence.LicenceError, match="Couldn't reach the licence server"):
        licence.check(licence.resolve(KEY, "."), now=t0 + 7 * 86400 + licence.GRACE + 60)


def test_never_verified_and_unreachable_fails(online):
    online.down = True
    with pytest.raises(licence.LicenceError, match="no recent verification"):
        licence.require("eval", KEY, ".")


def test_offline_flag_uses_cache_only(online):
    with pytest.raises(licence.LicenceError, match="--offline: there's no cached verification"):
        licence.require("eval", KEY, ".", offline=True)
    assert online.calls == []
    licence.require("eval", KEY, ".")
    t0 = time.time()
    assert licence.check(licence.resolve(KEY, "."), offline=True).mode == "offline-cache"
    assert licence.check(licence.resolve(KEY, "."), offline=True, now=t0 + 8 * 86400).mode == "offline-grace"
    with pytest.raises(licence.LicenceError, match="run out"):
        licence.check(licence.resolve(KEY, "."), offline=True, now=t0 + 7 * 86400 + licence.GRACE + 60)
    assert len(online.calls) == 1


def test_env_offline_is_respected(online, monkeypatch):
    monkeypatch.setenv("LASTORDERS_OFFLINE", "1")
    with pytest.raises(licence.LicenceError, match="--offline"):
        licence.require("eval", KEY, ".")
    assert online.calls == []


def test_other_repo_rejected_and_cache_cleared(online, monkeypatch):
    licence.require("eval", KEY, ".")
    monkeypatch.setenv("LASTORDERS_REPO", "github.com/acme/other")
    with pytest.raises(licence.LicenceError, match="already bound to github.com/acme/shop"):
        licence.require("eval", KEY, ".")


def test_revoked_clears_cache_even_with_a_valid_token(online):
    licence.require("eval", KEY, ".")
    online.keys[KEY]["status"] = "revoked"
    with pytest.raises(licence.LicenceError, match="revoked"):
        licence.check(licence.resolve(KEY, "."), now=time.time() + licence.REFRESH_AFTER + 60)
    assert not licence._cache_file(KEY, REPO).exists()
    online.down = True                                          # no grace for a revoked key
    with pytest.raises(licence.LicenceError):
        licence.require("eval", KEY, ".")


def test_unknown_and_malformed_keys(online):
    with pytest.raises(licence.LicenceError, match="not recognised"):
        licence.require("eval", "BTM-ZZZZ-ZZZZ-ZZZZ", ".")
    with pytest.raises(licence.LicenceError, match="format not recognised"):
        licence.require("eval", "nope", ".")
    with pytest.raises(licence.LicenceError, match="no licence key found"):
        licence.require("eval", None, ".")


def test_forged_or_mismatched_tokens_are_rejected(online):
    good = online.token(KEY, REPO)
    assert licence.verify_token(good, KEY, REPO)
    v, body, sig = good.split(".")
    claims = json.loads(licence._b64d(body))
    forged_body = licence.base64.urlsafe_b64encode(json.dumps({**claims, "exp": claims["exp"] + 10**8}).encode()).rstrip(b"=").decode()
    assert licence.verify_token(f"{v}.{forged_body}.{sig}", KEY, REPO) is None
    assert licence.verify_token(good, KEY, "github.com/acme/other") is None
    assert licence.verify_token(good, "BTM-ABCD-EFGH-JK24", REPO) is None
    assert licence.verify_token(online.token(KEY, REPO, kid="unknown"), KEY, REPO) is None
    from licence_fake import FakeLicenceServer
    assert licence.verify_token(FakeLicenceServer().token(KEY, REPO), KEY, REPO) is None     # other signing key
    # a tampered cache file is ignored and replaced by an online check
    licence._save(KEY, REPO, f"{v}.{forged_body}.{sig}")
    assert licence.require("eval", KEY, ".").mode == "online"


def test_server_token_it_cannot_verify_is_not_trusted(online, monkeypatch):
    from licence_fake import FakeLicenceServer
    rogue = FakeLicenceServer()
    rogue.add(KEY)
    monkeypatch.setattr(licence, "_transport", rogue.transport)
    with pytest.raises(licence.LicenceError, match="can't verify"):
        licence.require("eval", KEY, ".")


def test_no_repo_identity_explains_how_to_fix(online, monkeypatch, tmp_path):
    monkeypatch.delenv("LASTORDERS_REPO")
    with pytest.raises(licence.LicenceError, match="LASTORDERS_REPO"):
        licence.require("eval", KEY, tmp_path)


def test_repo_override_and_github_actions(monkeypatch, tmp_path):
    monkeypatch.setenv("LASTORDERS_REPO", "Acme/Shop")
    assert licence.repo_identity(tmp_path) == "github.com/acme/shop"
    monkeypatch.setenv("LASTORDERS_REPO", "https://gitlab.com/acme/shop.git")
    assert licence.repo_identity(tmp_path) == "gitlab.com/acme/shop"
    monkeypatch.setenv("GITHUB_REPOSITORY", "Acme/Actions")
    assert licence.repo_identity(tmp_path) == "github.com/acme/actions"


def test_dev_public_keys_only_for_loopback(monkeypatch):
    monkeypatch.setenv("LASTORDERS_LICENCE_DEV_PUBLIC_KEYS", json.dumps({"dev": "x"}))
    monkeypatch.setenv("LASTORDERS_LICENCE_URL", "https://evil.example/verify")
    assert licence._dev_keys() == {}
    monkeypatch.setenv("LASTORDERS_LICENCE_URL", "http://127.0.0.1:8787/api/licence/verify")
    assert licence._dev_keys() == {"dev": "x"}


def test_shipped_build_has_no_dev_keys_and_buy_link():
    src = (ROOT / "migration_kit" / "licence.py").read_text()
    assert "BEGIN PRIVATE" not in src
    assert licence.buy_url("github.com/acme/shop").endswith("/buy?repo=github.com/acme/shop")


def test_free_scan_needs_no_licence_and_no_network(monkeypatch, tmp_path, licence_server):
    def boom(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setattr(licence, "_transport", boom)
    monkeypatch.delenv("LASTORDERS_OFFLINE")
    assert main(["scan", str(SAMPLE), "--out", str(tmp_path), "--offline"]) == 0


def test_cli_licence_status_and_paid_command_offline(capsys, monkeypatch, tmp_path):
    # conftest pre-verified TEST_LICENCE for TEST_REPO; LASTORDERS_OFFLINE=1 so this is the cache path
    assert main(["licence", "status", str(tmp_path), "--licence", TEST_LICENCE]) == 0
    assert "--offline: cached verification" in capsys.readouterr().out
    assert main(["licence", "buy", str(tmp_path)]) == 0
    assert capsys.readouterr().out.strip().endswith("/buy?repo=" + TEST_REPO)
    assert main(["init-evals", str(SAMPLE), "--out", str(tmp_path / "e"), "--licence", "BTM-NOPE-NOPE-NOPE"]) == 4
    assert "--offline" in capsys.readouterr().err


NODE = shutil.which("node", path=f"/home/box/.local/node22/bin:{os.environ.get('PATH', '')}")


def _node_ok():
    if not NODE or not (ROOT / "server" / "node_modules" / "sql.js").exists():
        return False
    out = subprocess.run([NODE, "-e", "crypto.subtle.generateKey({name:'Ed25519'},true,['sign']).then(()=>console.log('ok'))"],
                         capture_output=True, text=True)
    return out.stdout.strip() == "ok"


@pytest.mark.skipif(not _node_ok(), reason="node 20+ and `npm install` in server/ needed for the end-to-end test")
def test_end_to_end_against_the_real_worker(monkeypatch, tmp_path):
    """Stripe webhook -> key -> CLI online verify (real HTTP) -> bound -> cached; second repo rejected."""
    proc = subprocess.Popen([NODE, "scripts/local-server.mjs", "--issue", "1"], cwd=ROOT / "server",
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        info = json.loads(proc.stdout.readline())
        key = info["keys"][0]
        monkeypatch.delenv("LASTORDERS_OFFLINE")
        monkeypatch.setattr(licence, "_transport", licence._http_post)
        monkeypatch.setattr(licence, "PUBLIC_KEYS", {})
        monkeypatch.setenv("LASTORDERS_LICENCE_URL", info["url"] + "/api/licence/verify")
        monkeypatch.setenv("LASTORDERS_LICENCE_DEV_PUBLIC_KEYS", json.dumps(info["public_keys"]))
        monkeypatch.setenv("LASTORDERS_REPO", "github.com/e2e/one")
        lic = licence.require("fix-apply", key, tmp_path)
        assert lic.mode == "online" and lic.test and lic.expires - time.time() > 6 * 86400
        assert licence.require("fix-apply", key, tmp_path).mode == "cached"
        monkeypatch.setenv("LASTORDERS_REPO", "github.com/e2e/two")
        with pytest.raises(licence.LicenceError, match="already bound to github.com/e2e/one"):
            licence.require("fix-apply", key, tmp_path)
        with urllib.request.urlopen(info["url"] + "/api/licence/public-key", timeout=5) as r:
            assert json.loads(r.read())["keys"][0]["x"] == info["public_keys"]["dev"]
    finally:
        proc.terminate()
        proc.wait(timeout=5)
