import hashlib
import json
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler

import pytest
import yaml
from conftest import ROOT
from migration_kit import packs as pk
from migration_kit.site import build_site


def test_bundled_packs_valid_and_listed():
    assert {"openai", "anthropic"} <= set(pk.bundled_providers())
    for prov in pk.bundled_providers():
        pk.validate(json.loads((ROOT / "migration_kit" / "pack_data" / f"{prov}.json").read_text()))


def test_engine_code_has_no_provider_specific_strings():
    for mod in ["scanner.py", "swapper.py", "report.py", "packs.py", "fixer/engine.py", "fixer/pyfix.py",
                "fixer/jsfix.py", "fixer/callsite.py"]:
        src = (ROOT / "migration_kit" / mod).read_text()
        for word in ["gpt-6-luna", "gpt-4o", "claude-", "max_completion_tokens", "reasoning_effort", "max_tokens",
                     "temperature", "openai", "anthropic", "chat_completions", "responses_api"]:
            assert word not in src, f"{word} hard-coded in {mod}"


def test_invalid_pack_rejected():
    bad = json.loads((ROOT / "migration_kit" / "pack_data" / "anthropic.json").read_text())
    bad["version"] = "latest"
    with pytest.raises(ValueError):
        pk.validate(bad)
    bad = json.loads((ROOT / "migration_kit" / "pack_data" / "anthropic.json").read_text())
    bad["id_patterns"] = [{"pattern": "(unclosed"}]
    with pytest.raises(Exception):
        pk.validate(bad)


def _serve(directory):
    srv = HTTPServer(("127.0.0.1", 0), partial(_Quiet, directory=str(directory)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def test_remote_pack_newer_version_wins_and_is_cached(tmp_path, monkeypatch):
    site = build_site(tmp_path / "site")
    p = site / "v1" / "packs" / "anthropic.json"
    d = json.loads(p.read_text())
    d["version"] = "2099.01.01"
    d["models"][0]["replacement"] = "claude-from-remote"
    p.write_text(json.dumps(d))
    idx = json.loads((site / "v1" / "index.json").read_text())
    for e in idx["packs"]:
        if e["provider"] == "anthropic":
            e["version"], e["sha256"] = "2099.01.01", hashlib.sha256(p.read_bytes()).hexdigest()
    (site / "v1" / "index.json").write_text(json.dumps(idx))
    srv = _serve(site)
    try:
        url = f"http://127.0.0.1:{srv.server_port}/v1"
        ps = pk.load_packs(offline=False, url=url)
        a = ps.get("anthropic")
        assert a.source == "remote" and a.version == "2099.01.01"
        assert ps.get("openai").source == "bundled"          # same version as bundled -> keep bundled
    finally:
        srv.shutdown()
    # server gone: fresh cache is used without network
    ps = pk.load_packs(offline=False, url="http://127.0.0.1:9/v1")
    assert ps.get("anthropic").source == "cache"


def test_remote_tampered_pack_ignored(tmp_path):
    site = build_site(tmp_path / "site")
    p = site / "v1" / "packs" / "openai.json"
    d = json.loads(p.read_text())
    d["version"] = "2099.01.01"
    p.write_text(json.dumps(d))                                 # sha256 in index now wrong
    srv = _serve(site)
    try:
        ps = pk.load_packs(offline=False, url=f"http://127.0.0.1:{srv.server_port}/v1")
        assert ps.get("openai").source == "bundled"
    finally:
        srv.shutdown()


def test_unreachable_remote_falls_back_to_bundled():
    ps = pk.load_packs(offline=False, url="http://127.0.0.1:9/v1")
    assert all(p.source == "bundled" and "remote unavailable" in p.source_detail for p in ps)


def test_site_build(tmp_path):
    site = build_site(tmp_path / "site")
    idx = json.loads((site / "v1" / "index.json").read_text())
    assert {e["provider"] for e in idx["packs"]} == {"openai", "anthropic", "google"}
    for e in idx["packs"]:
        assert hashlib.sha256((site / "v1" / e["url"]).read_bytes()).hexdigest() == e["sha256"]
    assert (site / "vercel.json").exists() and (site / "_headers").exists() and (site / "index.html").exists()
    assert (site / "v1" / "pack.schema.json").exists()


def test_unknown_provider_in_remote_index_is_skipped(tmp_path):
    """0.4.0 and 0.4.1 only fetch providers they bundle. A new index entry must not
    be downloaded or validated, and must not fail the providers they do know."""
    site = build_site(tmp_path / "site")
    idx_path = site / "v1" / "index.json"
    idx = json.loads(idx_path.read_text())
    idx["packs"].append({
        "provider": "future", "name": "Future", "version": "2099.01.01", "status": "stable",
        "pack_format": 1, "url": "packs/future.json", "sha256": "0" * 64,
    })
    idx["packs"].append({"provider": "broken"})  # missing fields; still skipped
    idx_path.write_text(json.dumps(idx))
    srv = _serve(site)
    try:
        url = f"http://127.0.0.1:{srv.server_port}/v1"
        remote, err = pk._fetch_remote(url, ["openai", "anthropic"])
        assert err is None
        assert set(remote) <= {"openai", "anthropic"}
        assert "google" not in remote and "future" not in remote
        ps = pk.load_packs(["openai", "anthropic"], offline=False, url=url)
        assert {p.provider for p in ps} == {"openai", "anthropic"}
        assert all(p.source == "bundled" for p in ps)
    finally:
        srv.shutdown()


def test_action_yml_shape():
    a = yaml.safe_load((ROOT / "action.yml").read_text())
    assert a["runs"]["using"] == "composite"
    assert {"path", "fail-on-high", "packs", "offline"} <= set(a["inputs"])
    uses = [s.get("uses", "") for s in a["runs"]["steps"]]
    assert any(u.startswith("actions/upload-artifact@") for u in uses)
    wf = yaml.safe_load((ROOT / "examples" / "workflows" / "model-scan.yml").read_text())
    assert "scan" in wf["jobs"]
