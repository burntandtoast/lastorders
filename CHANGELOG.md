# Changelog

## Unreleased
- The licence price is now £179 including VAT.

## 0.4.4
- **23 Oct 2026 is in the default mapping.** `lastorders mapping` swaps the chat and reasoning models that shut down that day: `gpt-4.1-nano` (and its snapshot) to `gpt-5.6-luna`; `gpt-4o-2024-05-13`, `gpt-4`, `gpt-4-turbo`, `gpt-4-1106-preview`, `o1`, `o3-mini` (and their snapshots and completions aliases) to `gpt-5.6-sol`; `gpt-3.5-turbo` and `o4-mini` (and their snapshots and the completions alias) to `gpt-5.6-terra`. Dates and substitutes are from OpenAI's deprecations page.
- **Chat Completions rewrites for those replacements are live-tested.** `probes/probe_56-result.json` (16 Oct 2026) shows `gpt-5.6-luna`, `gpt-5.6-sol` and `gpt-5.6-terra` match `gpt-6-luna` on Chat Completions. In the same change as the model switch, `fix` renames `max_tokens` to `max_completion_tokens` and sets `reasoning_effort` to `none` where the call uses temperature (other than 1), `top_p`, `logprobs` or tools. `temperature=1` is left alone. `reasoning_effort` `max` is rejected by the API (the model pages list it) and is flagged, not rewritten. Responses calls that pass those parameters are flagged: the probe did not call the Responses API. Assistants, legacy Completions and fine-tuning stay on the old model and are flagged, which the model pages also say.
- **`o1-pro` and `gpt-image-1` stay flag-only**, as do fine-tunes. The deprecations page replaces `o1-pro` with `gpt-5.6-sol` plus `reasoning.mode: pro`, which a name-only swap would drop.
- **Scanner gaps.** `gpt-4o-mini-transcribe-2025-03-20` (20 Jan 2027), `davinci-002`, `babbage-002`, `computer-use-preview`, and the 28 Sep 2026 and 23 Jul 2026 shutdowns (including `gpt-3.5-turbo-instruct`, `gpt-3.5-turbo-1106` and `gpt-5.2-codex`) are in the OpenAI pack. Past shutdowns are reported as already retired. On Vertex, `gemini-live-2.5-flash-native-audio` (13 Dec 2026, no replacement ID on the page) and `gemini-2.5-flash-image` (15 Mar 2027, `gemini-3.1-flash-lite-image`) are flagged and not rewritten.

