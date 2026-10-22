"""23 Oct 2026 mapping, live-tested Chat Completions rewrites, and pack gaps."""
import datetime as dt
import json
import os
import subprocess
import sys

from conftest import ROOT

from migration_kit.fixer import plan_fixes
from migration_kit.packs import load_packs
from migration_kit.scanner import scan

TODAY_SCAN = dt.date(2026, 10, 15)

OCT23_SOL = {
    "gpt-4o-2024-05-13", "gpt-4", "gpt-4-0613", "gpt-4-turbo", "gpt-4-turbo-2024-04-09",
    "gpt-4-1106-preview", "gpt-4-completions", "gpt-4-0613-completions", "gpt-4-turbo-completions",
    "o1", "o1-2024-12-17", "o3-mini", "o3-mini-2025-01-31",
}
OCT23_LUNA = {"gpt-4.1-nano", "gpt-4.1-nano-2025-04-14"}
OCT23_TERRA = {
    "gpt-3.5-turbo", "gpt-3.5-turbo-0125", "gpt-3.5-turbo-completions",
    "o4-mini", "o4-mini-2025-04-16",
}
FLAG_ONLY = {
    "o1-pro", "o1-pro-2025-03-19", "gpt-image-1", "ft-o4-mini-2025-04-16",
    "davinci-002", "babbage-002", "gpt-3.5-turbo-instruct", "gpt-3.5-turbo-1106",
    "computer-use-preview", "computer-use-preview-2025-03-11", "gpt-5.2-codex",
    "gpt-4o-mini-transcribe-2025-03-20",
}


def test_default_mapping_includes_oct23_chat_and_reasoning():
    mapping = load_packs().get("openai").default_mapping(None)
    assert {mid: mapping[mid] for mid in OCT23_SOL} == {mid: "gpt-5.6-sol" for mid in OCT23_SOL}
    assert {mid: mapping[mid] for mid in OCT23_LUNA} == {mid: "gpt-5.6-luna" for mid in OCT23_LUNA}
    assert {mid: mapping[mid] for mid in OCT23_TERRA} == {mid: "gpt-5.6-terra" for mid in OCT23_TERRA}
    assert not FLAG_ONLY & set(mapping)
    assert mapping["gpt-4o-2024-08-06"] == "gpt-6-luna"
    assert "gpt-4o-transcribe" not in mapping


def test_pack_gaps_and_already_retired(tmp_path):
    (tmp_path / "a.py").write_text(
        'a = "gpt-4o-mini-transcribe-2025-03-20"\n'
        'b = "davinci-002"\n'
        'c = "babbage-002"\n'
        'd = "text-davinci-002"\n'
        'e = "computer-use-preview"\n'
        'f = "computer-use-preview-2025-03-11"\n'
        'g = "gpt-3.5-turbo-instruct"\n'
        'h = "gpt-3.5-turbo-1106"\n'
        'i = "gpt-5.2-codex"\n'
        'j = "gpt-5-codex"\n'
        'k = "gpt-5.1-codex-max"\n'
        'l = "gpt-5.1-codex-mini"\n'
        'm = "o3-deep-research"\n'
        'n = "o4-mini-deep-research-2025-06-26"\n'
        'o = "gpt-audio-mini-2025-10-06"\n'
        'o2 = "gpt-realtime-mini-2025-10-06"\n'
        'o3 = "gpt-audio-1.5"\n'
        'o4 = "gpt-realtime-2.1"\n'
        'p = "ft-o4-mini-2025-04-16"\n'
        'q = "gpt-image-1"\n'
        'r = "o1-pro"\n'
    )
    found = {f.model: f for f in scan(tmp_path, today=TODAY_SCAN).findings}
    assert "text-davinci-002" not in found
    assert "gpt-audio-1.5" not in found and "gpt-realtime-2.1" not in found
    tr = found["gpt-4o-mini-transcribe-2025-03-20"]
    assert tr.category != "not_listed"
    assert tr.shutdown == "2027-01-20" and tr.suggested == "gpt-4o-mini-transcribe-2025-12-15"
    for mid in ("davinci-002", "babbage-002", "gpt-3.5-turbo-instruct", "gpt-3.5-turbo-1106"):
        f = found[mid]
        assert f.shutdown == "2026-09-28" and f.suggested == "gpt-5.6-terra" and f.risk == "high", mid
        assert any("has passed" in n for n in f.notes) and any("Already shut down" in n for n in f.notes)
    for mid, repl in (
        ("computer-use-preview", "gpt-5.6-terra"),
        ("computer-use-preview-2025-03-11", "gpt-5.6-terra"),
        ("gpt-5.2-codex", "gpt-5.6-sol"),
        ("gpt-5-codex", "gpt-5.6-sol"),
        ("gpt-5.1-codex-max", "gpt-5.6-sol"),
        ("gpt-5.1-codex-mini", "gpt-5.6-terra"),
        ("o3-deep-research", "gpt-5.6-sol"),
        ("o4-mini-deep-research-2025-06-26", "gpt-5.6-sol"),
        ("gpt-audio-mini-2025-10-06", "gpt-audio-1.5"),
        ("gpt-realtime-mini-2025-10-06", "gpt-realtime-2.1-mini"),
    ):
        f = found[mid]
        assert f.category != "not_listed" and f.shutdown == "2026-07-23" and f.suggested == repl, mid
        assert f.risk == "high" and any("has passed" in n for n in f.notes)
    assert found["gpt-image-1"].suggested.startswith("gpt-image-2.5")
    assert found["o1-pro"].shutdown == "2026-10-23"
    assert any("reasoning.mode" in n for n in found["o1-pro"].notes)
    assert found["ft-o4-mini-2025-04-16"].category != "not_listed"
    assert "ft-o4-mini-2025-04-16" not in load_packs().get("openai").default_mapping(None)


