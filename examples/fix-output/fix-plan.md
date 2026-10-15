# Automatic fix plan

- Repo: `sample-app`
- Packs: anthropic v2026.10.15.2, openai v2026.10.15.4
- Files changed: **8** | model ID replacements: 11
- Items: Fixed: **3**, Fixed (deploy with the model switch): **1**, Info: **1**, Needs a decision: **4**

Nothing has been changed on disk. Review `fix.diff`, then apply it with `git apply` or `modelmigrate fix --apply` (licensed).

## Fixed (3)

| File | Rule | Change | Why |
|---|---|---|---|
| `app/summarise.py:19` | luna-max-tokens | rename `max_tokens` -> `max_completion_tokens` | Uses `max_tokens`: gpt-6-luna rejects it with HTTP 400. Rename to `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses). |
| `app/summarise.py:19` | luna-sampling | set `reasoning_effort` = "none" | Sets temperature/top_p/logprobs: gpt-6-luna accepts these only with reasoning_effort 'none'; at other efforts temperature must be 1 and top_p/logprobs return HTTP 400. Alternative: remove temperature/top_p/logprobs/top_logprobs and keep the default reasoning effort. |
| `web/src/chat.ts:6` | luna-chat-tools-effort | set `reasoning_effort` = "none" | Chat Completions + tools: gpt-6-luna returns HTTP 400 for function tools on Chat Completions unless reasoning_effort is 'none'. Set it, or move to the Responses API. Alternative: move the call to the Responses API (tools work there at the default effort). |

## Fixed (deploy with the model switch) (1)

| File | Rule | Change | Why |
|---|---|---|---|
| `app/agent.py:29` | luna-chat-tools-effort | set `reasoning_effort` = "none" | Chat Completions + tools: gpt-6-luna returns HTTP 400 for function tools on Chat Completions unless reasoning_effort is 'none'. Set it, or move to the Responses API. Alternative: move the call to the Responses API (tools work there at the default effort). The model comes from $OPENAI_MODEL (default now gpt-6-luna). Deploy this change together with switching the model to gpt-6-luna: Live-tested 15 Oct 2026: gpt-4o-2024-08-06, gpt-4o-mini-2024-07-18 and gpt-4.1-2025-04-14 return HTTP 400 'Unrecognized request argument supplied: reasoning_effort' on Chat Completions; gpt-4.1-mini-2025-04-14 returns 400 for reasoning.effort on Responses (probes/params3-result.json). |

## Needs a decision (4)

| File | Rule | Change | Why |
|---|---|---|---|
| `app/agent.py:35` | fine-tune |  | Fine-tuned model `ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1` (base `gpt-4o-mini-2024-07-18`, shuts down 2027-01-14). Not changed automatically. No automatic replacement: gpt-6-luna does not support fine-tuning. Options are prompting/few-shot on gpt-6-luna validated with `eval`, or re-training on a fine-tunable model. New fine-tuning jobs stop on 6 Jan 2027. |
| `app/claude_fallback.py:8` | claude-sampling-deprecated | suggested: remove `temperature` (rule confidence 'inferred'; pass --include-inferred to apply) | Sets temperature/top_p/top_k: on Claude 4.7 and later models these return HTTP 400 at non-default values, and the anthropic Python SDK v1.0+ raises TypeError. Remove them and guide behaviour with prompting. |
| `config/models.yaml:6` | fine-tune |  | Fine-tuned model `ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1` referenced here (config). Not changed automatically. No automatic replacement: gpt-6-luna does not support fine-tuning. Options are prompting/few-shot on gpt-6-luna validated with `eval`, or re-training on a fine-tunable model. New fine-tuning jobs stop on 6 Jan 2027. |
| `config/settings.json:2` | luna-max-tokens | found by the file-level scan, but no SDK call in this file could be parsed: check where this value is used | Uses `max_tokens`: gpt-6-luna rejects it with HTTP 400. Rename to `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses). |

## Info (1)

| File | Rule | Change | Why |
|---|---|---|---|
| `app/summarise.py:19` | luna-structured |  | Structured output: gpt-6-luna lists structured_outputs as supported (and it worked in our live eval); verify schemas with `eval`. |
