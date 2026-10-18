# Fix plan

- Repo: `fixer-repo`
- Packs: anthropic v2026.10.15.2, openai v2026.10.15.4
- Files changed: **5** | model ID replacements: 17
- Items: Fixed: **10**, Fixed (deploy with the model switch): **1**, Info: **1**, Needs a decision: **11**

Nothing has been changed on disk. Review `fix.diff`, then apply it with `git apply` or `lastorders fix --apply` (licensed).

## Fixed (10)

| File | Rule | Change | Why |
|---|---|---|---|
| `py/legacy.py:9` | luna-chat-tools-effort | set `reasoning_effort` = "none" | Chat Completions + tools: gpt-6-luna returns HTTP 400 for function tools on Chat Completions unless reasoning_effort is 'none'. Set it, or move to the Responses API. Alternative: move the call to the Responses API (tools work there at the default effort). |
| `py/variants.py:12` | luna-sampling | set `reasoning.effort` = "none" | Sets temperature/top_p/logprobs: gpt-6-luna accepts these only with reasoning_effort 'none'; at other efforts temperature must be 1 and top_p/logprobs return HTTP 400. Alternative: remove temperature/top_p/logprobs/top_logprobs and keep the default reasoning effort. |
| `py/variants.py:16` | luna-sampling | set `reasoning.effort` = "none" | Sets temperature/top_p/logprobs: gpt-6-luna accepts these only with reasoning_effort 'none'; at other efforts temperature must be 1 and top_p/logprobs return HTTP 400. Alternative: remove temperature/top_p/logprobs/top_logprobs and keep the default reasoning effort. |
| `py/variants.py:25` | luna-max-tokens | rename `max_tokens` -> `max_completion_tokens` | Uses `max_tokens`: gpt-6-luna rejects it with HTTP 400. Rename to `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses). |
| `py/variants.py:34` | luna-chat-tools-effort | set `reasoning_effort` = "none" | Chat Completions + tools: gpt-6-luna returns HTTP 400 for function tools on Chat Completions unless reasoning_effort is 'none'. Set it, or move to the Responses API. Alternative: move the call to the Responses API (tools work there at the default effort). |
| `py/variants.py:34` | luna-max-tokens | rename `max_tokens` -> `max_completion_tokens` | Uses `max_tokens`: gpt-6-luna rejects it with HTTP 400. Rename to `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses). |
| `web/chat.js:11` | luna-max-tokens | rename `max_tokens` -> `max_completion_tokens` | Uses `max_tokens`: gpt-6-luna rejects it with HTTP 400. Rename to `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses). |
| `web/chat.js:11` | luna-sampling | set `reasoning_effort` = "none" | Sets temperature/top_p/logprobs: gpt-6-luna accepts these only with reasoning_effort 'none'; at other efforts temperature must be 1 and top_p/logprobs return HTTP 400. Alternative: remove temperature/top_p/logprobs/top_logprobs and keep the default reasoning effort. |
| `web/chat.js:16` | luna-max-tokens | rename `max_tokens` -> `max_completion_tokens` | Uses `max_tokens`: gpt-6-luna rejects it with HTTP 400. Rename to `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses). The model comes from $CHAT_MODEL; this change is safe on the old model too. |
| `web/resp.ts:14` | luna-sampling | set `reasoning.effort` = "none" | Sets temperature/top_p/logprobs: gpt-6-luna accepts these only with reasoning_effort 'none'; at other efforts temperature must be 1 and top_p/logprobs return HTTP 400. Alternative: remove temperature/top_p/logprobs/top_logprobs and keep the default reasoning effort. |

## Fixed (deploy with the model switch) (1)

| File | Rule | Change | Why |
|---|---|---|---|
| `py/variants.py:51` | luna-chat-tools-effort | set `reasoning_effort` = "none" | Chat Completions + tools: gpt-6-luna returns HTTP 400 for function tools on Chat Completions unless reasoning_effort is 'none'. Set it, or move to the Responses API. Alternative: move the call to the Responses API (tools work there at the default effort). The model comes from $CHAT_MODEL (default now gpt-6-luna). Deploy this change together with switching the model to gpt-6-luna: Live-tested 15 Oct 2026: gpt-4o-2024-08-06, gpt-4o-mini-2024-07-18 and gpt-4.1-2025-04-14 return HTTP 400 'Unrecognized request argument supplied: reasoning_effort' on Chat Completions; gpt-4.1-mini-2025-04-14 returns 400 for reasoning.effort on Responses (probes/params3-result.json). |

