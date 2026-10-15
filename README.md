# OpenAI API migration kit (Burnt & Toast Studios)

A small Python CLI behind our fixed-price **"OpenAI API migration"** service for agencies and
SaaS founders still on GPT-4o / GPT-4.1 before OpenAI removes them from the API on
**14 January 2027**.

```
bt-migrate scan    -> find every model ID (and fine-tune) in a repo, with risk notes
bt-migrate swap    -> turn a mapping file into a reviewable .diff (never edits in place by default)
bt-migrate eval    -> regression-test old vs new model: JSON-schema output, tool calls, text similarity
bt-migrate report  -> client-facing HTML + Markdown report
bt-migrate demo    -> run all of the above, offline, on examples/
```

## What OpenAI has confirmed (checked 15 Oct 2026)

Sources: <https://developers.openai.com/api/docs/deprecations> and
<https://developers.openai.com/api/docs/models/gpt-6-luna>. Re-check both before each job.
Everything the kit "knows" lives in `migration_kit/catalogue.py`.

- Announced 14 Oct 2026, shutdown **14 Jan 2027**, replacement **`gpt-6-luna`** for:
  `gpt-4o-2024-08-06`, `gpt-4o-2024-11-20`, `gpt-4o-mini-2024-07-18`, `gpt-4.1-2025-04-14`,
  `gpt-4.1-mini-2025-04-14`.
- Fine-tuned versions shut down with their base model.
- `gpt-6-luna` **cannot be fine-tuned**. From **6 Jan 2027** existing customers can't create new
  fine-tuning jobs at all.
- `gpt-6-luna` supports Chat Completions, Responses, Batch, structured outputs and function calling.
  **On Chat Completions, function calling only works with `reasoning_effort: "none"`.**
- `gpt-6-luna` doesn't support the Assistants API or legacy `/v1/completions`.
- `GET /v1/models` returns a `shutdown_date` per model. Use it on the client's account at handoff.
- Neighbouring shutdowns the scan also catches: `gpt-4.1-nano` and `gpt-4o-2024-05-13` go on
  **23 Oct 2026** (to `gpt-5.6-luna` / `gpt-5.6-sol`). The `gpt-4o-*` transcription, TTS, audio and realtime
  models have *different* replacements and must not be mapped to `gpt-6-luna`.

### Not confirmed (treated cautiously)

- **Undated aliases** (`gpt-4o`, `gpt-4o-mini`, `gpt-4.1`, `gpt-4.1-mini`): the page names the families
  but lists only dated snapshots. The kit treats the aliases as affected and marks them *inferred*.
- **Sampling params** (`temperature`, `top_p`, `max_tokens`, `logprobs`) on `gpt-6-luna` aren't covered
  on the pages we read. The scan flags them and the eval tests them.
- **Live API mode** of `eval` has been tested against a local fake server only, not the real API
  (no key was available). Request shapes follow the documented Chat Completions / Responses formats.

