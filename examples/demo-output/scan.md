# Model scan report

- Repository: `/workspace/migration-kit/examples/sample-app`
- Files scanned: 9
- Findings: 18 in 9 files
- Migration packs: anthropic v2026.10.15.2 (bundled), openai v2026.10.15.4 (bundled)
- SDKs detected: anthropic:anthropic, openai:openai

| Risk | Count |
|---|---|
| high | 8 |
| medium | 8 |
| low | 1 |
| info | 1 |

## Fine-tuned model

| File | Line | Provider | Current model | Suggested | Shutdown | Risk | Kind | Notes |
|---|---|---|---|---|---|---|---|---|
| `app/agent.py` | 36 | openai | `ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1` | manual decision | 2027-01-14 | **high** | sdk_call | Fine-tune of gpt-4o-mini-2024-07-18; it shuts down with its base model on 2027-01-14.<br>No automatic replacement: gpt-6-luna does not support fine-tuning. Options are prompting/few-shot on gpt-6-luna validated with `eval`, or re-training on a fine-tunable model. New fine-tuning jobs stop on 6 Jan 2027. |
| `config/models.yaml` | 6 | openai | `ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1` | manual decision | 2027-01-14 | **high** | config | Fine-tune of gpt-4o-mini-2024-07-18; it shuts down with its base model on 2027-01-14.<br>No automatic replacement: gpt-6-luna does not support fine-tuning. Options are prompting/few-shot on gpt-6-luna validated with `eval`, or re-training on a fine-tunable model. New fine-tuning jobs stop on 6 Jan 2027. |

## Headline migration

| File | Line | Provider | Current model | Suggested | Shutdown | Risk | Kind | Notes |
|---|---|---|---|---|---|---|---|---|
| `.env.example` | 2 | openai | `gpt-4o-mini` | `gpt-6-luna` (inferred) | 2027-01-14 | **medium** | env | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list. OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected. |
| `.env.example` | 3 | openai | `gpt-4.1-mini` | `gpt-6-luna` (inferred) | 2027-01-14 | **medium** | env | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list. OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected. |
| `README.md` | 4 | openai | `gpt-4o` | `gpt-6-luna` (inferred) | 2027-01-14 | **low** | doc | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list. OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected.<br>Appears in documentation/comment only. |
| `app/agent.py` | 8 | openai | `gpt-4o-mini` | `gpt-6-luna` (inferred) | 2027-01-14 | **high** | sdk_call | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list. OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected.<br>Chat Completions + tools: gpt-6-luna returns HTTP 400 for function tools on Chat Completions unless reasoning_effort is 'none'. Set it, or move to the Responses API. [live-tested] |
| `app/claude_fallback.py` | 9 | anthropic | `claude-sonnet-4-5-20250929` | `claude-sonnet-5-5` | 2026-11-30 | **high** | sdk_call | Deprecated 30 Sep 2026; retires 30 Nov 2026 on the Claude API.<br>Sets temperature/top_p/top_k: on Claude 4.7 and later models these return HTTP 400 at non-default values, and the anthropic Python SDK v1.0+ raises TypeError. Remove them and guide behaviour with prompting. [inferred] |
| `app/summarise.py` | 20 | openai | `gpt-4o-2024-08-06` | `gpt-6-luna` | 2027-01-14 | **high** | sdk_call | Uses `max_tokens`: gpt-6-luna rejects it with HTTP 400. Rename to `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses). [live-tested]<br>Sets temperature/top_p/logprobs: gpt-6-luna accepts these only with reasoning_effort 'none'; at other efforts temperature must be 1 and top_p/logprobs return HTTP 400. [live-tested]<br>Structured output: gpt-6-luna lists structured_outputs as supported (and it worked in our live eval); verify schemas with `eval`. |
| `config/models.yaml` | 2 | openai | `gpt-4o` | `gpt-6-luna` (inferred) | 2027-01-14 | **medium** | config | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list. OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected. |
| `config/models.yaml` | 3 | openai | `gpt-4o-mini-2024-07-18` | `gpt-6-luna` | 2027-01-14 | **medium** | config |  |
| `config/models.yaml` | 4 | openai | `gpt-4.1-2025-04-14` | `gpt-6-luna` | 2027-01-14 | **medium** | config |  |
| `config/settings.json` | 2 | openai | `gpt-4o-2024-11-20` | `gpt-6-luna` | 2027-01-14 | **high** | config | Uses `max_tokens`: gpt-6-luna rejects it with HTTP 400. Rename to `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses). [live-tested] |
| `web/src/chat.ts` | 7 | openai | `gpt-4.1` | `gpt-6-luna` (inferred) | 2027-01-14 | **high** | sdk_call | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list. OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected.<br>Chat Completions + tools: gpt-6-luna returns HTTP 400 for function tools on Chat Completions unless reasoning_effort is 'none'. Set it, or move to the Responses API. [live-tested] |
| `web/src/classify.js` | 4 | openai | `gpt-4.1-mini-2025-04-14` | `gpt-6-luna` | 2027-01-14 | **medium** | sdk_call |  |

## Other retiring model

| File | Line | Provider | Current model | Suggested | Shutdown | Risk | Kind | Notes |
|---|---|---|---|---|---|---|---|---|
| `config/models.yaml` | 5 | openai | `gpt-4.1-nano` | `gpt-5.6-luna` | 2026-10-23 | **high** | config | Shuts down 23 Oct 2026, before the main deadline.<br>Shuts down in 8 days.<br>Outside the headline migration; the listed replacement is gpt-5.6-luna. |
| `config/models.yaml` | 8 | openai | `gpt-4o-transcribe` | `gpt-live-transcribe or gpt-transcribe` | 2027-02-26 | **medium** | config | Not a chat model. Do not map to gpt-6-luna. (Transcription model.)<br>Outside the headline migration; the listed replacement is gpt-live-transcribe or gpt-transcribe. |
| `web/src/chat.ts` | 24 | openai | `gpt-4o-transcribe` | `gpt-live-transcribe or gpt-transcribe` | 2027-02-26 | **medium** | sdk_call | Not a chat model. Do not map to gpt-6-luna. (Transcription model.)<br>Outside the headline migration; the listed replacement is gpt-live-transcribe or gpt-transcribe. |

## Not listed as retiring

| File | Line | Provider | Current model | Suggested | Shutdown | Risk | Kind | Notes |
|---|---|---|---|---|---|---|---|---|
| `config/settings.json` | 3 | openai | `gpt-5.6-sol` | manual decision | - | **info** | config | Not listed as retiring in the openai pack (v2026.10.15.4). |

## Models read from environment variables

These are set outside the repo (hosting dashboard, CI secrets, .env on servers). Check their deployed values too.

| File | Line | Variable |
|---|---|---|
| `app/agent.py` | 8 | `OPENAI_MODEL` |
| `web/src/classify.js` | 4 | `CLASSIFIER_MODEL` |

## Next steps

- **See what the fix would change, free:** `lastorders fix .` shows the real per-file count. It skips docs unless you pass `--include-docs`, and it leaves alone any ID it can't rename safely (for example where renaming would create a duplicate entry), so it can be smaller than the table above.
- **Get the patch for this repo:** a reviewable patch plus a must-review list of anything it couldn't safely change, with a before-and-after report. £179 one-off, tax included: <https://lastorders.burntandtoast.com/#pricing>
- **Or have us do it:** from £1,500. Email hello@burntandtoast.com.
