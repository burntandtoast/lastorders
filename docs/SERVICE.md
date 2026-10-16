# Internal: done-for-you migration service and live findings

> Internal notes for Burnt & Toast Studios. The public README covers the free scan.
> The product is now **Last Orders**: CLI/PyPI name `lastorders`, env vars `LASTORDERS_*` (was the placeholder ModelMigrate / `modelmigrate` / `MODELMIGRATE_*`).
> The Install/Usage/Layout sections below describe v0.1 and are superseded by the README and `lastorders --help`.

## What OpenAI has confirmed (checked 15 Oct 2026)

Sources: <https://developers.openai.com/api/docs/deprecations> and
<https://developers.openai.com/api/docs/models/gpt-6-luna>. Re-check both before each job.
Everything the kit "knows" lives in `migration_kit/pack_data/openai.json`.

- Announced 14 Oct 2026, shutdown **14 Jan 2027**, replacement **`gpt-6-luna`** for:
  `gpt-4o-2024-08-06`, `gpt-4o-2024-11-20`, `gpt-4o-mini-2024-07-18`, `gpt-4.1-2025-04-14`,
  `gpt-4.1-mini-2025-04-14`.
- Fine-tuned versions shut down with their base model.
- `gpt-6-luna` **cannot be fine-tuned**. From **6 Jan 2027** existing customers can't create new
  fine-tuning jobs at all.
- `gpt-6-luna` supports Chat Completions, Responses, Batch, structured outputs and function calling.
  **On Chat Completions, function calling only works with `reasoning_effort: "none"`.**
- `gpt-6-luna` doesn't support the Assistants API or legacy `/v1/completions`.
- `GET /v1/models` documents a `shutdown_date` per model (but see the live checks below: not filled in yet for this batch).
- Neighbouring shutdowns the scan also catches: `gpt-4.1-nano` and `gpt-4o-2024-05-13` go on
  **23 Oct 2026** (to `gpt-5.6-luna` / `gpt-5.6-sol`). The `gpt-4o-*` transcription, TTS, audio and realtime
  models have *different* replacements and must not be mapped to `gpt-6-luna`.

### Confirmed by live API checks (15 Oct 2026)

These come from calls to the real API with our key. The scripts are in `probes/`, and the raw results are in
`probes/*-result.json`. They're Chat Completions unless stated.

| Question | Result |
|---|---|
| `max_tokens` on `gpt-6-luna` | **Rejected** (400 `unsupported_parameter`) at every reasoning effort. Use `max_completion_tokens` (Chat) / `max_output_tokens` (Responses). `max_completion_tokens` also works on `gpt-4o-2024-08-06`. |
| `temperature` | Accepted with `reasoning_effort: "none"`. At the default or `low` effort, only `1` is allowed (`0.2` returns 400). Responses API: accepted with `reasoning.effort: "none"`, rejected at the default effort. |
| `top_p` | Accepted with effort `none`, rejected otherwise (Chat and Responses). |
| `logprobs` | Accepted (and returned) with effort `none`, rejected otherwise. |
| Chat Completions + function tools | **400 without `reasoning_effort: "none"`** (default and `low` both fail, with an error saying to use `/v1/responses` or set effort to `none`). Works with `none`. Responses API tools work at the default effort. |
| Undated aliases | Still resolve: `gpt-4o` -> `gpt-4o-2024-08-06`, `gpt-4o-mini` -> `gpt-4o-mini-2024-07-18`, `gpt-4.1` -> `gpt-4.1-2025-04-14`, `gpt-4.1-mini` -> `gpt-4.1-mini-2025-04-14` (all on the shutdown list). |
| `GET /v1/models` `shutdown_date` | **`null` for all nine GPT-4o/4.1 ids and for `gpt-6-luna`**. The 14 Jan 2027 date isn't in the API yet. Older batches are populated (e.g. `gpt-4.1-nano` and `gpt-4o-2024-05-13` show `2026-10-23`). One mismatch: `gpt-4o-mini-tts-2025-03-20` shows `2026-07-23` in the API but 6 Jan 2027 on the docs page. |