def test_vertex_live_audio_and_flash_image(tmp_path):
    (tmp_path / "live.py").write_text(
        'import vertexai\nmodel = "gemini-live-2.5-flash-native-audio"\n')
    (tmp_path / "image.py").write_text(
        'from google.cloud import aiplatform\nmodel = "gemini-2.5-flash-image"\n')
    (tmp_path / "studio.py").write_text(
        'model = "gemini-live-2.5-flash-native-audio"\nimage = "gemini-2.5-flash-image"\n')
    (tmp_path / "preview.py").write_text(
        'model = "gemini-live-2.5-flash-preview-native-audio-09-2025"\n'
        'old = "gemini-2.5-pro-preview-06-05"\n')
    found = {}
    for f in scan(tmp_path, today=TODAY_SCAN).findings:
        found.setdefault(f.file, {})[f.model] = f
    live = found["live.py"]["gemini-live-2.5-flash-native-audio"]
    assert live.provider == "google" and live.shutdown == "2026-12-13" and live.suggested is None
    assert live.category == "in_scope" and live.risk == "info"
    assert any("no replacement model ID" in n for n in live.notes)
    image = found["image.py"]["gemini-2.5-flash-image"]
    assert image.shutdown == "2027-03-15" and image.suggested == "gemini-3.1-flash-lite-image"
    assert image.risk == "info" and image.category == "in_scope"
    studio = found["studio.py"]
    assert studio["gemini-live-2.5-flash-native-audio"].risk == "info"
    assert "retires on Vertex AI; not deprecated on the Gemini API" in studio["gemini-2.5-flash-image"].notes
    assert "preview.py" not in found
    assert load_packs().get("google").default_mapping(None) == {}


