# Migration pack format (pack_format 1)

A pack is a JSON file with one provider per pack. The schema is `migration_kit/pack_data/pack.schema.json`,
also hosted as `v1/pack.schema.json`. The scanner, swap mapping, report and auto-fixer are generic
engines. All provider knowledge lives in packs.

| Key | Purpose |
|---|---|
| `provider`, `name`, `version` (`YYYY.MM.DD[.N]`), `updated`, `status` (`stable`/`stub`/`example`) | identity; the highest version wins |
| `sources[]` | `{id, title, url, checked}`. Every fact should point at one |
| `id_patterns[]` | regexes for model-ID tokens (the engine adds token boundaries). `quoted_only` for ambiguous IDs such as `o3` |
| `fine_tune` | `{pattern, base_group, risk, notes, bases[]}`: how to spot a fine-tune and extract its base model. `bases[]` (`{base, match: exact/prefix, shutdown, replacement, section, confidence, source, notes}`) covers fine-tunes whose shutdown differs from, or isn't covered by, the base model entry; its `notes` replace the generic ones |
| `migrations[]` | named retirement events `{id, title, announced, shutdown, replacement, headline}`. `headline` ones drive the report deadline and the default swap mapping |
| `models[]` | `{id, kind: snapshot/alias/family, alias_of, match: exact/prefix, shutdown, replacement, migration, confidence, note, map_automatically}` |
| `signals[]` | call-site and usage detectors `{id, pattern, languages[], sdk, call}`, e.g. openai/anthropic/LangChain clients, plain HTTP, `max_tokens`, tools. `pattern` works at file level (scan). The optional `call` drives the fixer at call level: `callees` (dotted-suffix match, longest wins) marks an endpoint, `params` fires when an argument is passed (`ignore_values` excepted, e.g. `temperature: 1`), and `param_values` fires on literal values (e.g. `reasoning.effort: none`) |
| `rules[]` | `{id, type, applies_to{replacements, migrations}, when_all, when_any, unless_any, param, new_param, risk, message, confidence, evidence, fix}`. `type` is one of `param_renamed`, `param_removed`, `param_conditional`, `endpoint`, `tool_calling` or `info`. `fix` is a machine-readable hint for the auto-fixer |
| `risk_policy` | `{urgent_days, default_risk, shutdown_risk_when_any, otherwise_note}`. `shutdown_risk_when_any` is a list of signal ids: the shutdown date raises risk to high only when the same file has one of them. Otherwise the finding stays at `default_risk` and uses `otherwise_note` instead of the model note. Signals are file-level, so a signal in another file does not count |
| `replacement_facts{model: {...}}` | capabilities, prices and `eval.model_params` (used by `init-evals`) |
| `facts{confirmed, live_checked_on, live, unconfirmed}`, `report{next_steps, fine_tune_advice}` | text for the client report |

Confidence values: `confirmed` (provider docs), `live-tested` (our own API calls), `inferred` (our reading)
and `example`.

## Fix specs (`rules[].fix`)

The fixer evaluates each rule against each API call's own arguments, using the same `when_*`/`unless_any` logic
as the scan but with call-level signals. It then applies the rule's `fix`:

