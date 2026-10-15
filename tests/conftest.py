import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TODAY = dt.date(2026, 10, 15)   # fixed so date-based risk is deterministic
TEST_LICENCE = "BTM-TEST-0000-0000"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path_factory):
    monkeypatch.setenv("MODELMIGRATE_OFFLINE", "1")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))
    monkeypatch.delenv("MODELMIGRATE_LICENCE", raising=False)
    monkeypatch.delenv("MODELMIGRATE_PACKS_URL", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)


@pytest.fixture
def licensed(monkeypatch):
    monkeypatch.setenv("MODELMIGRATE_LICENCE", TEST_LICENCE)
