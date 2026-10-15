# Model scan report

- Repository: `/workspace/migration-kit/examples/sample-app`
- Files scanned: 8
- Findings: 17 in 8 files
- Deprecation data: https://developers.openai.com/api/docs/deprecations (checked 2026-10-15)

| Risk | Count |
|---|---|
| high | 7 |
| medium | 8 |
| low | 1 |
| info | 1 |

## Fine-tuned model

| File | Line | Current model | Suggested | Shutdown | Risk | Kind | Notes |
|---|---|---|---|---|---|---|---|
| `app/agent.py` | 36 | `ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1` | manual decision | 2027-01-14 | **high** | sdk_call | Fine-tune of gpt-4o-mini-2024-07-18; per OpenAI it shuts down with its base model on 2027-01-14.<br>No automatic replacement: gpt-6-luna does not support fine-tuning. Options are prompting/few-shot on gpt-6-luna validated with `eval`, or re-training on a fine-tunable model (none confirmed by the kit). New fine-tuning jobs stop on 6 Jan 2027. |
| `config/models.yaml` | 6 | `ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1` | manual decision | 2027-01-14 | **high** | config | Fine-tune of gpt-4o-mini-2024-07-18; per OpenAI it shuts down with its base model on 2027-01-14.<br>No automatic replacement: gpt-6-luna does not support fine-tuning. Options are prompting/few-shot on gpt-6-luna validated with `eval`, or re-training on a fine-tunable model (none confirmed by the kit). New fine-tuning jobs stop on 6 Jan 2027. |

## GPT-4o / 4.1 (shutdown 14 Jan 2027)

| File | Line | Current model | Suggested | Shutdown | Risk | Kind | Notes |
|---|---|---|---|---|---|---|---|
| `.env.example` | 2 | `gpt-4o-mini` | `gpt-6-luna` (inferred) | 2027-01-14 | **medium** | env | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list (gpt-4o -> gpt-4o-2024-08-06, gpt-4o-mini -> gpt-4o-mini-2024-07-18, gpt-4.1 -> gpt-4.1-2025-04-14, gpt-4.1-mini -> gpt-4.1-mini-2025-04-14). OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected. |
| `.env.example` | 3 | `gpt-4.1-mini` | `gpt-6-luna` (inferred) | 2027-01-14 | **medium** | env | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list (gpt-4o -> gpt-4o-2024-08-06, gpt-4o-mini -> gpt-4o-mini-2024-07-18, gpt-4.1 -> gpt-4.1-2025-04-14, gpt-4.1-mini -> gpt-4.1-mini-2025-04-14). OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected. |
| `README.md` | 4 | `gpt-4o` | `gpt-6-luna` (inferred) | 2027-01-14 | **low** | doc | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list (gpt-4o -> gpt-4o-2024-08-06, gpt-4o-mini -> gpt-4o-mini-2024-07-18, gpt-4.1 -> gpt-4.1-2025-04-14, gpt-4.1-mini -> gpt-4.1-mini-2025-04-14). OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected.<br>Appears in documentation/comment only. |
| `app/agent.py` | 8 | `gpt-4o-mini` | `gpt-6-luna` (inferred) | 2027-01-14 | **high** | sdk_call | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list (gpt-4o -> gpt-4o-2024-08-06, gpt-4o-mini -> gpt-4o-mini-2024-07-18, gpt-4.1 -> gpt-4.1-2025-04-14, gpt-4.1-mini -> gpt-4.1-mini-2025-04-14). OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected.<br>Chat Completions + tools in this file: gpt-6-luna returns HTTP 400 for function tools on Chat Completions unless reasoning_effort is 'none' (docs + live-tested). Set it, or move to the Responses API. |
| `app/summarise.py` | 20 | `gpt-4o-2024-08-06` | `gpt-6-luna` | 2027-01-14 | **high** | sdk_call | Uses `max_tokens`: gpt-6-luna rejects it with HTTP 400 (live-tested). Rename to `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses).<br>Structured output in this file: gpt-6-luna lists structured_outputs as supported; verify schemas with `eval`.<br>Sets temperature/top_p/logprobs: gpt-6-luna accepts these only with reasoning_effort 'none'; at other efforts temperature must be 1 and top_p/logprobs return HTTP 400 (live-tested). |
| `config/models.yaml` | 2 | `gpt-4o` | `gpt-6-luna` (inferred) | 2027-01-14 | **medium** | config | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list (gpt-4o -> gpt-4o-2024-08-06, gpt-4o-mini -> gpt-4o-mini-2024-07-18, gpt-4.1 -> gpt-4.1-2025-04-14, gpt-4.1-mini -> gpt-4.1-mini-2025-04-14). OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected. |
| `config/models.yaml` | 3 | `gpt-4o-mini-2024-07-18` | `gpt-6-luna` | 2027-01-14 | **medium** | config |  |
| `config/models.yaml` | 4 | `gpt-4.1-2025-04-14` | `gpt-6-luna` | 2027-01-14 | **medium** | config |  |
| `config/settings.json` | 2 | `gpt-4o-2024-11-20` | `gpt-6-luna` | 2027-01-14 | **high** | config | Uses `max_tokens`: gpt-6-luna rejects it with HTTP 400 (live-tested). Rename to `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses). |
| `web/src/chat.ts` | 7 | `gpt-4.1` | `gpt-6-luna` (inferred) | 2027-01-14 | **high** | sdk_call | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list (gpt-4o -> gpt-4o-2024-08-06, gpt-4o-mini -> gpt-4o-mini-2024-07-18, gpt-4.1 -> gpt-4.1-2025-04-14, gpt-4.1-mini -> gpt-4.1-mini-2025-04-14). OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected.<br>Chat Completions + tools in this file: gpt-6-luna returns HTTP 400 for function tools on Chat Completions unless reasoning_effort is 'none' (docs + live-tested). Set it, or move to the Responses API. |
| `web/src/classify.js` | 4 | `gpt-4.1-mini-2025-04-14` | `gpt-6-luna` | 2027-01-14 | **medium** | sdk_call |  |