- **gpt-4o-2024-08-06, gpt-4o-mini-2024-07-18 and gpt-4.1-2025-04-14 reject `reasoning_effort`** on Chat Completions ("Unrecognized request argument supplied"), and gpt-4.1-mini-2025-04-14 rejects `reasoning.effort` on Responses. So the `reasoning_effort: "none"` fix has to ship together with the model switch (`probes/params3-result.json`).
- `fix --verify --live` on the sample repo: all 4 patched calls were accepted by gpt-6-luna. Without the fix, all 3 changed calls were rejected (2× tools without `reasoning_effort` "none", 1× `max_tokens`). On the fixture repo, 0 unexpected rejections: the 3 rejected calls all had open manual items. Responses accepts `reasoning: {summary: "auto", effort: "none"}` together with `top_p`. Total token use across all runs was under 3k (less than $0.03).

### Still not confirmed

- **Undated aliases after 14 Jan 2027:** OpenAI hasn't said whether `gpt-4o` etc. are retired or re-pointed.
  They point at deprecated snapshots today, so the kit treats them as affected and marks them *inferred*.
- **Handoff check:** until OpenAI fills in `shutdown_date` for this batch, an empty `shutdown_date` is *not*
  evidence that a model is safe. At handoff, check usage for GPT-4o/4.1 model ids directly.

### Live eval on the sample repo (15 Oct 2026)

`examples/live-output/` holds a real run of `examples/evals/sample-suite.yaml` (6 cases,
`gpt-4o-2024-08-06` vs `gpt-6-luna`, output capped at 300 tokens) on Chat Completions, plus a second run on the
Responses API in `responses-api/`. Both API paths worked without request-format errors. Both runs came out
2 pass and 4 drift, with no schema or tool-name failures. The drifts were: different tag naming style (`refund_issue` vs `damaged-order`),
`priority` changing on an ambiguous ticket, a time argument changing from `19:30` to `7:30 PM` in one run, and
lexically different (but on-brief) apology text. Neither model knows today's date, so prompts with relative dates
("next Friday") should be given the date in the system prompt. Estimated cost of each run was under $0.005.

## Install

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/lastorders --help          # or: python -m migration_kit --help
.venv/bin/pytest -q
```

Needs Python 3.10+, `pyyaml` and `jsonschema`. HTTP calls use the standard library, so the OpenAI SDK isn't needed.

## Usage

### 1. Scan

```bash
lastorders scan /path/to/client-repo --out out/
```

Walks `.py .R .Rmd .qmd .js .mjs .cjs .jsx .ts .tsx`, `.env*`, YAML/JSON/TOML/INI and docs (skip with `--no-docs`).
Roxygen and other `#` comments are reported at low severity. Generated and vendored files are not findings:
`*.generated.*`, `*.gen.*`, `*_pb2.py`, `*.min.js`, a `@generated` / `DO NOT EDIT` / `auto-generated` header,
and `vendor/`, `third_party/`, `node_modules/`, `.yarn/` and `dist/`. Each of those files that contains model
IDs is one summary line, and it does not count toward `--fail-on-high`. `--include-generated` scans them.
`.venv` and other tool caches are ignored entirely. Writes `out/scan.md` and `out/scan.json` with the file,
line, current model, suggested replacement, shutdown date, risk and notes for each finding. It also:

- puts **fine-tuned ids** (`ft:...`) in their own section, with no automatic replacement;
- raises risk to **high** where the file (or config) uses `max_tokens` (rejected by `gpt-6-luna`), Chat
  Completions + tools without `reasoning_effort: "none"`, `temperature`/`top_p`/`logprobs` without effort `none`,
  the Assistants API or legacy completions;
- lists **env-var model lookups** (`os.getenv("OPENAI_MODEL")`, `process.env.X_MODEL`) whose live values sit
  outside the repo.

`--fail-on-high` exits 2 when there are high-risk findings, so it can run in CI.

### 2. Swap

```bash
lastorders swap /path/to/client-repo --mapping mappings/gpt4-series-to-gpt-6-luna.yaml --out out/
git -C /path/to/client-repo apply --check out/model-swap.diff   # then apply on a branch
```

Exact-token replacement driven by the mapping YAML. With a licence it writes `model-swap.diff` and
`swap-summary.json` and **does not modify the repo** unless you pass `--apply`. Without a licence it
prints a per-file model summary and writes nothing. Fine-tuned ids are skipped unless listed
individually under `fine_tuned:`. Docs are skipped unless `include_docs: true` or `--include-docs` is set.
The swap changes model ids only. Code changes such as adding `reasoning_effort` are flagged in the scan,
and we make them by hand.

### 3. Eval

```bash
OPENAI_API_KEY=sk-... lastorders eval examples/evals/sample-suite.yaml --out out/
lastorders eval examples/evals/sample-suite.yaml --dry-run --out out/   # offline, simulated
```

