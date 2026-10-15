# Model migration report: Acme Widgets Ltd (sample)

Prepared by Burnt & Toast Studios on 15 October 2026.

> **Demo: simulated eval outputs on a fictional sample repo**

## At a glance

- **Deadline:** Anthropic retires Claude Sonnet 4.5 on the Claude API: **30 November 2026** (46 days from this report).
- **Deadline:** OpenAI removes GPT-4o, GPT-4o mini, GPT-4.1 and GPT-4.1 mini from the API: **14 January 2027** (91 days from this report).
- **Model references found:** 18 across 9 files (9 files scanned).
- **High risk:** 8 | **Medium:** 8 | **Low:** 1 | **Info:** 1
- **Providers:** anthropic (1), openai (17)
- **Fine-tuned models:** 1 (need a separate decision)
- **Models set by environment variable:** `CLASSIFIER_MODEL`, `OPENAI_MODEL` (check the live values on your servers)
- **Proposed patch:** 8 files, 11 model ID replacements plus the code fixes below
- **Automatic fixes:** 3 code fixes in the patch, 1 that must ship with the model switch, 4 items that need a decision; verification **PASS** (mock)
- **Regression eval (mock):** 1 drift, 1 fail, 4 pass

## Anthropic Claude API (stub): what's confirmed

