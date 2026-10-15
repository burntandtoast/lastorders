import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from conftest import ROOT
from migration_kit import evaluator as ev

SUITE = ROOT / "examples" / "evals" / "sample-suite.yaml"


def test_dry_run_sample_suite():
    suite = ev.load_suite(SUITE)
    res = ev.run_suite(suite, ev.MockProvider())
    st = {c["id"]: c["status"] for c in res["cases"]}
    assert st["ticket-summary-refund"] == "pass"
    assert st["ticket-summary-question"] == "drift"
    assert st["book-table-simple"] == "pass"
    assert st["book-table-relative-date"] == "fail"    # date no longer matches schema pattern
    assert st["apology-tone"] == "pass"
    assert res["mode"] == "mock"
    c = [c for c in res["cases"] if c["id"] == "book-table-relative-date"][0]
    paths = {d["path"] for d in c["checks"]["argument_diff"][0]["diff"]}
    assert paths == {"date", "time"}


def test_mock_without_canned_outputs_is_valid():
    suite = {"models": {"old": "a", "new": "b"}, "cases": [
        {"id": "s", "type": "structured", "prompt": "x",
         "schema": {"type": "object", "properties": {"n": {"type": "integer"}, "e": {"enum": ["x", "y"]}},
                    "required": ["n", "e"]}},
        {"id": "t", "type": "tool_call", "prompt": "x",
         "tools": [{"name": "f", "parameters": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}}]},
        {"id": "x", "type": "text", "prompt": "hello"}]}
    res = ev.run_suite(suite, ev.MockProvider())
    assert all(c["status"] == "pass" for c in res["cases"]), res


def test_compare_detects_wrong_tool_and_invalid_json():
    case = {"id": "c", "type": "tool_call", "prompt": "p",
            "tools": [{"name": "a", "parameters": {"type": "object"}}, {"name": "b", "parameters": {"type": "object"}}]}
    r = ev.compare(case, ev.ModelOutput(tool_calls=[ev.ToolCall("a", {})]), ev.ModelOutput(tool_calls=[ev.ToolCall("b", {})]))
    assert r.status == "drift" and r.checks["tool_names"]["match"] is False
    case2 = {"id": "s", "type": "structured", "prompt": "p", "schema": {"type": "object"}}
    r2 = ev.compare(case2, ev.ModelOutput(text="{}"), ev.ModelOutput(text="not json"))
    assert r2.status == "fail" and r2.checks["schema_valid"] == {"old": True, "new": False}
    r3 = ev.compare(case2, ev.ModelOutput(text="{}"), ev.ModelOutput(error="HTTP 404"))
    assert r3.status == "error"


def test_make_provider_without_key_falls_back_to_mock(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    p, warn = ev.make_provider({}, dry_run=False)
    assert isinstance(p, ev.MockProvider) and "OPENAI_API_KEY" in warn
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    p, _ = ev.make_provider({}, dry_run=False)
    assert isinstance(p, ev.OpenAIProvider)
    p, _ = ev.make_provider({}, dry_run=True)
    assert isinstance(p, ev.MockProvider)


def test_request_shapes():
    suite = ev.load_suite(SUITE)
    case = [c for c in suite["cases"] if c["id"] == "book-table-simple"][0]
    path, body = ev.OpenAIProvider("k", "chat").build_request(case, "gpt-6-luna", "new", suite)
    assert path == "/chat/completions" and body["reasoning_effort"] == "none"
    assert body["tools"][0]["type"] == "function" and body["tools"][0]["function"]["name"] == "book_table"
    path, body = ev.OpenAIProvider("k", "chat").build_request(case, "gpt-4o-2024-08-06", "old", suite)
    assert "reasoning_effort" not in body
    s = [c for c in suite["cases"] if c["type"] == "structured"][0]
    path, body = ev.OpenAIProvider("k", "responses").build_request(s, "gpt-6-luna", "new", suite)
    assert path == "/responses" and body["text"]["format"]["type"] == "json_schema"


class _FakeOpenAI(BaseHTTPRequestHandler):
    seen = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _FakeOpenAI.seen.append((self.path, self.headers.get("Authorization"), body))
        if body.get("tools"):
            msg = {"role": "assistant", "content": None, "tool_calls": [{"id": "1", "type": "function", "function": {
                "name": "book_table", "arguments": json.dumps({"date": "2026-11-02", "time": "19:30", "party_size": 4})}}]}
        elif body.get("response_format"):
            msg = {"role": "assistant", "content": json.dumps({"summary": "s", "priority": "high", "tags": []})}
        else:
            msg = {"role": "assistant", "content": "Sorry about that."}
        out = json.dumps({"choices": [{"message": msg}], "usage": {"total_tokens": 5}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def test_live_path_against_fake_server(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), _FakeOpenAI)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{srv.server_port}/v1")
        suite = ev.load_suite(SUITE)
        p, _ = ev.make_provider(suite, dry_run=False)
        res = ev.run_suite(suite, p)
        assert res["mode"] == "openai"
        st = {c["id"]: c["status"] for c in res["cases"]}
        assert st["book-table-simple"] == "pass" and st["ticket-summary-refund"] == "pass"
        assert all(a == "Bearer sk-test" for _, a, _ in _FakeOpenAI.seen)
        assert all(path == "/v1/chat/completions" for path, _, _ in _FakeOpenAI.seen)
    finally:
        srv.shutdown()


def test_responses_parse():
    p = ev.OpenAIProvider("k", "responses")
    o = p.parse({"output": [{"type": "function_call", "name": "f", "arguments": '{"a": 1}'},
                            {"type": "message", "content": [{"type": "output_text", "text": "hi"}]}]})
    assert o.tool_calls[0].name == "f" and o.tool_calls[0].arguments == {"a": 1} and o.text == "hi"


def test_bad_suite_rejected(tmp_path):
    f = tmp_path / "s.yaml"
    f.write_text("cases:\n  - id: a\n    type: structured\n    prompt: x\n")
    with pytest.raises(ValueError):
        ev.load_suite(f)
