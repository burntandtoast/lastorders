"""Regression tests for request-format fixes made after the 15 Oct 2026 live run."""
import os

import pytest
from conftest import ROOT
from migration_kit import evaluator as ev
from migration_kit.scanner import scan

SUITE = ROOT / "examples" / "evals" / "sample-suite.yaml"


def test_output_cap_uses_max_completion_tokens_not_max_tokens():
    suite = ev.load_suite(SUITE)
    case = suite["cases"][0]
    _, body = ev.OpenAIProvider("k", "chat").build_request(case, "gpt-6-luna", "new", suite)
    assert body["max_completion_tokens"] == 300 and "max_tokens" not in body
    _, body = ev.OpenAIProvider("k", "responses").build_request(case, "gpt-6-luna", "new", suite)
    assert body["max_output_tokens"] == 300 and "max_completion_tokens" not in body


def test_reasoning_effort_translated_for_responses():
    suite = ev.load_suite(SUITE)
    case = [c for c in suite["cases"] if c["type"] == "tool_call"][0]
    _, body = ev.OpenAIProvider("k", "responses").build_request(case, "gpt-6-luna", "new", suite)
    assert body["reasoning"] == {"effort": "none"} and "reasoning_effort" not in body
    assert body["tools"][0]["name"] == "book_table"


def test_truncation_and_resolved_model_parsed():
    o = ev.OpenAIProvider("k", "chat").parse(
        {"model": "gpt-4o-2024-08-06", "choices": [{"finish_reason": "length", "message": {"content": "{"}}]})
    assert o.truncated and o.resolved_model == "gpt-4o-2024-08-06"
    o = ev.OpenAIProvider("k", "responses").parse({"status": "incomplete", "output": []})
    assert o.truncated


def test_ignore_fields():
    case = {"id": "s", "type": "structured", "prompt": "p", "ignore_fields": ["summary"],
            "schema": {"type": "object"}}
    r = ev.compare(case, ev.ModelOutput(text='{"summary": "a", "p": 1}'), ev.ModelOutput(text='{"summary": "b", "p": 1}'))
    assert r.status == "pass" and r.checks["field_diff"] == []
    r = ev.compare(case, ev.ModelOutput(text='{"summary": "a", "p": 1}'), ev.ModelOutput(text='{"summary": "b", "p": 2}'))
    assert r.status == "drift"


def test_cost_estimate():
    res = [ev.CaseResult("a", "text", "pass", {"usage": {"prompt_tokens": 1_000_000, "completion_tokens": 0}},
                         {"usage": {"input_tokens": 0, "output_tokens": 1_000_000}}, {}, [])]
    u = ev.usage_and_cost(res, {"o": {"input": 2.5, "output": 10}, "n": {"input": 0.1, "output": 0.5}}, "o", "n")
    assert u["old"]["est_cost_usd"] == 2.5 and u["new"]["est_cost_usd"] == 0.5 and u["total_est_cost_usd"] == 3.0


def test_scan_flags_max_tokens_and_sampling_as_high():
    fs = {(f.file, f.model): f for f in scan(ROOT / "examples" / "sample-app").findings}
    s = fs[("app/summarise.py", "gpt-4o-2024-08-06")]
    assert s.risk == "high" and any("max_completion_tokens" in n for n in s.notes)
    assert any("temperature" in n for n in s.notes)
    j = fs[("config/settings.json", "gpt-4o-2024-11-20")]       # max_tokens in JSON config
    assert j.risk == "high"


def test_reasoning_effort_none_suppresses_tool_warning(tmp_path):
    (tmp_path / "a.py").write_text('client.chat.completions.create(model="gpt-4o", tools=T, reasoning_effort="none")\n')
    f = scan(tmp_path).findings[0]
    assert f.risk == "medium" and not any("reasoning_effort is 'none'" in n for n in f.notes)


@pytest.mark.skipif(not os.environ.get("RUN_LIVE_TESTS"), reason="set RUN_LIVE_TESTS=1 (and OPENAI_API_KEY) to hit the real API")
def test_live_smoke():
    suite = ev.load_suite(SUITE)
    suite["cases"] = [c for c in suite["cases"] if c["id"] == "order-lookup"]
    res = ev.run_suite(suite, ev.OpenAIProvider(os.environ["OPENAI_API_KEY"], "chat"))
    assert res["cases"][0]["status"] in ("pass", "drift")