| `action` | Fields | Effect |
|---|---|---|
| `rename_param` | `from`, `to` (a name, or `{endpoint: name}`) | renames the argument; endpoints not listed become manual |
| `remove_param` | `params[]` | removes the listed arguments |
| `set_param` | `param`/`value`, or `per_endpoint: {endpoint: {param, value}}` | adds the argument (a dotted path means a nested key, e.g. `reasoning.effort`); a different existing value is a manual conflict |
| `move_endpoint` | `to` | manual (endpoint migrations aren't automated) |
| `manual` | `note` | manual, with the note as guidance |

Modifiers:

- `requires_new_model: true` means the old models reject the fixed call. The fix is only applied when the
  same patch switches the call to the replacement. If the model comes from an env var, the item is marked
  "ship with the model switch".
- `keep_model: true` means the replacement can't serve this call, so the patch leaves the call on its
  current model.
- Rules with `confidence: inferred` are only suggested unless `--include-inferred` is passed.

## Hosting

`lastorders packs build-site --out site` writes:

```
site/index.html            human landing page
site/v1/index.json         [{provider, version, url, sha256, pack_format}, ...]
site/v1/packs/<p>.json
site/v1/pack.schema.json
site/vercel.json           headers (CORS, cache, content-type) for Vercel
site/_headers              the same for Cloudflare Pages
```

The client fetches `index.json` and only downloads packs newer than its bundled copy. It checks the SHA-256
and the schema, then caches the result for 24 hours in `~/.cache/lastorders/packs/`. If anything fails, it
silently keeps the bundled pack.

## Adding a provider

1. Copy `anthropic.json` as a template and set `provider`, `id_patterns`, `signals` and `models`.
2. Run `lastorders packs validate path/to/pack.json`.
3. Try it locally with `lastorders scan . --pack-file path/to/pack.json`.
4. Drop it in `migration_kit/pack_data/` and rebuild the site.

Clients only download index entries whose `provider` is one they already bundle (see `load_packs`). A new provider in the hosted index is skipped by older installs, including 0.4.0 and 0.4.1, so publishing it does not change their scans.

## Google (Vertex AI)

`google` covers Vertex AI retirements. Facts are from the [model versions](https://cloud.google.com/vertex-ai/generative-ai/docs/learn/model-versions) table (checked 16 Oct 2026). That page lists no `-001`, dated, or preview ID for the three 20 Oct models. The same three stable IDs have no shutdown date on the [Gemini API](https://ai.google.dev/gemini-api/docs/deprecations).

| Model ID | Vertex retirement | Suggested replacement | Also listed |
|---|---|---|---|
| `gemini-2.5-pro` | 2026-10-20 | `gemini-3.8-flash` | `gemini-3.5-flash` |
| `gemini-2.5-flash` | 2026-10-20 | `gemini-3.8-flash` | `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite` |
| `gemini-2.5-flash-lite` | 2026-10-20 | `gemini-3.8-flash` | `gemini-3.1-flash-lite`, Gemma 4 (no model ID on the page) |
| `gemini-live-2.5-flash-native-audio` | 2026-12-13 | none on the page | |
| `gemini-2.5-flash-image` | 2027-03-15 | `gemini-3.1-flash-lite-image` | |

The pack is flag-only: every model has `map_automatically: false` and there are no `rules`, so `swap` and `fix` do not rewrite these IDs.

Risk uses `shutdown_risk_when_any: ["vertex"]`. The `vertex` signal matches, in the same file as the model ID:

- Python `import vertexai` / `from vertexai`, or `google.cloud.aiplatform`
- `genai.Client(vertexai=True)` and the JS `vertexai: true` form
- `GOOGLE_GENAI_USE_VERTEXAI` set to a truthy value
- a host containing `aiplatform.googleapis.com`
- the `@google-cloud/vertexai` package

`@google/genai` on its own is the Gemini API client and does not count. When the file has no `vertex` signal, the finding stays informational and the note is `retires on Vertex AI; not deprecated on the Gemini API`. A Vertex import in a different file does not raise this file: that case is unclear, and unclear stays informational. The shutdown date raises a Vertex finding to high only when it is within 30 days or already past.

## Microsoft Foundry (`azure-foundry`)

Partner models on Microsoft Foundry. Facts are from the [model retirement schedule](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule), "Foundry Models from partners and community" (checked 22 Oct 2026). These dates are Foundry's; the model makers' own APIs set their own.

| Model ID | Foundry retirement | Suggested replacement | Notes |
|---|---|---|---|
| `mistral-small-2503` | 2027-02-15 (was 2026-12-09) | `mistralai-mistral-small-4-119b-2603` | deprecated 9 Oct 2026; Mistral's own API retired it 30 Nov 2025 |
| `Cohere-embed-v3-english`, `Cohere-embed-v3-multilingual` | 2027-02-15 | `Cohere-Embed-V5-Fast` / `-Pro` | rule `foundry-cohere-embed-v3-rebuild-index`: rebuild every vector index |
| `Phi-4`, `Phi-4-mini-instruct`, `Phi-4-mini-reasoning`, `Phi-4-multimodal-instruct`, `Phi-4-reasoning` | 2027-01-17 | `microsoft--phi-4` (Foundry Managed Compute) | |
| `Llama-3.3-70B-Instruct` | none | | partner listing retires 2027-01-31 |
| `Llama-4-Maverick-17B-128E-Instruct-FP8` | none | | partner listing retires 2026-11-19 |

Flag only: no model is swapped. Risk uses `shutdown_risk_when_any: ["azure_foundry"]` (Foundry / Azure AI inference hosts, `azure.ai.inference`, `@azure-rest/ai-inference`, LangChain Azure AI, `AZURE_AI_*` endpoint or key variables). Deployment names on Foundry are chosen by the customer, so a repo may not contain these ids at all.

## Anthropic API version 2026-10-21

`temperature`, `top_p` and `top_k` were removed in API version `2026-10-21` ([API parameter deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations), checked 22 Oct 2026). The signal `anthropic_version_2026_10_21` matches an `anthropic-version` header, env var or config value of 2026-10-21 or later. With it the sampling parameters are an error (`claude-sampling-removed-api-2026-10-21`, high); without it they are a warning (`claude-sampling-api-2026-10-21-warning`, medium), because the SDKs send an older version by default. Both rules are `manual`. The scan only attaches rules to listed (retiring) model ids, so in the free scan these rules show next to retiring Claude ids; `fix` checks every Messages call on an active Claude model.
