# Migration pack format (pack_format 1)

A pack is a JSON file with one provider per pack. The schema is `migration_kit/pack_data/pack.schema.json`,
also hosted as `v1/pack.schema.json`. The scanner, swap mapping, report and (phase 2) auto-fixer are generic
engines. All provider knowledge lives in packs.

| Key | Purpose |
|---|---|
| `provider`, `name`, `version` (`YYYY.MM.DD[.N]`), `updated`, `status` (`stable`/`stub`/`example`) | identity; the highest version wins |
| `sources[]` | `{id, title, url, checked}`. Every fact should point at one |
| `id_patterns[]` | regexes for model-ID tokens (the engine adds token boundaries). `quoted_only` for ambiguous IDs such as `o3` |
| `fine_tune` | `{pattern, base_group, risk, notes}`: how to spot a fine-tune and extract its base model |
| `migrations[]` | named retirement events `{id, title, announced, shutdown, replacement, headline}`. `headline` ones drive the report deadline and the default swap mapping |
| `models[]` | `{id, kind: snapshot/alias/family, alias_of, match: exact/prefix, shutdown, replacement, migration, confidence, note, map_automatically}` |
| `signals[]` | call-site and usage detectors `{id, pattern, languages[], sdk}`, e.g. openai/anthropic/LangChain clients, plain HTTP, `max_tokens`, tools |
| `rules[]` | `{id, type, applies_to{replacements, migrations}, when_all, when_any, unless_any, param, new_param, risk, message, confidence, evidence, fix}`. `type` is one of `param_renamed`, `param_removed`, `param_conditional`, `endpoint`, `tool_calling` or `info`. `fix` is a machine-readable hint for the auto-fixer |
| `risk_policy` | `{urgent_days, default_risk}` |
| `replacement_facts{model: {...}}` | capabilities, prices and `eval.model_params` (used by `init-evals`) |
| `facts{confirmed, live_checked_on, live, unconfirmed}`, `report{next_steps, fine_tune_advice}` | text for the client report |

Confidence values: `confirmed` (provider docs), `live-tested` (our own API calls), `inferred` (our reading)
and `example`.

## Hosting

`modelmigrate packs build-site --out site` writes:

```
site/index.html            human landing page
site/v1/index.json         [{provider, version, url, sha256, pack_format}, ...]
site/v1/packs/<p>.json
site/v1/pack.schema.json
site/vercel.json           headers (CORS, cache, content-type) for Vercel
site/_headers              the same for Cloudflare Pages
```

The client fetches `index.json` and only downloads packs newer than its bundled copy. It checks the SHA-256
and the schema, then caches the result for 24 hours in `~/.cache/modelmigrate/packs/`. If anything fails, it
silently keeps the bundled pack.

## Adding a provider

1. Copy `anthropic.json` as a template and set `provider`, `id_patterns`, `signals` and `models`.
2. Run `modelmigrate packs validate path/to/pack.json`.
3. Try it locally with `modelmigrate scan . --pack-file path/to/pack.json`.
4. Drop it in `migration_kit/pack_data/` and rebuild the site.