## 0.4.3
- **R, R Markdown and Quarto are scanned.** `.R`, `.Rmd` and `.qmd` were missing from the extension list, so a file such as `R/llm_interpret.R` was never opened. Model IDs in code strings are reported as in other languages. Roxygen (`#'`) and other `#` comments are reported too, at low severity, the same cap used for comments elsewhere. In `.Rmd` and `.qmd`, prose outside ` ``` ` fences is documentation (low); IDs inside a code chunk stay at the normal severity.
- **Generated and vendored files are one line each.** By default, `*.generated.*`, `*.gen.*`, `*_pb2.py`, `*.min.js`, files whose first lines say `@generated`, `DO NOT EDIT` or `auto-generated`, and paths under `vendor/`, `third_party/`, `node_modules/`, `.yarn/` or `dist/` are not findings. Each file that contains model IDs is one summary line (`models.generated.ts: 97 model IDs in a generated file, skipped; use --include-generated to scan it`). They do not count toward `--fail-on-high`. `--include-generated` scans them.
- **Short model IDs need a model context.** Bare `o1`, `o3` and the same family match only as a whole quoted token (`"o1"`, `'o3-mini'`), next to a `model` / `engine` / `deployment` key, or as a config value. An assignment in minified code (`D=o1(c)`) is not a hit.

## 0.4.2
- **Google pack** (Vertex AI only, flag only). `gemini-2.5-pro`, `gemini-2.5-flash` and `gemini-2.5-flash-lite` retire on Vertex AI on 20 Oct 2026; suggested replacements start with `gemini-3.8-flash` (Google also lists alternatives per model). No automatic swap and no fix rules. High risk only when the same file is using Vertex (`vertexai`, `google.cloud.aiplatform`, `vertexai=True`, a truthy `GOOGLE_GENAI_USE_VERTEXAI`, an `aiplatform.googleapis.com` URL, or `@google-cloud/vertexai`). Otherwise the finding is informational: these IDs are not deprecated on the Gemini API. The hosted index can list `google` without breaking scanners 0.4.0 and 0.4.1, which skip providers they do not bundle.
- **The fix is proprietary.** `swapper.py` and `fixer/` are under `LICENSE-COMMERCIAL`, with `eval`, `init-evals` and `report`. Without a valid licence, `swap` and `fix` print a per-file summary (`src/app.py: 3 changes (gpt-4-turbo -> gpt-4.1)`) and write nothing. The diff, the plan, simulated `fix --verify` and `--apply` need a licence. No flag or environment variable prints or writes the patch without one. With a licence, the patch behaves as before.

## 0.4.1
- **Licence split.** The free scan, migration packs, CLI, licence client and patch preview (`swap` / `fix` without `--apply`, including simulated `fix --verify`) are MIT (`LICENSE`). `eval`, `init-evals` and `report` are proprietary (`LICENSE-COMMERCIAL`): source is visible, use needs a paid licence, no redistribution and no bypassing the licence check. `swap --apply`, `fix --apply` and `fix --verify --live` stay behind the same check.

## 0.4.0 (2026-10-15)
- **Renamed to Last Orders.** Package, CLI and PyPI name `lastorders`; env vars `LASTORDERS_*` (was the placeholder
  `modelmigrate` / `MODELMIGRATE_*`); output marker `.lastorders-output`; Action `burntandtoast/lastorders@v0`;
  Worker `lastorders-licence`, D1 database `lastorders-licences`, Stripe metadata product `lastorders-repo`.
- **Licence server** (`server/`). This is a Cloudflare Worker with D1:
  - Stripe Checkout at £149 per repo (configurable);
  - a signed webhook that issues `BTM-XXXX-XXXX-XXXX` keys, stores them with the buyer's email, and emails them through Resend (the email provider is pluggable);
  - the repo is bound on first activation;
  - full refunds revoke the licence;
  - a success page and admin rebind/revoke tools;
  - it also serves the pack site.

  Not deployed. See docs/LICENCE-SERVER.md.
- **Real licence check in the CLI**, replacing the format-only placeholder:
  - an online verify sends only the key and repo;
  - a 7-day Ed25519-signed token is cached locally;
  - a 14-day grace period applies if the server is unreachable;
  - `--offline` uses the cached token only;
  - the free `scan` is unaffected.
- New `licence status|buy|forget` command and the `LASTORDERS_REPO` fallback. New dependency: `cryptography`.

## 0.3.0 (unreleased)
- `fix`: automatic code fixes driven entirely by pack rules. It renames `max_tokens` per endpoint, adds
  `reasoning_effort`/`reasoning.effort` "none" where the new model needs it, and flags legacy functions,
  Assistants, legacy Completions, fine-tunes, fine-tuning jobs, LangChain, `**kwargs`/spread and unknown models
  for a manual decision. Python uses libcst (lossless); JS/TS use a built-in lexer. Outputs `fix.diff`, `fix-plan.md` and `fix-plan.json`.
- `fix --verify`: applies the patch to a scratch copy, checks syntax and idempotence, and replays every fixed call
  old vs new. With `--live` it also runs a control (unpatched arguments on the new model). `--evals` reruns the customer suite.
- `fix --apply` is gated behind the licence and refuses files with uncommitted changes unless `--force` is passed.
- Pack format: `signals[].call` (call-level detection) and structured `rules[].fix`
  (`per_endpoint`, `requires_new_model`, `keep_model`). OpenAI pack 2026.10.15.4, Anthropic 2026.10.15.2.
- Live finding (15 Oct 2026): GPT-4o and GPT-4.1 reject `reasoning_effort`, so that fix must ship with the model switch.
- Client report: an "Automatic fixes" section with the verification results.

## 0.2.0 (unreleased)
- Free `scan` packaged for `pip`/`pipx` (entry point then called `modelmigrate`, a placeholder name); no licence or API key needed.
- Provider-neutral **migration packs** (JSON + JSON Schema): OpenAI (full), Anthropic (stub). Fetched from a
  hosted URL at runtime with sha256 check, 24h cache and bundled offline fallback.
- Scanner, swap and report are generic engines driven by pack data (model IDs, aliases, families, shutdown dates,
  replacements, SDK/call-site signals, parameter/endpoint/tool-calling rules).
- GitHub Action (`action.yml`, composite): job summary, PR annotations, artifact upload, optional fail on high risk.
- Placeholder licence gate for `swap --apply`, `eval` and `report` (`LASTORDERS_LICENCE` / `--licence`). One licence = one GitHub repo (monorepos included).
- `init-evals`: generate a starter regression suite from the scan's call sites (prompts, schemas, tools read statically).
- Network policy: only the pack fetch (and, later, the licence check) contacts us; no telemetry. `--offline` / `LASTORDERS_OFFLINE=1`.
- `packs list|validate|build-site`; deployable static pack site for Vercel / Cloudflare Pages.

## 0.1.0
- Internal migration kit: scan, swap, eval (mock + live), client report.
