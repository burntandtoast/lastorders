# Prospects: OpenAI GPT-4o / GPT-4.1 migration kit

_Compiled 15 Oct 2026. Every entry was checked by fetching the evidence file or page and confirming the model ID is in it. Contacts are only routes the prospect lists publicly (website, GitHub org profile, social). Nothing has been sent._

**Deadlines (OpenAI deprecations page, https://platform.openai.com/docs/deprecations):** `gpt-4.1-nano` and `gpt-4o-2024-05-13` go on **23 Oct 2026**. `gpt-4o-2024-08-06`, `gpt-4o-2024-11-20`, `gpt-4o-mini-2024-07-18`, `gpt-4.1-2025-04-14` and `gpt-4.1-mini-2025-04-14` go on **14 Jan 2027** (replacement: `gpt-6-luna`).

Sorted with the 23 Oct cases first, then UK first.

## 1. UKHSA epiviz (UK (public sector)) — affected by 23 Oct 2026
- Site: https://ukhsa-collaboration.github.io/epiviz/
- Evidence: https://github.com/ukhsa-collaboration/epiviz/blob/2f820bb9313326024659e2f68f7bfed07832e789/README.md
- Why a good fit: UK public-health R package; README tells users to set LLM_MODEL=gpt-4.1-nano. That model goes on 23 Oct 2026. Public sector, so a goodwill PR/issue rather than a sale.
- Public contact route: GitHub issues on ukhsa-collaboration/epiviz

## 2. TheWidlarzGroup (react-native-voice-agent) (Poland) — affected by 23 Oct 2026
- Site: https://www.thewidlarzgroup.com
- Evidence: https://github.com/TheWidlarzGroup/react-native-voice-agent/blob/1618fe3e9592ed82faaaecd6ebf587203f7374dc/src/types/index.ts
- Why a good fit: Kraków RN agency; voice-agent library default config is model: 'gpt-4.1-nano'. Goes on 23 Oct 2026, and client apps built on it inherit the default.
- Public contact route: hi@thewidlarzgroup.com (public GitHub org profile); X @WidlarzGroup

## 3. ProxCenter (Unknown (EU)) — affected by 23 Oct 2026
- Site: https://www.proxcenter.io
- Evidence: https://github.com/adminsyspro/proxcenter-ui/blob/71eb943918578c0fc2e97a1e7da2c972bad9e780/frontend/src/app/api/v1/settings/ai/route.ts
- Why a good fit: Open-source Proxmox management UI (~1.7k stars); default AI setting openaiModel: 'gpt-4.1-nano'. Goes on 23 Oct 2026. Small vendor, actively maintained.
- Public contact route: contact@proxcenter.io (website); X @ProxCenter

## 4. Instructor-PHP / Polyglot (Cognesy) (Poland) — affected by 23 Oct 2026
- Site: https://instructorphp.com
- Evidence: https://github.com/cognesy/instructor-php/blob/70e72d1063ef15183918c33d04330bd0f3f31df1/packages/polyglot/docs/setup.md
- Why a good fit: Warsaw structured-output PHP library; setup docs and presets use gpt-4.1-nano (goes on 23 Oct 2026). Structured outputs are exactly what our regression report checks.
- Public contact route: GitHub issues; X @ddebowczyk (linked from instructorphp.com)

## 5. Memorix (RGLens) (Unknown (Asia)) — affected by 23 Oct 2026
- Site: https://mem.rglens.com
- Evidence: https://github.com/AVIDS2/memorix/blob/af2550290ca6d37c524450b4366277b211aa7402/src/llm/provider.ts
- Why a good fit: Open-source agent memory layer (~840 stars); OpenAI provider default model 'gpt-4.1-nano'. Goes on 23 Oct 2026.
- Public contact route: mail@rglens.com (website); GitHub issues

## 6. Smart Composer (Obsidian plugin) (South Korea) — affected by 23 Oct 2026
- Site: https://github.com/glowingjade/obsidian-smart-composer
- Evidence: https://github.com/glowingjade/obsidian-smart-composer/blob/6b38ab3c57e03c5c6cbeb79815277857df59cbd8/src/settings/schema/migrations/11_to_12.ts
- Why a good fit: Popular Obsidian AI plugin (~2.3k stars); default model list ships 'gpt-4.1-nano' (goes on 23 Oct 2026). Needs a settings migration, not just a string swap.
- Public contact route: GitHub issues; X @andy_suh_

## 7. YOLO (Obsidian plugin) (Unknown) — affected by 23 Oct 2026
- Site: https://github.com/Lapis0x0/obsidian-yolo
- Evidence: https://github.com/Lapis0x0/obsidian-yolo/blob/c499c63f2638ab6fe639d0714f106de5c71ba983/src/constants.ts
- Why a good fit: Obsidian AI assistant (~1.4k stars); constants ship 'gpt-4.1-nano' as a built-in model (goes on 23 Oct 2026).
- Public contact route: GitHub issues

## 8. Payload AI Localization plugin (Unknown) — affected by 23 Oct 2026
- Site: https://github.com/Crayonan/payload-plugin-ai-localization
- Evidence: https://github.com/Crayonan/payload-plugin-ai-localization/blob/12eb25854ebe0606af421e265f7d112026344e8c/dev/payload.config.ts
- Why a good fit: Payload CMS translation plugin; example config uses model 'gpt-4.1-nano' (goes on 23 Oct 2026). Agencies copying the example are affected too.
- Public contact route: GitHub issues

## 9. Caramel Web Studios (UK (London)) — affected by 14 Jan 2027
- Site: https://www.caramelwebstudios.com
- Evidence: https://github.com/Caramel-Web-Studios/mandmaccountants/blob/1e7dcac71934bb9a0c37b1a448f7d71d481a5a7d/app/api/chat/route.ts
- Why a good fit: London web studio selling AI chatbots to accountancy firms; client chatbot route pins model "gpt-4o-mini". Likely the same pattern across several client sites, so one migration method serves many.
- Public contact route: info@caramelwebstudios.com (listed on their website and GitHub profile)

## 10. Yug Solutions (ContractorIQ) (UK (Eastbourne)) — affected by 14 Jan 2027
- Site: https://www.yugsolutions.co.uk/
- Evidence: https://github.com/Virendra-Vyas/contractoriq/blob/5b969d1e8ae054ccec2fd6d997d30bc7db07545d/ContractorIQ.API/Services/Ir35ScreenerService.cs
- Why a good fit: Eastbourne solo founder; ContractorIQ IR35 screener and CV tailoring services call model = "gpt-4o" (C#/.NET). Structured analysis output, so a regression check matters.
- Public contact route: hello@yugsolutions.co.uk (website); LinkedIn company page linkedin.com/company/yug-solutions

## 11. Scott Logic (UK (Newcastle)) — affected by 14 Jan 2027
- Site: https://www.scottlogic.com
- Evidence: https://github.com/ScottLogic/prompt-injection/blob/501e4be0e6e2e7ebfcaad558009589f31f61fa6b/backend/src/models/chat.ts
- Why a good fit: Newcastle-founded consultancy; open-source prompt-injection app lists 'gpt-4o' in its model table, and its blog/demos reference GPT-4o. Bigger than us, so pitch as subcontract capacity or for the OSS repo.
- Public contact route: Contact form https://www.scottlogic.com/contact-us ; LinkedIn company page

## 12. Fuzzy Labs (UK (Manchester)) — affected by 14 Jan 2027
- Site: https://fuzzylabs.ai
- Evidence: https://github.com/fuzzylabs/awesome-mlops-recipes/blob/0111df02c7c4784597f09094e5f81d33f90aec81/rag_stack/evals/ragas/run.py
- Why a good fit: Manchester MLOps consultancy; RAG eval recipe defaults to "gpt-4o-mini". Peer firm: possible partner/referral rather than a straight client.
- Public contact route: talk@fuzzylabs.ai (public GitHub org profile); X @fuzzylabsai

## 13. mySociety (UK) — affected by 14 Jan 2027
- Site: https://www.mysociety.org
- Evidence: https://github.com/mysociety/appg-membership/blob/a4cd857e040d1fb0f990eb42f3838047dab8010d/src/appg_membership/classify_appg_agent.py
- Why a good fit: UK civic-tech charity; APPG classification agent pins "gpt-4o" via pydantic-ai (structured output). Small team, open code, easy to show a before/after.
- Public contact route: hello@mysociety.org (website contact page) / https://www.mysociety.org/contact/

## 14. The Open Data Institute (UK (London)) — affected by 14 Jan 2027
- Site: https://theodi.org
- Evidence: https://github.com/theodi/national-volunteer-services-demo/blob/c0fb3665f930e5c32933298d649f17c902e9e3d6/app/api/chat/route.ts
- Why a good fit: London non-profit; demo app calls model "gpt-4o" four times, and care.theodi.org defaults to 'gpt-4o-mini'. Several small repos with the same pattern.
- Public contact route: Contact page https://theodi.org/contact-us/ ; X @ODIHQ

## 15. Global Witness (Augmenta) (UK (London)) — affected by 14 Jan 2027
- Site: https://globalwitness.org
- Evidence: https://github.com/Global-Witness/augmenta/blob/69391cba319d79aaaf51fb4786019290531d11fd/README.md
- Why a good fit: London NGO; open-source Augmenta research tool's example config uses gpt-4o-mini. Its outputs feed investigations, so regression evidence is valuable.
- Public contact route: data@globalwitness.org (public GitHub org profile); LinkedIn company page

## 16. PFD Toolkit (Sam Osian) (UK (Liverpool)) — affected by 14 Jan 2027
- Site: https://pfdtoolkit.org
- Evidence: https://github.com/Sam-Osian/PFD-toolkit/blob/16dd75b86f6e78f1274411a3ccb7abe200bc69f9/tutorials/ons_research.ipynb
- Why a good fit: Liverpool-based open-source toolkit for Prevention of Future Deaths reports; tutorials pin "gpt-4.1-mini" and "gpt-4.1". Research users need consistent outputs across the switch.
- Public contact route: Contact page https://pfdtoolkit.org/contact/ ; GitHub issues

## 17. Karakeep (UK) — affected by 14 Jan 2027
- Site: https://karakeep.app
- Evidence: https://github.com/karakeep-app/karakeep/blob/b783cf6d155d36e8e821e454b83499ed766228af/docs/docs/03-configuration/02-different-ai-providers.md
- Why a good fit: UK-registered self-hosted bookmark app (~29.7k stars); docs give INFERENCE_TEXT_MODEL=gpt-4.1-mini and INFERENCE_IMAGE_MODEL=gpt-4o-mini for AI tagging. Docs/defaults update plus a tagging regression set.
- Public contact route: info@karakeep.app (public GitHub org profile); GitHub issues

## 18. Trigger.dev (UK) — affected by 14 Jan 2027
- Site: https://trigger.dev
- Evidence: https://github.com/triggerdotdev/trigger.dev/blob/d2ed5c0f857e6f5802d570a20c97c108f65ede42/apps/webapp/app/v3/services/aiQueryTitleService.server.ts
- Why a good fit: UK-registered dev-tools startup; webapp service defaults to openai("gpt-4o-mini") and docs examples use gpt-4o. Probably has its own engineers, so a light-touch offer.
- Public contact route: hello@trigger.dev (public GitHub org profile); https://trigger.dev/contact

## 19. Budibase (UK (Belfast)) — affected by 14 Jan 2027
- Site: https://budibase.com
- Evidence: https://github.com/Budibase/budibase/blob/d84fcc090ec7d4890ccc9f15e48867dd60e78bbd/packages/shared-core/src/automations/steps/openai.ts
- Why a good fit: Belfast low-code platform; the OpenAI automation step lists GPT_4O and GPT_4O_MINI options. Their users' saved automations may hard-code those values: a migration-path concern.
- Public contact route: https://budibase.com/contact/ ; LinkedIn company page

## 20. ETechProvider UK (UK) — affected by 14 Jan 2027 (assumed)
- Site: https://etechprovider.co.uk
- Evidence: https://etechprovider.co.uk/services.html
- Why a good fit: UK web/SEO agency; services page offers 'OpenAI GPT-4o & Google Gemini Pro custom workflow pipelines' for clients. Marketing claim only, so no code seen.
- Public contact route: Contact form https://etechprovider.co.uk/contact.html ; LinkedIn company page; X @etechprovider

## 21. i.AI ThemeFinder (UK (public sector)) — affected by 14 Jan 2027
- Site: https://github.com/i-dot-ai/themefinder
- Evidence: https://github.com/i-dot-ai/themefinder/blob/09918eb213e022677fbfe04cbb3d6443f8607d2c/src/themefinder/llm_batch_processor.py
- Why a good fit: UK government AI incubator's open-source consultation-analysis library; defaults to MODEL_NAME 'gpt-4o'. Procurement rules apply; best treated as a credibility/open-source contribution.
- Public contact route: GitHub issues on i-dot-ai/themefinder

## 22. Paperless-AI (Unknown (EU)) — affected by 14 Jan 2027
- Site: https://clusterzx.github.io/paperless-ai/
- Evidence: https://github.com/clusterzx/paperless-ai/blob/d2fda6991e5e55d51d6473997176bb8d054f61fd/services/setupService.js
- Why a good fit: Self-hosted document tagger (~6k stars); setup validation calls model "gpt-4o-mini". Structured tag/metadata output, so a good fit for a regression report.
- Public contact route: GitHub issues

## Caveats
- Most evidence is an **undated alias** (`gpt-4o`, `gpt-4o-mini`, `gpt-4.1-mini`) rather than a dated snapshot. The deprecations table lists dated snapshots for 14 Jan 2027, and the plain `gpt-4.1-nano` alias is listed explicitly for 23 Oct 2026. Before quoting a date to a prospect, confirm which snapshot their alias points to (use `GET /v1/models` and its `shutdown_date`).
- The code is public, but a prospect may already have migrated in a private branch or production config. Treat this as a lead, not a diagnosis.
- Several are open-source projects or public-sector or charity teams (UKHSA, i.AI, mySociety, ODI, Global Witness). They are better approached with a helpful issue or PR than a sales pitch, and public-sector work brings procurement rules.
- Scott Logic, Fuzzy Labs, Trigger.dev and Budibase have their own engineers. Pitch partnership or overflow capacity there, not rescue.
- ETechProvider's evidence is a services-page claim, not code.
- Not included: projects that only use Azure OpenAI deployments (e.g. Lightdash's GPT-4.1 path, Big Indexer's eval). Azure runs its own retirement schedule, which the OpenAI page doesn't cover.