def test_fixer_rewrites_verified_chat_parameters_with_the_model_switch(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text(
        "from openai import OpenAI\n"
        "c = OpenAI()\n"
        "c.chat.completions.create(model=\"gpt-4-turbo\", messages=[], max_tokens=32, temperature=0.2, top_p=0.9)\n"
        "c.chat.completions.create(model=\"gpt-4.1-nano\", messages=[], tools=[{\"type\": \"function\", \"function\": {\"name\": \"ping\"}}])\n"
        "c.responses.create(model=\"o4-mini\", input=\"hi\", max_tokens=20, temperature=0.4)\n"
        "c.chat.completions.create(model=\"gpt-3.5-turbo\", messages=[])\n"
        "c.chat.completions.create(model=\"o1\", messages=[], max_completion_tokens=16)\n"
        "c.beta.assistants.create(model=\"gpt-4\", name=\"n\")\n"
        "c.completions.create(model=\"gpt-4-0613\", prompt=\"hi\", max_tokens=50)\n"
        "c.fine_tuning.jobs.create(model=\"gpt-4o-2024-05-13\", training_file=\"file-x\")\n"
        "c.chat.completions.create(model=\"o1-pro\", messages=[], max_tokens=16)\n"
        "c.chat.completions.create(model=\"gpt-image-1\", messages=[])\n"
        "c.chat.completions.create(model=\"ft:gpt-3.5-turbo-0125:acme::abc123\", messages=[])\n"
    )
    res = plan_fixes(repo, load_packs(offline=True))
    text = res.new_contents["app.py"]
    lines = text.splitlines()
    assert 'model="gpt-5.6-sol"' in lines[2]
    assert "max_completion_tokens=32" in lines[2] and 'reasoning_effort="none"' in lines[2]
    assert "max_tokens=32" not in lines[2]
    assert 'model="gpt-5.6-luna"' in lines[3] and 'reasoning_effort="none"' in lines[3]
    # Responses was not probed, so the id swaps and the parameters stay.
    assert lines[4] == 'c.responses.create(model="gpt-5.6-terra", input="hi", max_tokens=20, temperature=0.4)'
    assert lines[5] == 'c.chat.completions.create(model="gpt-5.6-terra", messages=[])'
    assert "reasoning_effort" not in lines[6]
    assert 'model="gpt-5.6-sol"' in lines[6] and "max_completion_tokens=16" in lines[6]
    assert 'model="gpt-4", name="n"' in text
    assert 'model="gpt-4-0613", prompt="hi", max_tokens=50' in text
    assert 'model="gpt-4o-2024-05-13", training_file="file-x"' in text
    assert 'model="o1-pro", messages=[], max_tokens=16' in text
    assert 'model="gpt-image-1"' in text
    assert "ft:gpt-3.5-turbo-0125:acme::abc123" in text
    assert "max_output_tokens" not in text

    items = {(i.line, i.rule): i for i in res.items}
    assert items[(3, "gpt56-max-tokens")].status == "fixed"
    assert "max_completion_tokens" in items[(3, "gpt56-max-tokens")].change
    assert items[(3, "gpt56-sampling")].status == "fixed"
    assert 'reasoning_effort' in items[(3, "gpt56-sampling")].change
    assert items[(4, "gpt56-chat-tools")].status == "fixed"
    assert items[(5, "gpt56-max-tokens")].status == "manual"
    assert "responses_api" in items[(5, "gpt56-max-tokens")].change
    assert items[(5, "gpt56-sampling")].status == "manual"
    assert "responses_api" in items[(5, "gpt56-sampling")].change
    assert (6, "gpt56-max-tokens") not in items and (6, "gpt56-sampling") not in items
    assert items[(8, "gpt56-assistants")].status == "manual"
    assert "kept on `gpt-4`" in items[(8, "gpt56-assistants")].change
    assert items[(9, "gpt56-legacy-completions")].status == "manual"
    assert "kept on `gpt-4-0613`" in items[(9, "gpt56-legacy-completions")].change
    assert items[(9, "gpt56-max-tokens")].status == "manual"
    assert items[(10, "gpt56-fine-tuning-jobs")].status == "manual"
    assert any(i.rule == "fine-tune" and i.status == "manual" for i in res.items)
    # o1-pro is not swapped, so max_tokens stays and is only suggested with the switch
    assert items[(11, "gpt56-max-tokens")].status == "manual"
    assert "only together with switching" in items[(11, "gpt56-max-tokens")].change
    rules = {r["id"]: r for r in load_packs(offline=True).get("openai").data["rules"]}
    for rid in ("gpt56-max-tokens", "gpt56-sampling", "gpt56-chat-tools"):
        assert rules[rid]["confidence"] == "live-tested"
        assert rules[rid]["fix"]["requires_new_model"] is True
        assert "probe_56-result.json" in rules[rid]["evidence"]


def test_fixer_leaves_temperature_one_and_flags_effort_max(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text(
        "from openai import OpenAI\n"
        "c = OpenAI()\n"
        "c.chat.completions.create(model=\"gpt-4\", messages=[], temperature=1, max_tokens=8)\n"
        "c.chat.completions.create(model=\"o3-mini\", messages=[], temperature=0.2, reasoning_effort=\"none\", max_tokens=8)\n"
        "c.chat.completions.create(model=\"gpt-4-turbo\", messages=[], reasoning_effort=\"max\")\n"
        "c.chat.completions.create(model=\"gpt-5.6-sol\", messages=[], max_tokens=4, tools=[{\"type\": \"function\", \"function\": {\"name\": \"ping\"}}])\n"
    )
    res = plan_fixes(repo, load_packs(offline=True))
    lines = res.new_contents["app.py"].splitlines()
    assert "max_completion_tokens=8" in lines[2] and "temperature=1" in lines[2]
    assert "reasoning_effort" not in lines[2]
    assert 'reasoning_effort="none"' in lines[3] and "max_completion_tokens=8" in lines[3]
    assert lines[3].count("reasoning_effort") == 1
    assert 'model="gpt-5.6-sol"' in lines[4] and 'reasoning_effort="max"' in lines[4]
    assert "max_completion_tokens=4" in lines[5] and 'reasoning_effort="none"' in lines[5]
    items = {(i.line, i.rule): i for i in res.items}
    assert (3, "gpt56-sampling") not in items
    assert (4, "gpt56-sampling") not in items
    assert items[(5, "gpt56-effort-max")].status == "manual"
    assert "max" in items[(5, "gpt56-effort-max")].change
    assert items[(6, "gpt56-max-tokens")].status == "fixed"
    assert items[(6, "gpt56-chat-tools")].status == "fixed"
    facts = load_packs(offline=True).get("openai").data["replacement_facts"]
    for mid in ("gpt-5.6-luna", "gpt-5.6-sol", "gpt-5.6-terra"):
        assert facts[mid]["reasoning_effort"] == ["none", "low", "medium", "high", "xhigh"]
        assert facts[mid]["eval"]["model_params"] == {"reasoning_effort": "none"}


def test_probe_56_refuses_without_a_key(tmp_path):
    result = ROOT / "probes" / "probe_56-result.json"
    before = result.read_bytes()
    env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
    proc = subprocess.run(
        [sys.executable, str(ROOT / "probes" / "probe_56.py")],
        check=False, cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert proc.returncode == 2
    assert "OPENAI_API_KEY" in proc.stderr
    assert proc.stdout == ""
    assert result.read_bytes() == before


def test_probe_56_result_matches_gpt6_luna_on_chat():
    rows = json.loads((ROOT / "probes" / "probe_56-result.json").read_text())
    by = {}
    for row in rows:
        kind = row["probe"].split(" chat ", 1)[1]
        by[(row["request_model"], kind)] = row
    for model in ("gpt-5.6-luna", "gpt-5.6-sol", "gpt-5.6-terra"):
        for effort in ("none", "default"):
            rejected = by[(model, f"max_tokens=16 effort={effort}")]
            assert rejected["status"] == 400
            assert "max_completion_tokens" in rejected["error"]["message"]
            assert by[(model, f"max_completion_tokens=16 effort={effort}")]["status"] == 200
            assert by[(model, f"temperature=1 effort={effort}")]["status"] == 200
        assert by[(model, "temperature=0.2 effort=none")]["status"] == 200
        assert by[(model, "top_p=0.9 effort=none")]["status"] == 200
        assert by[(model, "logprobs effort=none")]["status"] == 200
        assert by[(model, "tools effort=none")]["status"] == 200
        assert by[(model, "tools effort=default")]["status"] == 400
        assert "reasoning_effort" in by[(model, "tools effort=default")]["error"]["message"]
        for effort in ("low", "medium", "high", "xhigh"):
            assert by[(model, f"temperature=0.2 effort={effort}")]["status"] == 400
            assert by[(model, f"top_p=0.9 effort={effort}")]["status"] == 400
            assert by[(model, f"logprobs effort={effort}")]["status"] == 400
            assert by[(model, f"tools effort={effort}")]["status"] == 400
        rejected_max = by[(model, "temperature=0.2 effort=max")]
        assert rejected_max["status"] == 400
        assert "does not support 'max'" in rejected_max["error"]["message"]


def test_bundled_site_packs_match():
    for name in ("openai", "google", "anthropic", "azure-foundry"):
        bundled = json.loads((ROOT / "migration_kit" / "pack_data" / f"{name}.json").read_text())
        site = json.loads((ROOT / "site" / "v1" / "packs" / f"{name}.json").read_text())
        assert bundled == site