The suite is YAML: `models: {old, new}`, `api: chat|responses`, `max_output_tokens` (sent as
`max_completion_tokens` on Chat, `max_output_tokens` on Responses), optional `pricing` (USD per 1M tokens, for a
cost estimate), optional per-side `model_params` (the sample sends `reasoning_effort: none` to the new model;
on the Responses API it's translated to `reasoning: {effort: none}`), and `cases` of three types:

| type | checks |
|---|---|
| `structured` | output parses, validates against `schema` on both models, field-by-field diff (skip free-text fields with `ignore_fields`), similarity |
| `tool_call` | tool names match, args validate against each tool's `parameters`, argument diff, optional `expect: {tool, args}` |
| `text` | lexical similarity (difflib) vs `min_similarity`, optional `must_include` phrases |

Statuses are `pass`, `drift` (valid but different, so needs review), `fail` (new model breaks a check),
`error` (API error) and `improved`. Without `OPENAI_API_KEY`, or with `--dry-run`/`--mock`, it runs
offline. It uses each case's `mock:` outputs where given and otherwise synthesises schema-valid ones,
and every result is labelled as simulated. Live runs record the resolved model, token usage, truncation
(`finish_reason: length`) and estimated cost. `OPENAI_BASE_URL` is honoured. `--fail-on-regression` exits 3.
`RUN_LIVE_TESTS=1 pytest tests/test_live_findings.py` runs one tiny live smoke test.

### 4. Report

```bash
lastorders report --client "Client Ltd" --scan out/scan.json --swap-summary out/swap-summary.json \
  --diff out/model-swap.diff --eval out/eval.json --out out/
```

Produces `client-report.html` (self-contained, no JS) and `client-report.md`. `--label` adds a banner, for
example to mark a demo or a live run.

### Demo

`lastorders demo` runs scan, the unlicensed model-id summary, a simulated eval and a report on
`examples/sample-app` (a fictional "Acme Widgets" codebase) and writes to `examples/demo-output/`.
It does not write a patch. The demo eval is a dry run with one deliberate DRIFT and one FAIL, so
the report shows what problems look like. A licensed `swap` or `fix` is what writes `model-swap.diff` and `fix.diff`.

## The service: scan, swap, eval, handoff

1. **Scan (est. half a day).** We get read access to the repo and run `scan`. We also ask for production env
   var values and call `GET /v1/models` on their key to check each model's `shutdown_date`. They
   get the scan section of the report, plus a fixed quote that prices fine-tunes separately.
2. **Swap (est. half a day).** We agree the mapping, generate the patch, and hand-fix flagged call sites:
   `max_tokens` -> `max_completion_tokens`, `reasoning_effort: "none"` on Chat Completions + tools or
   temperature/top_p (or move them to Responses), and legacy `functions`. Everything goes on a branch or PR, never straight to main.
3. **Eval (est. half a day to a day).** We build a 10 to 30 case suite from their real prompts, schemas and tools,
   run it live against old and new, and fix prompts or schemas until DRIFT and FAIL are understood or resolved.
   Fine-tunes are evaluated as "base `gpt-6-luna` + prompt" against the fine-tune.
4. **Handoff.** They get the client report, merged PR, eval suite (re-runnable in their CI) and an
   env-var checklist. After deploy we check the client's API usage for any remaining calls to GPT-4o/4.1 ids.
   (`shutdown_date` on `GET /v1/models` isn't filled in for this batch yet, so it can't be the only check.)

## Layout

```
migration_kit/   catalogue.py (deprecation facts), scanner.py, swapper.py, evaluator.py, report.py, cli.py
mappings/        gpt4-series-to-gpt-6-luna.yaml
examples/        sample-app/, evals/sample-suite.yaml, demo-output/ (simulated), live-output/ (real API run)
probes/          live API checks (models, parameters) + their JSON results; never print the key
tests/           pytest suite (offline; includes a fake OpenAI HTTP server)
```

## Known limitations

- Detection is regex-based. Model ids built at runtime (`"gpt-" + version`) or stored in a database
  won't be found. Env-var lookups are listed so they can be checked by hand.
- Text similarity is lexical (difflib), not semantic. Use `must_include`, or read the diffs.
- Single run per case: no repeated sampling or variance measurement yet.
- The swap only changes model ids. Parameter fixes (`max_tokens`, `reasoning_effort`) are flagged by the scan
  and done by hand.
- The cost estimate needs prices in the suite's `pricing:` block (taken from OpenAI model pages), and it doesn't
  account for cached-input discounts.