Migration pack `anthropic` v2026.10.15.2 (stub). Sources: [Anthropic model deprecations](https://docs.anthropic.com/en/docs/about-claude/model-deprecations).

- claude-sonnet-4-5-20250929 is deprecated and retires on the Claude API on 30 Nov 2026; recommended replacement claude-sonnet-5-5.
- Anthropic gives at least 60 days' notice before retiring publicly released models.
- Amazon Bedrock and Google Cloud set their own retirement schedules; these dates apply to Anthropic-operated platforms only.
- temperature, top_p and top_k are deprecated on Claude 4.7 and later models (400 at non-default values).

**Not confirmed:**

- This is a stub pack: no live checks, no alias data, and replacements' parameter behaviour beyond the docs is untested.

## OpenAI API: what's confirmed

Migration pack `openai` v2026.10.15.4 (stable). Sources: [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations), [GPT-6 Luna model page](https://developers.openai.com/api/docs/models/gpt-6-luna), [GPT-4o model page](https://developers.openai.com/api/docs/models/gpt-4o).

- OpenAI announced on 14 Oct 2026 that gpt-4o-2024-08-06, gpt-4o-2024-11-20, gpt-4o-mini-2024-07-18, gpt-4.1-2025-04-14 and gpt-4.1-mini-2025-04-14 will be removed from the API on 14 Jan 2027.
- OpenAI's recommended replacement for all five is gpt-6-luna.
- Fine-tuned versions of these models follow the same shutdown schedule as their base models.
- gpt-6-luna does not support fine-tuning. From 6 Jan 2027, active existing customers can no longer create new fine-tuning jobs.
- gpt-6-luna supports Chat Completions, Responses, Batch, structured outputs and function calling; on Chat Completions, function calling works only with reasoning_effort set to 'none'.
- gpt-6-luna does not support the Assistants API or legacy /v1/completions.
- OpenAI documents a shutdown_date field on GET /v1/models (not yet filled in for this batch; see the live checks).

**Confirmed by our own live API checks (2026-10-15):**

- gpt-6-luna rejects `max_tokens` (400 unsupported_parameter, at every reasoning effort). Use `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses). `max_completion_tokens` also works on gpt-4o-2024-08-06.
- gpt-6-luna accepts temperature, top_p and logprobs only with reasoning_effort 'none'. At the default and 'low' effort, temperature is accepted only at 1, and top_p and logprobs are rejected. On the Responses API, temperature and top_p work with reasoning.effort 'none' and are rejected at the default effort.
- Chat Completions + function tools on gpt-6-luna returns 400 unless reasoning_effort is 'none' ('low' and the default both fail). Function tools on the Responses API work at the default effort.
- Undated aliases still resolve: gpt-4o -> gpt-4o-2024-08-06, gpt-4o-mini -> gpt-4o-mini-2024-07-18, gpt-4.1 -> gpt-4.1-2025-04-14, gpt-4.1-mini -> gpt-4.1-mini-2025-04-14.
- GET /v1/models shows shutdown_date null for all nine GPT-4o / 4.1 ids and for gpt-6-luna; the 14 Jan 2027 date isn't in the API yet. Earlier batches are populated (e.g. gpt-4.1-nano and gpt-4o-2024-05-13 show 2026-10-23).
- GPT-4o / GPT-4.1 models reject reasoning_effort (Chat: 'Unrecognized request argument', Responses: reasoning.effort unsupported), so adding reasoning_effort must ship in the same deploy as the model swap (live-tested 15 Oct 2026).

**Not confirmed:**

- Whether the undated aliases (gpt-4o, gpt-4o-mini, gpt-4.1, gpt-4.1-mini) are retired or re-pointed on 14 Jan 2027. Today they resolve to dated snapshots that are on the shutdown list, so we treat them as affected.
- Output quality, latency and cost on your own workload. Only a regression eval can show that.

## Findings

| Risk | File | Line | Current model | Suggested | Category | Notes |
|---|---|---|---|---|---|---|
| **high** | `app/agent.py` | 8 | `gpt-4o-mini` | `gpt-6-luna` (inferred) | Headline migration | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list. OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected.<br>Chat Completions + tools: gpt-6-luna returns HTTP 400 for function tools on Chat Completions unless reasoning_effort is 'none'. Set it, or move to the Responses API. [live-tested] |
| **high** | `app/agent.py` | 36 | `ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1` | decision needed | Fine-tuned model | Fine-tune of gpt-4o-mini-2024-07-18; it shuts down with its base model on 2027-01-14.<br>No automatic replacement: gpt-6-luna does not support fine-tuning. Options are prompting/few-shot on gpt-6-luna validated with `eval`, or re-training on a fine-tunable model. New fine-tuning jobs stop on 6 Jan 2027. |
| **high** | `app/claude_fallback.py` | 9 | `claude-sonnet-4-5-20250929` | `claude-sonnet-5-5` | Headline migration | Deprecated 30 Sep 2026; retires 30 Nov 2026 on the Claude API.<br>Sets temperature/top_p/top_k: on Claude 4.7 and later models these return HTTP 400 at non-default values, and the anthropic Python SDK v1.0+ raises TypeError. Remove them and guide behaviour with prompting. [inferred] |
| **high** | `app/summarise.py` | 20 | `gpt-4o-2024-08-06` | `gpt-6-luna` | Headline migration | Uses `max_tokens`: gpt-6-luna rejects it with HTTP 400. Rename to `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses). [live-tested]<br>Sets temperature/top_p/logprobs: gpt-6-luna accepts these only with reasoning_effort 'none'; at other efforts temperature must be 1 and top_p/logprobs return HTTP 400. [live-tested]<br>Structured output: gpt-6-luna lists structured_outputs as supported (and it worked in our live eval); verify schemas with `eval`. |
| **high** | `config/models.yaml` | 5 | `gpt-4.1-nano` | `gpt-5.6-luna` | Other retiring model | Shuts down 23 Oct 2026, before the main deadline.<br>Shuts down in 8 days.<br>Outside the headline migration; the listed replacement is gpt-5.6-luna. |
| **high** | `config/models.yaml` | 6 | `ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1` | decision needed | Fine-tuned model | Fine-tune of gpt-4o-mini-2024-07-18; it shuts down with its base model on 2027-01-14.<br>No automatic replacement: gpt-6-luna does not support fine-tuning. Options are prompting/few-shot on gpt-6-luna validated with `eval`, or re-training on a fine-tunable model. New fine-tuning jobs stop on 6 Jan 2027. |
| **high** | `config/settings.json` | 2 | `gpt-4o-2024-11-20` | `gpt-6-luna` | Headline migration | Uses `max_tokens`: gpt-6-luna rejects it with HTTP 400. Rename to `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses). [live-tested] |
| **high** | `web/src/chat.ts` | 7 | `gpt-4.1` | `gpt-6-luna` (inferred) | Headline migration | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list. OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected.<br>Chat Completions + tools: gpt-6-luna returns HTTP 400 for function tools on Chat Completions unless reasoning_effort is 'none'. Set it, or move to the Responses API. [live-tested] |
| **medium** | `.env.example` | 2 | `gpt-4o-mini` | `gpt-6-luna` (inferred) | Headline migration | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list. OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected. |
| **medium** | `.env.example` | 3 | `gpt-4.1-mini` | `gpt-6-luna` (inferred) | Headline migration | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list. OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected. |
| **medium** | `config/models.yaml` | 2 | `gpt-4o` | `gpt-6-luna` (inferred) | Headline migration | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list. OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected. |
| **medium** | `config/models.yaml` | 3 | `gpt-4o-mini-2024-07-18` | `gpt-6-luna` | Headline migration |  |
| **medium** | `config/models.yaml` | 4 | `gpt-4.1-2025-04-14` | `gpt-6-luna` | Headline migration |  |
| **medium** | `config/models.yaml` | 8 | `gpt-4o-transcribe` | `gpt-live-transcribe or gpt-transcribe` | Other retiring model | Not a chat model. Do not map to gpt-6-luna. (Transcription model.)<br>Outside the headline migration; the listed replacement is gpt-live-transcribe or gpt-transcribe. |
| **medium** | `web/src/chat.ts` | 24 | `gpt-4o-transcribe` | `gpt-live-transcribe or gpt-transcribe` | Other retiring model | Not a chat model. Do not map to gpt-6-luna. (Transcription model.)<br>Outside the headline migration; the listed replacement is gpt-live-transcribe or gpt-transcribe. |
| **medium** | `web/src/classify.js` | 4 | `gpt-4.1-mini-2025-04-14` | `gpt-6-luna` | Headline migration |  |
| **low** | `README.md` | 4 | `gpt-4o` | `gpt-6-luna` (inferred) | Headline migration | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list. OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected.<br>Appears in documentation/comment only. |
| **info** | `config/settings.json` | 3 | `gpt-5.6-sol` | decision needed | Not listed as retiring | Not listed as retiring in the openai pack (v2026.10.15.4). |

## Fine-tuned models

These can't be swapped automatically. For each one, choose to:

1. Replace it with gpt-6-luna plus a stronger prompt and examples, proven with the regression eval, or
2. re-train on another fine-tunable model before new fine-tuning jobs close on 6 January 2027.

- `ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1` in `app/agent.py` line 36
- `ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1` in `config/models.yaml` line 6

## Automatic fixes

Generated from the migration-pack rules for each API call (not from text search).

| Status | File | Rule | Change | Why |
|---|---|---|---|---|
| **Fixed; ship with the model switch** | `app/agent.py:29` | luna-chat-tools-effort | set `reasoning_effort` = "none" | Chat Completions + tools: gpt-6-luna returns HTTP 400 for function tools on Chat Completions unless reasoning_effort is 'none'. Set it, or move to the Responses API. Alternative: move the call to the Responses API (tools work there at the default effort). The model comes from $OPENAI_MODEL (default now gpt-6-luna). Deploy this change together with switching the model to gpt-6-luna: Live-tested 15 Oct 2026: gpt-4o-2024-08-06, gpt-4o-mini-2024-07-18 and gpt-4.1-2025-04-14 return HTTP 400 'Unrecognized request argument supplied: reasoning_effort' on Chat Completions; gpt-4.1-mini-2025-04-14 returns 400 for reasoning.effort on Responses (probes/params3-result.json). |
| **Needs a decision** | `app/agent.py:35` | fine-tune |  | Fine-tuned model `ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1` (base `gpt-4o-mini-2024-07-18`, shuts down 2027-01-14). Not changed automatically. No automatic replacement: gpt-6-luna does not support fine-tuning. Options are prompting/few-shot on gpt-6-luna validated with `eval`, or re-training on a fine-tunable model. New fine-tuning jobs stop on 6 Jan 2027. |
| **Needs a decision** | `app/claude_fallback.py:8` | claude-sampling-deprecated | suggested: remove `temperature` (rule confidence 'inferred'; pass --include-inferred to apply) | Sets temperature/top_p/top_k: on Claude 4.7 and later models these return HTTP 400 at non-default values, and the anthropic Python SDK v1.0+ raises TypeError. Remove them and guide behaviour with prompting. |
| **Fixed in the patch** | `app/summarise.py:19` | luna-max-tokens | rename `max_tokens` -> `max_completion_tokens` | Uses `max_tokens`: gpt-6-luna rejects it with HTTP 400. Rename to `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses). |
| **Fixed in the patch** | `app/summarise.py:19` | luna-sampling | set `reasoning_effort` = "none" | Sets temperature/top_p/logprobs: gpt-6-luna accepts these only with reasoning_effort 'none'; at other efforts temperature must be 1 and top_p/logprobs return HTTP 400. Alternative: remove temperature/top_p/logprobs/top_logprobs and keep the default reasoning effort. |
| **Needs a decision** | `config/models.yaml:6` | fine-tune |  | Fine-tuned model `ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1` referenced here (config). Not changed automatically. No automatic replacement: gpt-6-luna does not support fine-tuning. Options are prompting/few-shot on gpt-6-luna validated with `eval`, or re-training on a fine-tunable model. New fine-tuning jobs stop on 6 Jan 2027. |
| **Needs a decision** | `config/settings.json:2` | luna-max-tokens | found by the file-level scan, but no SDK call in this file could be parsed: check where this value is used | Uses `max_tokens`: gpt-6-luna rejects it with HTTP 400. Rename to `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses). |
| **Fixed in the patch** | `web/src/chat.ts:6` | luna-chat-tools-effort | set `reasoning_effort` = "none" | Chat Completions + tools: gpt-6-luna returns HTTP 400 for function tools on Chat Completions unless reasoning_effort is 'none'. Set it, or move to the Responses API. Alternative: move the call to the Responses API (tools work there at the default effort). |

**Verification:**

- Patch applies cleanly: yes. Changed files parse: yes. Re-running the fixer changes nothing: yes.
- chat: 3 fixed call(s) replayed old vs new (mock); new model rejected 0.
- responses: 1 fixed call(s) replayed old vs new (mock); new model rejected 0.

## Proposed code change

Nothing has been changed in your repository. This is the patch for review:

```diff
--- a/.env.example
+++ b/.env.example
@@ -1,3 +1,3 @@
 OPENAI_API_KEY=sk-replace-me
