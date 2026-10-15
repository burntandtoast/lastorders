# Changelog

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
- Free `scan` packaged for `pip`/`pipx` (`modelmigrate` entry point; the name is a placeholder, see `scripts/rename_product.py`); no licence or API key needed.
- Provider-neutral **migration packs** (JSON + JSON Schema): OpenAI (full), Anthropic (stub). Fetched from a
  hosted URL at runtime with sha256 check, 24h cache and bundled offline fallback.
- Scanner, swap and report are generic engines driven by pack data (model IDs, aliases, families, shutdown dates,
  replacements, SDK/call-site signals, parameter/endpoint/tool-calling rules).
- GitHub Action (`action.yml`, composite): job summary, PR annotations, artifact upload, optional fail on high risk.
- Placeholder licence gate for `swap --apply`, `eval` and `report` (`MODELMIGRATE_LICENCE` / `--licence`). One licence = one GitHub repo (monorepos included).
- `init-evals`: generate a starter regression suite from the scan's call sites (prompts, schemas, tools read statically).
- Network policy: only the pack fetch (and, later, the licence check) contacts us; no telemetry. `--offline` / `MODELMIGRATE_OFFLINE=1`.
- `packs list|validate|build-site`; deployable static pack site for Vercel / Cloudflare Pages.

## 0.1.0
- Internal migration kit: scan, swap, eval (mock + live), client report.
