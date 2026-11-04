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
| `models[]` | `{id, kind: snapshot/alias/family, alias_of, match: exact/prefix, shutdown, replacement, migration, confidence, note, past_note, map_automatically, platforms[]}`. `platforms[]` is `{when_any, shutdown, replacement, migration, note, past_note, source, map_automatically}`. The first entry whose `when_any` hits the file's signals wins. An entry with no `when_any` is the schedule when none match, and that date raises risk on its own. `past_note` replaces the default "calls are likely failing" sentence after the date |
| `signals[]` | call-site and usage detectors `{id, pattern, languages[], sdk, call}`, e.g. openai/anthropic/LangChain clients, plain HTTP, `max_tokens`, tools. `pattern` works at file level (scan). The optional `call` drives the fixer at call level: `callees` (dotted-suffix match, longest wins) marks an endpoint, `params` fires when an argument is passed (`ignore_values` excepted, e.g. `temperature: 1`), and `param_values` fires on literal values (e.g. `reasoning.effort: none`) |
| `rules[]` | `{id, type, applies_to{replacements, migrations} (omit for a model-independent rule, reported per file), when_all, when_any, unless_any, param, new_param, risk, message, confidence, evidence, fix}`. `type` is one of `param_renamed`, `param_removed`, `param_conditional`, `endpoint`, `tool_calling` or `info`. `fix` is a machine-readable hint for the auto-fixer |
| `risk_policy` | `{urgent_days, default_risk, shutdown_risk_when_any, otherwise_note}`. `shutdown_risk_when_any` is a list of signal ids: for a row with no `platforms` schedule, the shutdown date raises risk to high only when the same file has one of them. Otherwise the finding stays at `default_risk` and uses `otherwise_note` instead of the model note. A `platforms` schedule replaces that gate for that model. Signals are file-level, so a signal in another file does not count |
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

## Google (Vertex AI and the Gemini API)