-OPENAI_MODEL=gpt-4o-mini
-CLASSIFIER_MODEL=gpt-4.1-mini
+OPENAI_MODEL=gpt-6-luna
+CLASSIFIER_MODEL=gpt-6-luna
--- a/app/agent.py
+++ b/app/agent.py
@@ -5,7 +5,7 @@
 from openai import OpenAI
 
 client = OpenAI()
-MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
+MODEL = os.getenv("OPENAI_MODEL", "gpt-6-luna")
 
 TOOLS = [{
     "type": "function",
@@ -26,7 +26,7 @@
 
 
 def handle(message: str):
-    resp = client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": message}], tools=TOOLS)
+    resp = client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": message}], tools=TOOLS, reasoning_effort="none")
     return resp.choices[0].message.tool_calls
 
 
--- a/app/claude_fallback.py
+++ b/app/claude_fallback.py
@@ -6,7 +6,7 @@
 
 def summarise_with_claude(ticket: str) -> str:
     msg = client.messages.create(
-        model="claude-sonnet-4-5-20250929",
+        model="claude-sonnet-5-5",
         max_tokens=400,
         temperature=0.3,
         messages=[{"role": "user", "content": ticket}],
--- a/app/summarise.py
+++ b/app/summarise.py
@@ -17,10 +17,11 @@
 
 def summarise(ticket: str) -> str:
     resp = client.chat.completions.create(
-        model="gpt-4o-2024-08-06",
+        model="gpt-6-luna",
         temperature=0.2,
-        max_tokens=400,
+        max_completion_tokens=400,
         messages=[{"role": "user", "content": ticket}],
         response_format={"type": "json_schema", "json_schema": {"name": "ticket", "schema": TICKET_SCHEMA, "strict": True}},
+        reasoning_effort="none",
     )
     return resp.choices[0].message.content
--- a/config/models.yaml
+++ b/config/models.yaml
@@ -1,7 +1,7 @@
 llm:
-  default: gpt-4o
-  fallback: gpt-4o-mini-2024-07-18
-  long_context: gpt-4.1-2025-04-14
+  default: gpt-6-luna
+  fallback: gpt-6-luna
+  long_context: gpt-6-luna
   cheap_tagging: gpt-4.1-nano
   intent_classifier: ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1
 speech:
--- a/config/settings.json
+++ b/config/settings.json
@@ -1,4 +1,4 @@
 {
-  "assistant": { "model": "gpt-4o-2024-11-20", "max_tokens": 800 },
+  "assistant": { "model": "gpt-6-luna", "max_tokens": 800 },
   "reports": { "model": "gpt-5.6-sol" }
 }
--- a/web/src/chat.ts
+++ b/web/src/chat.ts
@@ -4,7 +4,7 @@
 
 export async function reply(history: OpenAI.Chat.ChatCompletionMessageParam[]) {
   const completion = await openai.chat.completions.create({
-    model: "gpt-4.1",
+    model: "gpt-6-luna",
     messages: history,
     tools: [
       {
@@ -15,6 +15,7 @@
         },
       },
     ],
+    reasoning_effort: "none",
   });
   return completion.choices[0].message;
 }
--- a/web/src/classify.js
+++ b/web/src/classify.js
@@ -1,7 +1,7 @@
 import OpenAI from "openai";
 
 const openai = new OpenAI();
-const MODEL = process.env.CLASSIFIER_MODEL ?? 'gpt-4.1-mini-2025-04-14';
+const MODEL = process.env.CLASSIFIER_MODEL ?? 'gpt-6-luna';
 
 export async function classify(text) {
   const response = await openai.responses.create({
```

## Regression eval: `gpt-4o-2024-08-06` vs `gpt-6-luna`

> **Demo run.** These results use simulated outputs to show the format. A real engagement runs the same suite against both models with the client's API key.

| Case | Type | Status | What changed |
|---|---|---|---|
| `ticket-summary-refund` | structured | **PASS** | no material difference |
| `ticket-summary-question` | structured | **DRIFT** | fields differ: priority (changed), tags (changed) |
| `book-table-simple` | tool_call | **PASS** | no material difference |
| `book-table-relative-date` | tool_call | **FAIL** | book_table args: date "2026-10-23" -> "23/10/2026", time "19:30" -> "7:30pm"; book_table: date: '23/10/2026' does not match '^\\d{4}-\\d{2}-\\d{2}$' |
| `order-lookup` | tool_call | **PASS** | no material difference |
| `apology-tone` | text | **PASS** | text similarity 0.556 |

## Next steps

1. Swap retired Claude model ids for the recommended replacements, remove temperature/top_p/top_k where targeting Claude 4.7+, and run a regression eval.
2. Scan: confirm the findings, including environment variables set outside the repo.
3. Swap: review and apply the patch on a branch. Then rename `max_tokens` to `max_completion_tokens`, and add `reasoning_effort: "none"` where Chat Completions uses tools or temperature/top_p (or move those calls to the Responses API).
4. Eval: run the regression suite against live models and fix any DRIFT or FAIL.
5. Handoff: merge, deploy, update environment variables, and check your API usage for any remaining calls to GPT-4o / 4.1 models. GET /v1/models doesn't show the 14 Jan 2027 date yet, so don't rely on shutdown_date alone.

_Migration packs: anthropic v2026.10.15.2, openai v2026.10.15.4._
