# OpenAI model migration report: Acme Widgets Ltd (sample)

Prepared by Burnt & Toast Studios on 15 October 2026.

> **Demo: simulated eval outputs on a fictional sample repo**

## At a glance

- **Deadline:** OpenAI removes GPT-4o, GPT-4o mini, GPT-4.1 and GPT-4.1 mini from the API on **14 January 2027** (91 days from this report).
- **Model references found:** 17 across 8 files (8 files scanned).
- **High risk:** 7 | **Medium:** 8 | **Low:** 1 | **Info:** 1
- **Fine-tuned models:** 1 (need a separate decision)
- **Models set by environment variable:** `CLASSIFIER_MODEL`, `OPENAI_MODEL` (check the live values on your servers)
- **Proposed patch:** 10 replacements in 7 files, 2 fine-tuned references left untouched
- **Regression eval (mock):** 1 drift, 1 fail, 4 pass

## What OpenAI has confirmed

Source: [https://developers.openai.com/api/docs/deprecations](https://developers.openai.com/api/docs/deprecations) and [gpt-6-luna model page](https://developers.openai.com/api/docs/models/gpt-6-luna), checked 2026-10-15.

- OpenAI announced on 14 Oct 2026 that these GPT-4 series snapshots will be removed from the API on 14 Jan 2027: gpt-4o-2024-08-06, gpt-4o-2024-11-20, gpt-4o-mini-2024-07-18, gpt-4.1-2025-04-14, gpt-4.1-mini-2025-04-14.
- OpenAI's recommended replacement for all five is gpt-6-luna.
- Fine-tuned versions of the GPT-4 series models follow the same shutdown schedule as their base models (shutdown 14 Jan 2027).
- gpt-6-luna does not support fine-tuning (model page: Fine-tuning - Not supported).
- From 6 Jan 2027, active existing customers can no longer create new fine-tuning jobs.
- gpt-6-luna supports Chat Completions, Responses, Batch, structured outputs and function calling; on Chat Completions, function calling works only with reasoning_effort set to 'none'.
- gpt-6-luna does not support the Assistants API or legacy /v1/completions.
- OpenAI documents a shutdown_date field on GET /v1/models (not yet filled in for this batch; see the live checks).

## Confirmed by our own live API checks (2026-10-15)

- gpt-6-luna rejects `max_tokens` (400 unsupported_parameter, at every reasoning effort). Use `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses). `max_completion_tokens` also works on gpt-4o-2024-08-06.
- gpt-6-luna accepts temperature, top_p and logprobs only with reasoning_effort 'none'. At the default and 'low' effort, temperature is accepted only at 1, and top_p and logprobs are rejected. On the Responses API, temperature and top_p work with reasoning.effort 'none' and are rejected at the default effort.
- Chat Completions + function tools on gpt-6-luna returns 400 unless reasoning_effort is 'none' ('low' and the default both fail). Function tools on the Responses API work at the default effort.
- Undated aliases still resolve: gpt-4o -> gpt-4o-2024-08-06, gpt-4o-mini -> gpt-4o-mini-2024-07-18, gpt-4.1 -> gpt-4.1-2025-04-14, gpt-4.1-mini -> gpt-4.1-mini-2025-04-14.
- GET /v1/models shows shutdown_date null for all nine GPT-4o / 4.1 ids (aliases and dated snapshots) and for gpt-6-luna. The 14 Jan 2027 date isn't in the API yet, so for this batch it's not a reliable check. Earlier batches are populated (e.g. gpt-4.1-nano and gpt-4o-2024-05-13 show 2026-10-23).

## What we have not been able to confirm

- Whether the undated aliases (gpt-4o, gpt-4o-mini, gpt-4.1, gpt-4.1-mini) are retired or re-pointed on 14 Jan 2027. Today they resolve to dated snapshots that are on the shutdown list. OpenAI hasn't said what happens to them, and GET /v1/models doesn't show a shutdown date for them yet, so we treat them as affected.
- Output quality, latency and cost on the client's own workload. Only the regression eval below can show that.

## Findings

| Risk | File | Line | Current model | Suggested | Category | Notes |
|---|---|---|---|---|---|---|
| **high** | `app/agent.py` | 8 | `gpt-4o-mini` | `gpt-6-luna` (inferred) | GPT-4o / 4.1 (shutdown 14 Jan 2027) | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list (gpt-4o -> gpt-4o-2024-08-06, gpt-4o-mini -> gpt-4o-mini-2024-07-18, gpt-4.1 -> gpt-4.1-2025-04-14, gpt-4.1-mini -> gpt-4.1-mini-2025-04-14). OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected.<br>Chat Completions + tools in this file: gpt-6-luna returns HTTP 400 for function tools on Chat Completions unless reasoning_effort is 'none' (docs + live-tested). Set it, or move to the Responses API. |
| **high** | `app/agent.py` | 36 | `ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1` | decision needed | Fine-tuned model | Fine-tune of gpt-4o-mini-2024-07-18; per OpenAI it shuts down with its base model on 2027-01-14.<br>No automatic replacement: gpt-6-luna does not support fine-tuning. Options are prompting/few-shot on gpt-6-luna validated with `eval`, or re-training on a fine-tunable model (none confirmed by the kit). New fine-tuning jobs stop on 6 Jan 2027. |
| **high** | `app/summarise.py` | 20 | `gpt-4o-2024-08-06` | `gpt-6-luna` | GPT-4o / 4.1 (shutdown 14 Jan 2027) | Uses `max_tokens`: gpt-6-luna rejects it with HTTP 400 (live-tested). Rename to `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses).<br>Structured output in this file: gpt-6-luna lists structured_outputs as supported; verify schemas with `eval`.<br>Sets temperature/top_p/logprobs: gpt-6-luna accepts these only with reasoning_effort 'none'; at other efforts temperature must be 1 and top_p/logprobs return HTTP 400 (live-tested). |
| **high** | `config/models.yaml` | 5 | `gpt-4.1-nano` | `gpt-5.6-luna` | Other deprecated model | Shuts down 23 Oct 2026, before the main deadline.<br>Outside the GPT-4o/4.1 migration; OpenAI's listed replacement is gpt-5.6-luna. |
| **high** | `config/models.yaml` | 6 | `ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1` | decision needed | Fine-tuned model | Fine-tune of gpt-4o-mini-2024-07-18; per OpenAI it shuts down with its base model on 2027-01-14.<br>No automatic replacement: gpt-6-luna does not support fine-tuning. Options are prompting/few-shot on gpt-6-luna validated with `eval`, or re-training on a fine-tunable model (none confirmed by the kit). New fine-tuning jobs stop on 6 Jan 2027. |
| **high** | `config/settings.json` | 2 | `gpt-4o-2024-11-20` | `gpt-6-luna` | GPT-4o / 4.1 (shutdown 14 Jan 2027) | Uses `max_tokens`: gpt-6-luna rejects it with HTTP 400 (live-tested). Rename to `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses). |
| **high** | `web/src/chat.ts` | 7 | `gpt-4.1` | `gpt-6-luna` (inferred) | GPT-4o / 4.1 (shutdown 14 Jan 2027) | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list (gpt-4o -> gpt-4o-2024-08-06, gpt-4o-mini -> gpt-4o-mini-2024-07-18, gpt-4.1 -> gpt-4.1-2025-04-14, gpt-4.1-mini -> gpt-4.1-mini-2025-04-14). OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected.<br>Chat Completions + tools in this file: gpt-6-luna returns HTTP 400 for function tools on Chat Completions unless reasoning_effort is 'none' (docs + live-tested). Set it, or move to the Responses API. |
| **medium** | `.env.example` | 2 | `gpt-4o-mini` | `gpt-6-luna` (inferred) | GPT-4o / 4.1 (shutdown 14 Jan 2027) | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list (gpt-4o -> gpt-4o-2024-08-06, gpt-4o-mini -> gpt-4o-mini-2024-07-18, gpt-4.1 -> gpt-4.1-2025-04-14, gpt-4.1-mini -> gpt-4.1-mini-2025-04-14). OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected. |
| **medium** | `.env.example` | 3 | `gpt-4.1-mini` | `gpt-6-luna` (inferred) | GPT-4o / 4.1 (shutdown 14 Jan 2027) | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list (gpt-4o -> gpt-4o-2024-08-06, gpt-4o-mini -> gpt-4o-mini-2024-07-18, gpt-4.1 -> gpt-4.1-2025-04-14, gpt-4.1-mini -> gpt-4.1-mini-2025-04-14). OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected. |
| **medium** | `config/models.yaml` | 2 | `gpt-4o` | `gpt-6-luna` (inferred) | GPT-4o / 4.1 (shutdown 14 Jan 2027) | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list (gpt-4o -> gpt-4o-2024-08-06, gpt-4o-mini -> gpt-4o-mini-2024-07-18, gpt-4.1 -> gpt-4.1-2025-04-14, gpt-4.1-mini -> gpt-4.1-mini-2025-04-14). OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected. |
| **medium** | `config/models.yaml` | 3 | `gpt-4o-mini-2024-07-18` | `gpt-6-luna` | GPT-4o / 4.1 (shutdown 14 Jan 2027) |  |
| **medium** | `config/models.yaml` | 4 | `gpt-4.1-2025-04-14` | `gpt-6-luna` | GPT-4o / 4.1 (shutdown 14 Jan 2027) |  |
| **medium** | `config/models.yaml` | 8 | `gpt-4o-transcribe` | `gpt-live-transcribe or gpt-transcribe` | Other deprecated model | Not a chat model. Do not map to gpt-6-luna (Luna does not support transcription).<br>Outside the GPT-4o/4.1 migration; OpenAI's listed replacement is gpt-live-transcribe or gpt-transcribe. |
| **medium** | `web/src/chat.ts` | 24 | `gpt-4o-transcribe` | `gpt-live-transcribe or gpt-transcribe` | Other deprecated model | Not a chat model. Do not map to gpt-6-luna (Luna does not support transcription).<br>Outside the GPT-4o/4.1 migration; OpenAI's listed replacement is gpt-live-transcribe or gpt-transcribe. |
| **medium** | `web/src/classify.js` | 4 | `gpt-4.1-mini-2025-04-14` | `gpt-6-luna` | GPT-4o / 4.1 (shutdown 14 Jan 2027) |  |
| **low** | `README.md` | 4 | `gpt-4o` | `gpt-6-luna` (inferred) | GPT-4o / 4.1 (shutdown 14 Jan 2027) | Undated alias. Live check 15 Oct 2026: it still resolves, to a dated snapshot on the 14 Jan 2027 list (gpt-4o -> gpt-4o-2024-08-06, gpt-4o-mini -> gpt-4o-mini-2024-07-18, gpt-4.1 -> gpt-4.1-2025-04-14, gpt-4.1-mini -> gpt-4.1-mini-2025-04-14). OpenAI hasn't said whether the alias is retired or re-pointed, so it's treated as affected.<br>Appears in documentation/comment only. |
| **info** | `config/settings.json` | 3 | `gpt-5.6-sol` | decision needed | Not in catalogue | Not in the kit's deprecation catalogue. Leave as-is unless the client wants to consolidate. |

## Fine-tuned models

These can't be swapped automatically. gpt-6-luna can't be fine-tuned, so for each one you choose to:

1. replace it with gpt-6-luna plus a stronger prompt and examples, proven with the regression eval, or
2. re-train on another fine-tunable model, before new fine-tuning jobs close on 6 January 2027.

- `ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1` in `app/agent.py` line 36
- `ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1` in `config/models.yaml` line 6

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
--- a/app/summarise.py
+++ b/app/summarise.py
@@ -17,7 +17,7 @@
 
 def summarise(ticket: str) -> str:
     resp = client.chat.completions.create(
-        model="gpt-4o-2024-08-06",
+        model="gpt-6-luna",
         temperature=0.2,
         max_tokens=400,
         messages=[{"role": "user", "content": ticket}],
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

1. **Scan:** confirm the findings above, including environment variables set outside the repo.
2. **Swap:** review and apply the patch on a branch. Then rename `max_tokens` to `max_completion_tokens`, add `reasoning_effort: "none"` where Chat Completions uses tools or temperature/top_p (or move to the Responses API).
3. **Eval:** run the regression suite against live models; fix prompts or schemas for any DRIFT or FAIL.
4. **Handoff:** merge, deploy, update environment variables, and check your API usage for any remaining calls to GPT-4o / 4.1 models. (GET /v1/models doesn't show the 14 Jan 2027 date yet, so don't rely on shutdown_date alone.)
