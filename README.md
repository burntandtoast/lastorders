# Last Orders (working name)

**Find retiring AI model IDs in your code before they break.** One command scans your repo for OpenAI
(and, as a preview, Anthropic) model IDs that are being shut down. For each one it tells you the
shutdown date, the replacement the provider recommends, and the code changes the new model needs.

> **Heads-up:** OpenAI removes **GPT-4o, GPT-4o mini, GPT-4.1 and GPT-4.1 mini** from the API on
> **14 January 2027** and recommends `gpt-6-luna`. In our tests, `gpt-6-luna` rejects `max_tokens`, and it
> rejects tool calls on Chat Completions unless `reasoning_effort` is `"none"`. So changing the model name
> isn't enough. The scan flags both.

The scan is free. You don't need an account, a licence or an API key, and your code never leaves your machine.

## Install

```bash
pipx install lastorders        # or: pip install lastorders
```

You need Python 3.10 or later.

## Scan

```bash
lastorders scan .              # scan the current repo
lastorders scan path/to/repo --out scan-results
lastorders scan . --offline    # no network at all (uses the bundled migration pack)
```

You get `scan.md`, a readable report, and `scan.json`, the same data for tools. They go in `lastorders-out/`, or wherever `--out` points. Each finding includes:

- **File, line and model ID**, from code (Python, R, R Markdown, Quarto, JS, TS), `.env` files, YAML, JSON, TOML and docs
- **Shutdown date and recommended replacement**, from the provider's published deprecations
- **Risk level**. High means the date is close or has passed, or the new model needs a code change your
  code doesn't have yet, such as `max_tokens` becoming `max_completion_tokens`, `reasoning_effort` for tools
  and `temperature`, or an unsupported endpoint
- **Fine-tuned models** (`ft:...`), listed separately. They shut down with their base model and can't be
  swapped automatically.
- **Models chosen by environment variable** (`os.getenv("OPENAI_MODEL")`), so you can check the
  values you have deployed
- **SDKs detected**: the official `openai` and `anthropic` clients, LangChain and plain HTTP

Useful flags:

| Flag | What it does |
|---|---|
| `--fail-on-high` | exit code 2 if anything is high risk (for CI) |
| `--include-generated` | also scan generated, minified and vendored files (one summary line each by default; they do not fail CI) |
| `--no-docs` | skip `.md` / `.txt` files |
| `--pack openai` | only use some providers' packs (default: all) |
| `--offline` | use the bundled pack only; makes no network calls |
| `--format json` | print the summary as JSON |
| `--summary-file F` / `--annotations` | CI outputs (used by the GitHub Action) |

## Fix

Without a licence, `swap` and `fix` print a per-file summary of model IDs that would change. They do not print a diff, and they do not write one.

```bash
lastorders fix .
# app/summarise.py: 1 change (gpt-4o-2024-08-06 -> gpt-6-luna)
```

With a licence, the same commands write a reviewable patch and leave the repo unchanged until you apply it:

```bash
lastorders fix .                 # writes lastorders-out/fix.diff + fix-plan.md
lastorders fix . --verify        # also checks the patch on a scratch copy (see below)
git apply lastorders-out/fix.diff
```

`fix` swaps the retiring model IDs and then makes the code changes the new model needs at each API call:

- **Renames `max_tokens`**, to `max_completion_tokens` on Chat Completions or `max_output_tokens` on Responses.
- **Adds `reasoning_effort: "none"`** where gpt-6-luna needs it: Chat Completions calls with tools, and
  calls that set `temperature`, `top_p` or `logprobs`. On Responses it adds `reasoning.effort`.
- **Flags anything it can't decide safely** in `fix-plan.md`: legacy `functions` calls, Assistants and legacy
  Completions calls (these stay on their current model in the patch), fine-tunes and fine-tuning jobs,
  LangChain wrappers, calls that pass `**kwargs` or a spread object, conflicting values, and calls whose model
  isn't visible in the code (use `--assume-model`).

