import datetime as dt
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TODAY = dt.date(2026, 10, 15)   # fixed so date-based risk is deterministic
TEST_LICENCE = "BTM-TEST-0000-0000"
TEST_REPO = "github.com/test/repo"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path_factory):
    monkeypatch.setenv("LASTORDERS_OFFLINE", "1")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))
    for var in ("LASTORDERS_LICENCE", "LASTORDERS_PACKS_URL", "LASTORDERS_LICENCE_URL", "LASTORDERS_REPO",
                "LASTORDERS_LICENCE_DEV_PUBLIC_KEYS", "GITHUB_REPOSITORY"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def _checkout_has_no_origin(monkeypatch):
    """Licence tests treat this tree as a folder with no git origin, so LASTORDERS_REPO is the identity.

    A GitHub Actions checkout has origin. Hide that URL only. Repos a test creates keep theirs.
    """
    from migration_kit import licence

    real_run = subprocess.run

    def run(args, *a, **kw):
        if isinstance(args, (list, tuple)) and list(args[-3:]) == ["config", "--get", "remote.origin.url"]:
            cwd = kw.get("cwd") or Path.cwd()
            top = real_run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True)
            if top.returncode == 0 and Path(top.stdout.strip()).resolve() == ROOT.resolve():
                return subprocess.CompletedProcess(list(args), 1, stdout="", stderr="")
        return real_run(args, *a, **kw)

    monkeypatch.setattr(licence.subprocess, "run", run)


@pytest.fixture(autouse=True)
def licence_server(monkeypatch):
    """Never talk to a real licence server in tests. A fake one (same contract as server/) signs with a
    throwaway key; TEST_LICENCE is pre-verified for TEST_REPO, which is the repo identity of any test
    folder without a git remote, so offline paid-command tests use the cached-token path."""
    from licence_fake import FakeLicenceServer
    from migration_kit import licence
    srv = FakeLicenceServer()
    monkeypatch.setattr(licence, "PUBLIC_KEYS", {srv.kid: srv.public_x})
    monkeypatch.setattr(licence, "_transport", srv.transport)
    monkeypatch.setenv("LASTORDERS_LICENCE_URL", "https://licence.invalid/api/licence/verify")
    monkeypatch.setenv("LASTORDERS_REPO", TEST_REPO)
    srv.add(TEST_LICENCE, TEST_REPO)
    licence._save(TEST_LICENCE, TEST_REPO, srv.token(TEST_LICENCE, TEST_REPO))
    return srv


@pytest.fixture
def licensed(monkeypatch):
    monkeypatch.setenv("LASTORDERS_LICENCE", TEST_LICENCE)
