# Changelog

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