Every change comes from the migration pack's rules. Python is edited with
[libcst](https://github.com/Instagram/LibCST), so your formatting and comments are kept. JS and TS are edited
with a built-in parser. Rules the pack marks `inferred` are only suggested unless you pass `--include-inferred`.

**Old models reject `reasoning_effort`.** We tested gpt-4o and gpt-4.1 against the live API, and both return
HTTP 400. Any fix that adds it has to ship together with the model switch. When the model comes from an
environment variable, the plan marks the fix "ship with the model switch". `--no-model-swap` applies only
the changes that are safe on the old model.

`--verify` applies the patch to a temporary copy of your repo, then:

1. checks the changed files still parse;
2. re-runs the fixer and checks it changes nothing more;
3. replays each fixed call twice: once as it was (old model, old arguments) and once as patched (new model,
   new arguments).

Without `--live`, the replay uses simulated responses. With `--live` and your own `OPENAI_API_KEY` (licence),
the calls go straight to OpenAI. A control run also sends the unpatched arguments to the new model, to show
each fix was needed. `--evals evals/regression.yaml` reruns your own suite with the fixed arguments.

## GitHub Action

Add `.github/workflows/model-scan.yml`:

```yaml
name: Model retirement scan
on:
  pull_request:
  schedule: [{ cron: "0 7 * * 1" }]   # weekly, so new deprecations show up without code changes
permissions:
  contents: read
jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: burntandtoast/lastorders@v0.4.4
        with:
          fail-on-high: "true"
```

The Action posts a summary table to the job page, marks findings inline on the PR and uploads `scan.json`
as an artifact. Inputs:

| Input | Default | |
|---|---|---|
| `path` | `.` | folder to scan |
| `fail-on-high` | `false` | fail the job on high-risk findings |
| `include-docs` | `true` | scan `.md`/`.txt` |
| `annotations` | `true` | inline PR annotations |
| `packs` | all | e.g. `openai,anthropic` |
| `offline` | `false` | bundled pack only, no network |
| `packs-url` | built-in | override the pack URL |
| `version` | action source | install this version from PyPI instead |
| `python-version` | `3.12` | |
| `fix-preview` | `false` | also print the per-file model summary. With `LASTORDERS_LICENCE`, write the patch and run simulated verify |
| `artifact-name` | `lastorders-scan` | |

Outputs: `total`, `high` and `report-dir`.

## Migration packs: where the data comes from

What the scanner knows lives in **migration packs**, versioned JSON files with one pack per provider. Each pack
holds the model IDs and aliases, shutdown dates, replacements, call-site patterns, and parameter and endpoint
rules. Every fact links to the provider's documentation and the date we checked it. Rules we confirmed
against the live API are marked `live-tested`, and anything we assumed is marked `inferred`.

- **OpenAI**: full pack. The default mapping swaps the 14 Jan 2027 GPT-4o / GPT-4.1 batch to `gpt-6-luna`, and the 23 Oct 2026 chat and reasoning models to `gpt-5.6-luna`, `gpt-5.6-sol` or `gpt-5.6-terra`. For those three replacements the paid `fix` rewrites a parameter only when that model's page states the rule. `max_tokens`, sampling parameters and Chat Completions tool calls are flagged until `probes/probe_56.py` confirms them. `o1-pro` (the documented substitute is `gpt-5.6-sol` with `reasoning.mode: pro`), `gpt-image-1` and fine-tunes are flagged, not rewritten. Models that have already shut down, including the 28 Sep 2026 batch and the 23 Jul 2026 batch, are reported as already retired.
- **Anthropic**: preview (stub). It covers Claude API retirement dates from Anthropic's deprecations page.
  Amazon Bedrock and Google Cloud dates for Claude are not covered.
- **Google**: Vertex AI only, and flag-only. `gemini-2.5-pro`, `gemini-2.5-flash` and `gemini-2.5-flash-lite` retire on Vertex on 20 Oct 2026. `gemini-live-2.5-flash-native-audio` retires on 13 Dec 2026; the model versions table lists no replacement ID. `gemini-2.5-flash-image` retires on 15 Mar 2027; the table lists `gemini-3.1-flash-lite-image`. A Vertex retirement is high risk only when that file is using Vertex and the shutdown is within 30 days or already past. On the Gemini API the same IDs are not treated as this retirement, so the finding stays informational. Nothing is rewritten automatically.
- Azure OpenAI and Bedrock: planned

The tool checks for a newer pack once a day and falls back to the copy bundled with the package.
`lastorders packs list` shows which version and source you're using. The format is documented in
[docs/PACKS.md](docs/PACKS.md), with a JSON Schema in `migration_kit/pack_data/pack.schema.json`.

## Privacy and network use

- The scan runs **entirely on your machine**. Your code and prompts are never uploaded.
- **The tool has no telemetry, analytics or tracking.** (Our website counts visits anonymously with Cloudflare Web Analytics: no cookies, no ads, no tracking across sites.)
- The tool only ever contacts us to **download the latest migration pack** (a plain GET of a static JSON file,
  with no identifiers) and, for paid features, to **check a licence key**. That check sends only the key and the
  repo name (`github.com/owner/repo`), and the signed answer is cached for a week, with a 14-day offline grace period after that.
- `--offline` (or `LASTORDERS_OFFLINE=1`) turns off all network access and uses the bundled pack.
- The paid `eval` command calls the AI provider directly **with your own API key**. Nothing goes through us.

## Paid features

| | Free | Licence (per repo) | Done for you |
|---|---|---|---|
| `scan`, GitHub Action, per-file model summary (`fix` / `swap` with no licence) | ✓ | ✓ | ✓ |
| `fix` / `swap` patch (`.diff`, plan, simulated `--verify`), `--apply`, `fix --verify --live`, `init-evals` + `eval`, client-ready `report` | | ✓ | ✓ |
| We do the migration, evals and handoff | | | ✓ |

One licence covers **one GitHub repository, monorepos included**. It's bound to the repo the first time
you use it. Buy one with `lastorders licence buy` (it prints a Stripe Checkout link for this repo), then pass the key
with `LASTORDERS_LICENCE` (a repository secret in Actions) or `--licence`. `lastorders licence status` shows
whether it's verified. Paid commands work `--offline` from the cached check. Repos without an `origin` remote
can set `LASTORDERS_REPO=github.com/owner/repo`. The licence server lives in `server/`; see
[docs/LICENCE-SERVER.md](docs/LICENCE-SERVER.md).

`init-evals` reads the call sites the scan found, including prompts, JSON schemas and tool definitions where
they can be read from the code, and writes a starter `evals/regression.yaml`. You then edit it into 10 to 20
real examples. `eval` runs them against the old and new model with your own key.

## Licence

The free scan is [MIT](LICENSE): the scanner, migration packs, CLI and licence client.

The patch is proprietary ([LICENSE-COMMERCIAL](LICENSE-COMMERCIAL)), together with `eval`, `init-evals` and `report`. That covers `migration_kit/swapper.py` and `migration_kit/fixer/`: generating the diff, writing it, applying it, and simulated or live verify. The source is in this repository so you can read it. Using it requires a paid licence from <https://lastorders.burntandtoast.com>. You may not redistribute that code, or modify it to skip the licence check. Without a licence the CLI prints only the per-file model summary.

## Limitations

- Detection uses pattern matching. Model names built at runtime or stored in a database won't be found;
  env-var lookups are listed so you can check them.
- A pack is only as current as its `updated` date. Always check the provider's documentation before acting.
- The scan names retiring model IDs. Review every licensed patch before you apply it.

---

Made by [Burnt & Toast Studios](https://burntandtoast.com). Not affiliated with OpenAI or Anthropic.