`google` covers Vertex AI retirements and the Gemini API auto-routes for the same stable IDs. Vertex facts are from the [model versions](https://cloud.google.com/vertex-ai/generative-ai/docs/learn/model-versions) table (checked 16 Oct 2026). That page lists no `-001`, dated, or preview ID for the three 20 Oct models. Gemini API facts are from [Gemini API deprecations](https://ai.google.dev/gemini-api/docs/deprecations) (checked 4 Nov 2026).

| Model ID | Vertex retirement | Vertex replacement | Gemini API |
|---|---|---|---|
| `gemini-2.5-pro` | 2026-10-20 | `gemini-3.8-flash` (also `gemini-3.5-flash`) | 2026-12-01, auto-routes to `gemini-3.8-flash` |
| `gemini-2.5-flash` | 2026-10-20 | `gemini-3.8-flash` (also `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`) | 2026-12-01, auto-routes to `gemini-3.5-flash-lite` |
| `gemini-2.5-flash-lite` | 2026-10-20 | `gemini-3.8-flash` (also `gemini-3.1-flash-lite`, Gemma 4 with no model ID on the page) | no shutdown date |
| `gemini-live-2.5-flash-native-audio` | 2026-12-13 | none on the page | not a row on the Gemini API page |
| `gemini-2.5-flash-image` | 2027-03-15 | `gemini-3.1-flash-lite-image` | same date and replacement |

The pack is flag-only: every model and every `platforms` entry has `map_automatically: false`, and there are no `rules`, so `swap` and `fix` do not rewrite these IDs. Pro and Flash each have two schedules on the same ID. The `vertex` entry wins when the file has that signal. The entry with no `when_any` is the Gemini API schedule.

Risk uses `shutdown_risk_when_any: ["vertex"]` for rows without `platforms` (Flash-Lite and the live model). The `vertex` signal matches, in the same file as the model ID:

- Python `import vertexai` / `from vertexai`, or `google.cloud.aiplatform`
- `genai.Client(vertexai=True)` and the JS `vertexai: true` form
- `GOOGLE_GENAI_USE_VERTEXAI` set to a truthy value
- a host containing `aiplatform.googleapis.com`
- the `@google-cloud/vertexai` package

`@google/genai` on its own is the Gemini API client and does not count. A Vertex import in a different file does not raise this file. For Flash-Lite and the live model, a file with no `vertex` signal stays informational and the note is `retires on Vertex AI; not deprecated on the Gemini API`. For Pro and Flash, that file uses the 1 Dec 2026 Gemini API schedule instead, and that date raises risk when it is within 30 days or already past. After 1 Dec the note says the API automatically routes the ID. It does not say the call is failing. The Vertex date raises a Vertex finding to high only when it is within 30 days or already past.

## Microsoft Foundry (`azure-foundry`)

Partner models on Microsoft Foundry. Facts are from the [model retirement schedule](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule), "Foundry Models from partners and community" (checked 22 Oct 2026). These dates are Foundry's; the model makers' own APIs set their own.

| Model ID | Foundry retirement | Suggested replacement | Notes |
|---|---|---|---|
| `mistral-small-2503` | 2027-02-15 (was 2026-12-09) | `mistralai-mistral-small-4-119b-2603` | deprecated 9 Oct 2026; Mistral's own API retired it 30 Nov 2025 |
| `Cohere-embed-v3-english`, `Cohere-embed-v3-multilingual` | 2027-02-15 | `Cohere-Embed-V5-Fast` / `-Pro` | rule `foundry-cohere-embed-v3-rebuild-index`: rebuild every vector index |
| `Phi-4`, `Phi-4-mini-instruct`, `Phi-4-mini-reasoning`, `Phi-4-multimodal-instruct`, `Phi-4-reasoning` | 2027-01-17 | `microsoft--phi-4` (Foundry Managed Compute) | |
| `Llama-3.3-70B-Instruct` | none | | partner listing retires 2027-01-31 |
| `Llama-4-Maverick-17B-128E-Instruct-FP8` | none | | partner listing retires 2026-11-19 |

Flag only: no model is swapped. Risk uses `shutdown_risk_when_any: ["azure_foundry"]` (Foundry / Azure AI inference hosts, `azure.ai.inference`, `@azure-rest/ai-inference`, LangChain Azure AI, `AZURE_AI_*` / `AZURE_OPENAI_*` variables, `AzureOpenAI`, `azure_endpoint`). Deployment names on Foundry are chosen by the customer, so a repo may not contain these ids at all.

### Azure OpenAI (same pack, checked 2 Nov 2026)

Rows under "Foundry Models sold by Azure > Azure OpenAI" on the [model retirement schedule](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule). They are not copied onto the OpenAI platform pack. A file is assessed on this schedule only when it has the `azure_foundry` signal; otherwise the OpenAI pack keeps the snapshot.

| Model ID | Azure retirement | Suggested replacement | Notes |
|---|---|---|---|
| `gpt-4o-2024-05-13` | 2027-01-14 (was 9 December 2026) | `gpt-5.1` version `2025-11-13` | Rule `azure-gpt-4o-20240513-provisioned`: Global Standard and Data Zone Standard deployments upgrade automatically; Provisioned deployments do not |
| `gpt-4.1-mini-2025-04-14` | 2027-04-14 | none listed | footnote 3 |
| `gpt-5-mini-2025-08-07` | 2027-07-13 (was 9 February 2027) | none listed | |
| `gpt-5.1-2025-11-13` | 2027-07-13 (was 15 May 2027) | none listed | target of the gpt-4o 2024-05-13 automatic upgrade |

## Mistral API (`mistral`)

Mistral's own API, from the [models overview](https://docs.mistral.ai/models) (checked 2 Nov 2026). These dates are not Microsoft Foundry's. `mistral-small-2503` stays in the `azure-foundry` pack. Third-party models Mistral hosts (DeepSeek, Z.ai, and others) are not rows here.

Flag only: every row has `map_automatically: false`, so `swap` and `fix` do not rewrite the IDs. The replacement is not a name-only change.

| Model ID | Mistral retirement | Suggested replacement | Notes |
|---|---|---|---|
| `mistral-medium-3-5` | 2027-04-30 (deprecated 2026-10-31) | `mistral-large-4` | Medium 3.5. $1.50 / $7.50 per 1M tokens. Accepts `reasoning_effort` `none`. Large 4 does not |
| `mistral-large-2512` | 2027-04-30 (deprecated 2026-10-31) | `mistral-large-4` | Large 3. $0.50 / $1.50 per 1M tokens, text output. Large 4 costs more and returns reasoning |
| `voxtral-mini-2602` | 2027-04-30 (deprecated 2026-10-31) | `voxtral-mini-transcribe-3-0` | $0.003 to $0.0035 per minute. Rule `voxtral-word-timestamps-removed`: `word` timestamps return 400 |
| `voxtral-mini-transcribe-realtime-2602` | 2027-04-30 (deprecated 2026-10-31) | `voxtral-mini-transcribe-realtime-3-0` | $0.006 to $0.008 per minute. Rule `voxtral-realtime-session-lock` |
| `voxtral-mini-tts-2603` | 2027-04-30 (deprecated 2026-10-31) | `voxtral-mini-tts-3-0` | $16 to $13 per million characters. Do not pin `voxtral-mini-tts-latest` |

Large 4's API name on the models overview and the [pricing page](https://docs.mistral.ai/inference/pricing) is `mistral-large-4` ($0.70 input, $0.07 cached input, $2.10 output per 1M tokens, public preview, 1M context). The [model card](https://docs.mistral.ai/models/mistral-large-4-0) also accepts `mistral-large-4-0`. Audio prices are per minute or per million characters, so `price_usd_per_1m` is null. Rule `mistral-large-4-reasoning-effort` fires when the same file sets `reasoning_effort` to `none`, `minimal`, `xhigh`, or `max`. All three rules are `manual`.

`voxtral-small-2507` is still GA on the models overview. The Voxtral 2 migration page maps it anyway; this pack leaves it out.

## Moonshot API (`moonshot`)

Moonshot's own Kimi API (`https://api.moonshot.ai/v1`, env `MOONSHOT_API_KEY`), from the [model list](https://platform.kimi.ai/docs/models) (checked 2 Nov 2026). Model IDs stay the `kimi-*` strings. Flag only: every row has `map_automatically: false`, so `swap` and `fix` do not rewrite the IDs.

New sign-ups have been blocked from the K2 series since 31 Oct 2026. Moonshot says it will retire all K2 series models by the end of December 2026 and has not published a day. This pack uses 31 Dec 2026 until it does.

| Model ID | Moonshot retirement | Suggested replacement | Notes |
|---|---|---|---|
| `kimi-k2.6` | 2026-12-31 (new sign-ups blocked 2026-10-31) | `kimi-k3.1-pro` | 256k / 262,144 tokens, $0.95 / $0.16 cached / $4.00 per 1M. Thinking can be disabled. `kimi-k2.6-highspeed` is not listed |
| `kimi-k2.7-code` | 2026-12-31 (new sign-ups blocked 2026-10-31) | `kimi-k3.1-pro` | 256k / 262,144 tokens, $0.95 / $0.19 cached / $4.00 per 1M. Thinking is already always on |
| `kimi-k2.7-code-highspeed` | 2026-12-31 (new sign-ups blocked 2026-10-31) | `kimi-k3.1-pro` | Same model as K2.7 Code per the parameter reference, own id and price ($1.90 / $0.38 / $8.00). A separate row so the scan matches the suffix |

K3.1 Pro on the [quickstart](https://platform.kimi.ai/docs/guide/kimi-k3-1-pro-quickstart.md) and the [pricing page](https://platform.kimi.ai/docs/pricing/chat.md): 1,048,576 tokens, $2.00 input / $0.20 cached input / $10.00 output per 1M tokens, plus cache writes at $2.00 (5-minute TTL) and $4.00 (1-hour TTL). Thinking is always on. `reasoning_effort` is `low`, `high`, or `max`, and the default is `max`. `temperature`, `top_p`, `n`, `presence_penalty`, and `frequency_penalty` are fixed; omit them. Vision does not accept a public image URL; use base64 or an `ms://` file id, and `content` must be an array of objects. `kimi-k3.1-pro-highspeed` is a separate, more expensive id with the same parameter constraints. It is not the pinned replacement.

Rules, all `manual`: `kimi-k3-thinking-always-on`, `kimi-k3-sampling-fixed`, `kimi-k3-vision-no-public-url`, `kimi-k3-reasoning-effort` (fires on `none`, `minimal`, `medium`, or `xhigh`).

Parked for a follow-up, not rows: `kimi-k2.5`, the `moonshot-v1` series, the older `kimi-k2` preview / thinking / turbo ids, `kimi-latest`, and `kimi-thinking-preview`. `kimi-k3` is current and is not a row.

## Anthropic API version 2026-10-21

`temperature`, `top_p` and `top_k` were removed in API version `2026-10-21` ([API parameter deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations), checked 22 Oct 2026). The signal `anthropic_version_2026_10_21` matches an `anthropic-version` header, env var or config value of 2026-10-21 or later. With it the sampling parameters are an error (`claude-sampling-removed-api-2026-10-21`, high); without it they are a warning (`claude-sampling-api-2026-10-21-warning`, medium), because the SDKs send an older version by default. Both rules are `manual`, and so is `claude-sampling-deprecated` (never applied, also with `--include-inferred`). They have no `applies_to`, which makes them model-independent: the scan reports them once per file in Anthropic code (category `param_rule`) unless a retiring-model finding in that file already carries them, and `fix` checks every Messages call. In a file that also names another provider's model, those parameters are checked on the call that holds the model id, not across the whole file, so a `temperature` on an OpenAI call does not flag a Claude call. Installs up to 0.4.11 only show them next to retiring Claude ids in the scan, and as a warning in the fix plan when the version is set on the client.