## Other deprecated model

| File | Line | Current model | Suggested | Shutdown | Risk | Kind | Notes |
|---|---|---|---|---|---|---|---|
| `config/models.yaml` | 5 | `gpt-4.1-nano` | `gpt-5.6-luna` | 2026-10-23 | **high** | config | Shuts down 23 Oct 2026, before the main deadline.<br>Outside the GPT-4o/4.1 migration; OpenAI's listed replacement is gpt-5.6-luna. |
| `config/models.yaml` | 8 | `gpt-4o-transcribe` | `gpt-live-transcribe or gpt-transcribe` | 2027-02-26 | **medium** | config | Not a chat model. Do not map to gpt-6-luna (Luna does not support transcription).<br>Outside the GPT-4o/4.1 migration; OpenAI's listed replacement is gpt-live-transcribe or gpt-transcribe. |
| `web/src/chat.ts` | 24 | `gpt-4o-transcribe` | `gpt-live-transcribe or gpt-transcribe` | 2027-02-26 | **medium** | sdk_call | Not a chat model. Do not map to gpt-6-luna (Luna does not support transcription).<br>Outside the GPT-4o/4.1 migration; OpenAI's listed replacement is gpt-live-transcribe or gpt-transcribe. |

## Not in catalogue

| File | Line | Current model | Suggested | Shutdown | Risk | Kind | Notes |
|---|---|---|---|---|---|---|---|
| `config/settings.json` | 3 | `gpt-5.6-sol` | manual decision | - | **info** | config | Not in the kit's deprecation catalogue. Leave as-is unless the client wants to consolidate. |

## Models read from environment variables

These are set outside the repo (hosting dashboard, CI secrets, .env on servers). Check their deployed values too.

| File | Line | Variable |
|---|---|---|
| `app/agent.py` | 8 | `OPENAI_MODEL` |
| `web/src/classify.js` | 4 | `CLASSIFIER_MODEL` |