## Install

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/bt-migrate --help          # or: python -m migration_kit --help
.venv/bin/pytest -q
```

Needs Python 3.10+, `pyyaml` and `jsonschema`. HTTP calls use the standard library, so the OpenAI SDK isn't needed.

## Usage

### 1. Scan

```bash
bt-migrate scan /path/to/client-repo --out out/
```

Walks `.py .js .mjs .cjs .jsx .ts .tsx`, `.env*`, YAML/JSON/TOML/INI and docs (skip with `--no-docs`),
ignoring `node_modules`, `.venv`, `dist` and similar. Writes `out/scan.md` and `out/scan.json` with the file,
line, current model, suggested replacement, shutdown date, risk and notes for each finding. It also:

- puts **fine-tuned ids** (`ft:...`) in their own section, with no automatic replacement;
- raises risk where the file uses **Chat Completions + tools** (`reasoning_effort` caveat), the Assistants API,
  legacy completions or sampling params;
- lists **env-var model lookups** (`os.getenv("OPENAI_MODEL")`, `process.env.X_MODEL`) whose live values sit
  outside the repo.

`--fail-on-high` exits 2 when there are high-risk findings, so it can run in CI.

### 2. Swap

```bash
bt-migrate swap /path/to/client-repo --mapping mappings/gpt4-series-to-gpt-6-luna.yaml --out out/
git -C /path/to/client-repo apply --check out/model-swap.diff   # then apply on a branch
```

Exact-token replacement driven by the mapping YAML. It writes `model-swap.diff` and `swap-summary.json`
and **does not modify the repo** unless you pass `--apply`. Fine-tuned ids are skipped unless listed
individually under `fine_tuned:`. Docs are skipped unless `include_docs: true` or `--include-docs` is set.
The swap changes model ids only. Code changes such as adding `reasoning_effort` are flagged in the scan,
and we make them by hand.

### 3. Eval

```bash
OPENAI_API_KEY=sk-... bt-migrate eval examples/evals/sample-suite.yaml --out out/
bt-migrate eval examples/evals/sample-suite.yaml --dry-run --out out/   # offline, simulated
```

The suite is YAML: `models: {old, new}`, `api: chat|responses`, optional per-side `model_params`
(the sample sends `reasoning_effort: none` to the new model), and `cases` of three types:

| type | checks |
|---|---|
| `structured` | output parses, validates against `schema` on both models, field-by-field diff, similarity |
| `tool_call` | tool names match, args validate against each tool's `parameters`, argument diff, optional `expect: {tool, args}` |
| `text` | lexical similarity (difflib) vs `min_similarity`, optional `must_include` phrases |

Statuses are `pass`, `drift` (valid but different, so needs review), `fail` (new model breaks a check),
`error` (API error) and `improved`. Without `OPENAI_API_KEY`, or with `--dry-run`/`--mock`, it runs
offline. It uses each case's `mock:` outputs where given and otherwise synthesises schema-valid ones,
and every result is labelled as simulated. `OPENAI_BASE_URL` is honoured. `--fail-on-regression` exits 3.

### 4. Report

```bash
bt-migrate report --client "Client Ltd" --scan out/scan.json --swap-summary out/swap-summary.json \
  --diff out/model-swap.diff --eval out/eval.json --out out/
```

Produces `client-report.html` (self-contained, no JS) and `client-report.md`.

### Demo

`bt-migrate demo` runs the whole pipeline on `examples/sample-app` (a fictional "Acme Widgets" codebase) and
writes to `examples/demo-output/`. The demo eval is a dry run with one deliberate DRIFT and one FAIL, so
the report shows what problems look like.

## The service: scan, swap, eval, handoff

1. **Scan (est. half a day).** We get read access to the repo and run `scan`. We also ask for production env
   var values and call `GET /v1/models` on their key to check each model's `shutdown_date`. They
   get the scan section of the report, plus a fixed quote that prices fine-tunes separately.
2. **Swap (est. half a day).** We agree the mapping, generate the patch, and hand-fix flagged call sites:
   `reasoning_effort: "none"` on Chat Completions + tools (or move them to Responses), legacy `functions`,
   and sampling params. Everything goes on a branch or PR, never straight to main.
3. **Eval (est. half a day to a day).** We build a 10 to 30 case suite from their real prompts, schemas and tools,
   run it live against old and new, and fix prompts or schemas until DRIFT and FAIL are understood or resolved.
   Fine-tunes are evaluated as "base `gpt-6-luna` + prompt" against the fine-tune.
4. **Handoff.** They get the client report, merged PR, eval suite (re-runnable in their CI) and an
   env-var checklist. After deploy we check the client's API usage for any remaining calls to retired
   models, and use `GET /v1/models` to confirm that nothing they still call has a `shutdown_date`.

## Layout

```
migration_kit/   catalogue.py (deprecation facts), scanner.py, swapper.py, evaluator.py, report.py, cli.py
mappings/        gpt4-series-to-gpt-6-luna.yaml
examples/        sample-app/, evals/sample-suite.yaml, demo-output/
tests/           pytest suite (offline; includes a fake OpenAI HTTP server)
```

## Known limitations

- Detection is regex-based. Model ids built at runtime (`"gpt-" + version`) or stored in a database
  won't be found. Env-var lookups are listed so they can be checked by hand.
- Text similarity is lexical (difflib), not semantic. Use `must_include`, or read the diffs.
- Single run per case: no repeated sampling or variance measurement yet.
- No cost or latency comparison in the report yet (latency and usage are recorded in `eval.json` on live runs).
