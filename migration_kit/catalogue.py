"""Deprecation catalogue.

Every entry here was transcribed from OpenAI's deprecations page
(https://developers.openai.com/api/docs/deprecations) and the GPT-6 Luna model
page (https://developers.openai.com/api/docs/models/gpt-6-luna), both read on
2026-10-15. Nothing in this file is inferred unless the entry says so in
``confidence``/``note``. Re-check both pages before every client engagement.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CHECKED_ON = "2026-10-15"
DEPRECATIONS_URL = "https://developers.openai.com/api/docs/deprecations"
LUNA_URL = "https://developers.openai.com/api/docs/models/gpt-6-luna"

PRIMARY_REPLACEMENT = "gpt-6-luna"
PRIMARY_SHUTDOWN = "2027-01-14"


@dataclass(frozen=True)
class Entry:
    model: str
    shutdown: str | None          # ISO date, None if already past / not stated
    replacement: str | None       # as written on the page
    section: str                  # heading on the deprecations page
    confidence: str = "confirmed"  # confirmed | inferred
    note: str = ""
    in_scope: bool = False        # part of the GPT-4o / 4.1 Jan-2027 migration


_GPT4_SECTION = "2026-10-14: GPT-4 series model deprecations"
_LEGACY_OCT = "2026-04-22: Legacy GPT model snapshots (shutdown 23 Oct 2026)"

_ALIAS_NOTE = (
    "Undated alias: OpenAI lists only the dated snapshots, so treating the alias as "
    "affected is inferred. Confirm with GET /v1/models (shutdown_date)."
)

ENTRIES: list[Entry] = [
    # --- In scope: the 14 Jan 2027 GPT-4 series shutdown ------------------
    Entry("gpt-4o-2024-08-06", PRIMARY_SHUTDOWN, PRIMARY_REPLACEMENT, _GPT4_SECTION, in_scope=True),
    Entry("gpt-4o-2024-11-20", PRIMARY_SHUTDOWN, PRIMARY_REPLACEMENT, _GPT4_SECTION, in_scope=True),
    Entry("gpt-4o-mini-2024-07-18", PRIMARY_SHUTDOWN, PRIMARY_REPLACEMENT, _GPT4_SECTION, in_scope=True),
    Entry("gpt-4.1-2025-04-14", PRIMARY_SHUTDOWN, PRIMARY_REPLACEMENT, _GPT4_SECTION, in_scope=True),
    Entry("gpt-4.1-mini-2025-04-14", PRIMARY_SHUTDOWN, PRIMARY_REPLACEMENT, _GPT4_SECTION, in_scope=True),
    Entry("gpt-4o", PRIMARY_SHUTDOWN, PRIMARY_REPLACEMENT, _GPT4_SECTION, "inferred", _ALIAS_NOTE, True),
    Entry("gpt-4o-mini", PRIMARY_SHUTDOWN, PRIMARY_REPLACEMENT, _GPT4_SECTION, "inferred", _ALIAS_NOTE, True),
    Entry("gpt-4.1", PRIMARY_SHUTDOWN, PRIMARY_REPLACEMENT, _GPT4_SECTION, "inferred", _ALIAS_NOTE, True),
    Entry("gpt-4.1-mini", PRIMARY_SHUTDOWN, PRIMARY_REPLACEMENT, _GPT4_SECTION, "inferred", _ALIAS_NOTE, True),
    # --- Earlier shutdowns that a GPT-4 era codebase often also contains --
    Entry("gpt-4o-2024-05-13", "2026-10-23", "gpt-5.6-sol", _LEGACY_OCT,
          note="Shuts down 23 Oct 2026, before the main deadline. Different replacement."),
    Entry("gpt-4.1-nano", "2026-10-23", "gpt-5.6-luna", _LEGACY_OCT,
          note="Shuts down 23 Oct 2026, before the main deadline."),
    Entry("gpt-4.1-nano-2025-04-14", "2026-10-23", "gpt-5.6-luna", _LEGACY_OCT,
          note="Shuts down 23 Oct 2026, before the main deadline."),
    Entry("gpt-4-turbo", "2026-10-23", "gpt-5.6-sol", _LEGACY_OCT),
    Entry("gpt-4-turbo-2024-04-09", "2026-10-23", "gpt-5.6-sol", _LEGACY_OCT),
    Entry("gpt-4", "2026-10-23", "gpt-5.6-sol", _LEGACY_OCT, note="Alias of gpt-4-0613 per the page."),
    Entry("gpt-4-0613", "2026-10-23", "gpt-5.6-sol", _LEGACY_OCT),
    Entry("gpt-3.5-turbo", "2026-10-23", "gpt-5.6-terra", _LEGACY_OCT, note="Alias of gpt-3.5-turbo-0125 per the page."),
    Entry("gpt-3.5-turbo-0125", "2026-10-23", "gpt-5.6-terra", _LEGACY_OCT),
    # --- gpt-4o-* audio / realtime / transcription: NOT gpt-6-luna --------
    Entry("gpt-4o-transcribe", "2027-02-26", "gpt-live-transcribe or gpt-transcribe",
          "2026-08-26: Transcription models",
          note="Not a chat model. Do not map to gpt-6-luna (Luna does not support transcription)."),
    Entry("gpt-4o-mini-transcribe", "2027-02-26", "gpt-live-transcribe or gpt-transcribe",
          "2026-08-26: Transcription models", note="Not a chat model. Do not map to gpt-6-luna."),
    Entry("gpt-4o-transcribe-diarize", "2027-02-26", "gpt-live-transcribe or gpt-transcribe",
          "2026-08-26: Transcription models", note="Not a chat model. Do not map to gpt-6-luna."),
    Entry("gpt-4o-mini-tts-2025-03-20", "2027-01-06", "gpt-realtime-2.1-mini",
          "2026-10-01: Text-to-speech models", note="Speech model. Do not map to gpt-6-luna."),
    Entry("gpt-4o-mini-tts-2025-12-15", "2027-01-06", "gpt-realtime-2.1-mini",
          "2026-10-01: Text-to-speech models", note="Speech model. Do not map to gpt-6-luna."),
    Entry("gpt-4o-audio", "2027-01-20", "gpt-audio-1.5", "2026-07-20: Legacy audio, realtime, and transcription models",
          note="Audio model family. Do not map to gpt-6-luna."),
    Entry("gpt-4o-realtime", "2027-01-20", "gpt-realtime-2.1", "2026-07-20: Legacy audio, realtime, and transcription models",
          note="Realtime model family. Do not map to gpt-6-luna."),
    Entry("gpt-4o-mini-realtime", "2027-01-20", "gpt-realtime-2.1-mini", "2026-07-20: Legacy audio, realtime, and transcription models",
          note="Realtime model family. Do not map to gpt-6-luna."),
    Entry("gpt-4o-mini-audio", "2027-01-20", "gpt-audio-1.5", "2026-07-20: Legacy audio, realtime, and transcription models",
          note="Audio model family. Do not map to gpt-6-luna."),
    Entry("chatgpt-4o-latest", "2026-02-17", "gpt-5.1-chat-latest", "2025-11-18: chatgpt-4o-latest snapshot",
          note="Already shut down; calls should be failing today."),
    Entry("gpt-4o-search-preview-2025-03-11", "2026-07-23", "gpt-5.6-terra", "2026-04-22: Legacy GPT model snapshots (July 2026 shutdown)",
          note="Already shut down."),
    Entry("gpt-4o-mini-search-preview-2025-03-11", "2026-07-23", "gpt-5.6-terra", "2026-04-22: Legacy GPT model snapshots (July 2026 shutdown)",
          note="Already shut down."),
]

BY_ID: dict[str, Entry] = {e.model: e for e in ENTRIES}

# Prefix families (longest first) for ids not listed exactly, e.g. dated
# realtime/audio snapshots. Used only to stop them being mapped to Luna.
FAMILY_PREFIXES = sorted(
    [e.model for e in ENTRIES if "Do not map" in e.note], key=len, reverse=True
)

# Facts about the replacement model taken from its model page.
LUNA_FACTS = {
    "fine_tuning": False,           # Fine-tuning endpoint: Not supported
    "structured_outputs": True,
    "function_calling": True,
    "chat_completions": True,
    "responses": True,
    "assistants": False,
    "completions_legacy": False,
    "chat_tools_requires_reasoning_effort_none": True,
    "context_window": 1_050_000,
    "max_output_tokens": 128_000,
}

FINE_TUNE_FACTS = [
    "Fine-tuned versions of the GPT-4 series models follow the same shutdown schedule as their base models (shutdown 14 Jan 2027).",
    "gpt-6-luna does not support fine-tuning (model page: Fine-tuning - Not supported).",
    "From 6 Jan 2027, active existing customers can no longer create new fine-tuning jobs.",
]


def lookup(model_id: str) -> Entry | None:
    """Exact lookup; for fine-tuned ids use base_of_fine_tune first."""
    if model_id in BY_ID:
        return BY_ID[model_id]
    for prefix in FAMILY_PREFIXES:
        if model_id.startswith(prefix + "-"):
            e = BY_ID[prefix]
            return Entry(model_id, e.shutdown, e.replacement, e.section, "inferred",
                         f"Matched by family prefix '{prefix}'. " + e.note, e.in_scope)
    return None


def base_of_fine_tune(model_id: str) -> str | None:
    """'ft:gpt-4o-mini-2024-07-18:org:name:id' -> 'gpt-4o-mini-2024-07-18'."""
    if not model_id.startswith("ft:"):
        return None
    parts = model_id.split(":")
    return parts[1] if len(parts) > 1 and parts[1] else None