## Needs a decision (11)

| File | Rule | Change | Why |
|---|---|---|---|
| `py/chains.py:3` | luna-max-tokens | no automatic rename defined for this call type (langchain_openai) | Uses `max_tokens`: gpt-6-luna rejects it with HTTP 400. Rename to `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses). LangChain and other wrappers are not renamed automatically: check how your wrapper version maps max_tokens. |
| `py/chains.py:3` | luna-sampling | no automatic fix defined for this call type (langchain_openai) | Sets temperature/top_p/logprobs: gpt-6-luna accepts these only with reasoning_effort 'none'; at other efforts temperature must be 1 and top_p/logprobs return HTTP 400. Alternative: remove temperature/top_p/logprobs/top_logprobs and keep the default reasoning effort. |
| `py/legacy.py:9` | luna-legacy-functions | Rewrite `functions`/`function_call` as `tools`/`tool_choice` and update the response handling (message.tool_calls). | Uses legacy `functions`/`function_call` parameters. Not tested on gpt-6-luna; migrate to `tools`. |
| `py/legacy.py:14` | luna-assistants | kept on `gpt-4o` in the patch (not swapped to gpt-6-luna). The Assistants API has shut down; port threads/runs to the Responses API (conversation state, tools, file search). | Assistants API: gpt-6-luna does not support it (and the Assistants API shut down 26 Aug 2026). |
| `py/legacy.py:18` | luna-legacy-completions | kept on `gpt-4o-mini` in the patch (not swapped to gpt-6-luna). Move prompt-completion calls to the Responses API (input=...). | Legacy /v1/completions: gpt-6-luna does not support it. |
| `py/legacy.py:18` | luna-max-tokens | fix this when you move the call | Uses `max_tokens`: gpt-6-luna rejects it with HTTP 400. Rename to `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses). |
| `py/legacy.py:22` | luna-fine-tuning-jobs | kept on `gpt-4o-mini-2024-07-18` in the patch (not swapped to gpt-6-luna). gpt-6-luna can't be fine-tuned; decide whether to keep a fine-tunable model or replace the fine-tune with prompting validated by eval. | Creates fine-tuning jobs: gpt-6-luna can't be fine-tuned, and new fine-tuning jobs stop on 6 Jan 2027. |
| `py/variants.py:25` | luna-sampling | the call also passes **kwargs / a spread object; adding the argument could duplicate it | Sets temperature/top_p/logprobs: gpt-6-luna accepts these only with reasoning_effort 'none'; at other efforts temperature must be 1 and top_p/logprobs return HTTP 400. Alternative: remove temperature/top_p/logprobs/top_logprobs and keep the default reasoning effort. |
| `py/variants.py:30` | model-unknown | re-run with --assume-model gpt-6-luna to apply them | The model for this call isn't visible in the code, so no fix was applied. If it runs on gpt-6-luna, these rules apply: luna-chat-tools-effort. model expression: `model_name` |
| `py/variants.py:47` | luna-chat-tools-effort | `reasoning_effort` is already set to `"low"`; decide which value you need | Chat Completions + tools: gpt-6-luna returns HTTP 400 for function tools on Chat Completions unless reasoning_effort is 'none'. Set it, or move to the Responses API. Alternative: move the call to the Responses API (tools work there at the default effort). |
| `web/resp.ts:6` | luna-sampling | the call also passes **kwargs / a spread object; adding the argument could duplicate it | Sets temperature/top_p/logprobs: gpt-6-luna accepts these only with reasoning_effort 'none'; at other efforts temperature must be 1 and top_p/logprobs return HTTP 400. Alternative: remove temperature/top_p/logprobs/top_logprobs and keep the default reasoning effort. |

## Info (1)

| File | Rule | Change | Why |
|---|---|---|---|
| `py/chains.py:3` | langchain-max-tokens |  | LangChain: check how your langchain-openai version maps `max_tokens` before relying on the rename; not verified by us. |
