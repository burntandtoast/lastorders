# Model scan report

- Repository: `/workspace/migration-kit/examples/sample-app`
- Files scanned: 8
- Findings: 17 in 8 files
- Deprecation data: https://developers.openai.com/api/docs/deprecations (checked 2026-10-15)

| Risk | Count |
|---|---|
| high | 5 |
| medium | 10 |
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
| `.env.example` | 2 | `gpt-4o-mini` | `gpt-6-luna` (inferred) | 2027-01-14 | **medium** | env | Undated alias: OpenAI lists only the dated snapshots, so treating the alias as affected is inferred. Confirm with GET /v1/models (shutdown_date). |
| `.env.example` | 3 | `gpt-4.1-mini` | `gpt-6-luna` (inferred) | 2027-01-14 | **medium** | env | Undated alias: OpenAI lists only the dated snapshots, so treating the alias as affected is inferred. Confirm with GET /v1/models (shutdown_date). |
| `README.md` | 4 | `gpt-4o` | `gpt-6-luna` (inferred) | 2027-01-14 | **low** | doc | Undated alias: OpenAI lists only the dated snapshots, so treating the alias as affected is inferred. Confirm with GET /v1/models (shutdown_date).<br>Appears in documentation/comment only. |
| `app/agent.py` | 8 | `gpt-4o-mini` | `gpt-6-luna` (inferred) | 2027-01-14 | **high** | sdk_call | Undated alias: OpenAI lists only the dated snapshots, so treating the alias as affected is inferred. Confirm with GET /v1/models (shutdown_date).<br>Chat Completions + tools in this file: gpt-6-luna supports function calling on Chat Completions only with reasoning_effort set to 'none' (or move to the Responses API). |
| `app/summarise.py` | 20 | `gpt-4o-2024-08-06` | `gpt-6-luna` | 2027-01-14 | **medium** | sdk_call | Structured output in this file: gpt-6-luna lists structured_outputs as supported; verify schemas with `eval`.<br>Sets sampling/length params (temperature, max_tokens, etc.). gpt-6-luna is a reasoning model; the kit could not confirm which of these it accepts - test with `eval`. |
| `config/models.yaml` | 2 | `gpt-4o` | `gpt-6-luna` (inferred) | 2027-01-14 | **medium** | config | Undated alias: OpenAI lists only the dated snapshots, so treating the alias as affected is inferred. Confirm with GET /v1/models (shutdown_date). |
| `config/models.yaml` | 3 | `gpt-4o-mini-2024-07-18` | `gpt-6-luna` | 2027-01-14 | **medium** | config |  |
| `config/models.yaml` | 4 | `gpt-4.1-2025-04-14` | `gpt-6-luna` | 2027-01-14 | **medium** | config |  |
| `config/settings.json` | 2 | `gpt-4o-2024-11-20` | `gpt-6-luna` | 2027-01-14 | **medium** | config |  |
| `web/src/chat.ts` | 7 | `gpt-4.1` | `gpt-6-luna` (inferred) | 2027-01-14 | **high** | sdk_call | Undated alias: OpenAI lists only the dated snapshots, so treating the alias as affected is inferred. Confirm with GET /v1/models (shutdown_date).<br>Chat Completions + tools in this file: gpt-6-luna supports function calling on Chat Completions only with reasoning_effort set to 'none' (or move to the Responses API). |
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
