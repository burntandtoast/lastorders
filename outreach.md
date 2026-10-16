# Outreach templates (drafts for Leigh to review, not sent)

Fill in the {curly} fields from prospects.csv. Keep the evidence link and file name accurate: it's the reason the message isn't spam. Only use the contact route listed in the CSV. For open-source projects and public-sector teams, a helpful GitHub issue or PR usually goes down better than a sales email (see version C).

Primary call to action: a free scan. We look at a copy or branch of their codebase, find retiring model IDs, and confirm which date applies. No obligation.

---

## A. Cold email

**Subject:** {Project}: your code pins a model OpenAI is retiring

Hi {first name or "there"},

I was looking at {project} and noticed `{file path}` calls `{model_id}` ({evidence link}). That pins a model OpenAI is retiring: some GPT-4o / GPT-4.1 snapshots go on **23 October 2026**, the rest on **14 January 2027**. See https://platform.openai.com/docs/deprecations

We offer a free scan of a copy or branch of your code. We find the retiring model IDs and confirm the exact date that applies to you. No obligation, and if it's a one-line fix we'll just say so.

Two catches worth knowing about before then:
- On Chat Completions, the January replacement (`gpt-6-luna`) only does tool calling with `reasoning_effort` set to `none`, so swapping the model name alone can break tool calls. The October models (`gpt-4.1-nano`, `gpt-4o-2024-05-13`) map to `gpt-5.6-luna` / `gpt-5.6-sol` instead.
- Fine-tunes can't move across, and new fine-tuning jobs stop on 6 January 2027.

If the scan shows a paid migration would help, that is a fixed-price job (usually one or two days for a small project): we work on a branch, re-run your structured outputs and tool calls before and after, and send a short regression report. Standard is [PRICE]. Fine-tuned models are quoted separately.

Would a free scan be useful?

Leigh Efford
Burnt and Toast Studios Ltd · burntandtoast.com · hello@burntandtoast.com

(For dated 23 Oct IDs such as `gpt-4.1-nano` or `gpt-4o-2024-05-13`, you may add: "Given the 23 October date, I can start this week." Do not invent a date for undated names like `gpt-4o` or `gpt-4o-mini`.)

---

## B. LinkedIn / X DM (short)

Hi {name}, I spotted `{model_id}` in {project} ({short link}). That pins a model OpenAI is retiring (some on 23 Oct 2026, the rest on 14 Jan 2027). Happy to run a free scan of a copy or branch: we confirm the exact date and whether a one-line swap is enough. The January path (`gpt-6-luna`) breaks tool calls on Chat Completions unless you change the code; the October models go to `gpt-5.6-luna` / `gpt-5.6-sol`. Leigh, Burnt & Toast · hello@burntandtoast.com

---

## C. Open-source / public-sector variant (GitHub issue)

**Title:** `{model_id}` pins a model OpenAI is retiring

Heads-up: `{file path}` defaults to `{model_id}`, which pins a model OpenAI is retiring (https://platform.openai.com/docs/deprecations). Some snapshots go on 23 October 2026, the rest on 14 January 2027. The free scan confirms which date applies and which replacement fits: `gpt-5.6-luna` / `gpt-5.6-sol` for the October models (`gpt-4.1-nano`, `gpt-4o-2024-05-13`), and `gpt-6-luna` for the January batch. If you move to `gpt-6-luna` on Chat Completions, note that tool calling needs `reasoning_effort: "none"`.

Happy to open a PR or run a free scan if that's useful. — Leigh (Burnt & Toast) · hello@burntandtoast.com

(No pricing in this version. It's goodwill, and any paid work follows only if they ask.)

---

### Checks before sending
- Re-open the evidence link to confirm the model ID is still there. It may have been changed since 15 Oct.
- For undated aliases (`gpt-4o`, `gpt-4o-mini`, `gpt-4.1-mini`), say "your code pins a model that OpenAI is retiring" and mention the dates generally. Never claim a specific retirement date for the alias itself; the free scan confirms which dated snapshot (and date) applies.
- For dated IDs only (`gpt-4.1-nano`, `gpt-4o-2024-05-13`), you may name 23 October 2026.
- Fill in [PRICE] only if they ask about paid migration after the free scan. Send one message per prospect, with no follow-up sequence.
