# Licence server and Stripe

`server/` is a small Cloudflare Worker that sells, issues and checks licences, and also serves the
pack site (`site/`). It has been built and tested locally only. **Nothing is deployed, and there are no
Stripe, Resend or Cloudflare credentials anywhere in the repo.**

```
buyer ──/buy──▶ Worker ──▶ Stripe Checkout (£149, test mode) ──▶ /success shows the key
                  ▲                         │
                  │      checkout.session.completed (signed webhook)
                  │                         ▼
                  │            Worker: issue BTM-XXXX-XXXX-XXXX, store in D1, email via Resend
                  │
CLI ──POST /api/licence/verify {key, repo}──▶ bind repo on first use ──▶ 7-day Ed25519-signed token
```

## Why Cloudflare Workers (not Vercel)

- **Storage is built in.** D1 (SQLite) is bound to the Worker; the licence table needs no extra vendor.
  On Vercel we'd add Neon, Upstash or similar: another account, more keys and another bill.
- **One deploy for both jobs.** The pack site is served as static assets by the same Worker, so
  `packs.burntandtoast.com/v1/...` and `/api/licence/verify` share one domain, one deploy and one log.
- **Web-standard runtime.** WebCrypto has Ed25519 and HMAC built in, so there are no crypto libraries.
  Stripe is called with `fetch` (no SDK), which keeps the bundle around 30 KB and makes it easy to mock.
- **Cheap and fast.** The free plan covers launch volumes (check current Cloudflare pricing). Verify
  requests are a handful per customer per week. There are no cold starts that matter for a CLI.
- **Portable.** The code is plain `fetch(request, env)`. Moving to Vercel later means swapping the D1 calls in
  `src/store.js` for a Postgres client.

## What's built

| Route | What it does |
|---|---|
| `GET /buy?repo=&email=` | Creates a Checkout Session and redirects (303) to Stripe. `repo` is only a hint stored in metadata. |
| `POST /api/checkout` | The same, returning `{id, url}` as JSON (for a button on the landing page). |
| `POST /api/stripe/webhook` | Checks the `Stripe-Signature` (v1 HMAC-SHA256 over `t.rawBody`, 5-minute tolerance, constant-time compare, two secrets allowed while rolling). Idempotent per event id and per Checkout Session. |
| `GET /success?session_id=` | Shows the key. If the webhook hasn't arrived yet, it fetches the session from Stripe and issues the key itself (same row, no duplicates). The webhook is what sends the email. |
| `GET /cancel` | "No payment was taken" page. |
| `POST /api/licence/verify` | `{key, repo}`. Binds the repo on first use (atomic `UPDATE … WHERE repo IS NULL`) and returns a signed token. Errors: `not_found` 404, `revoked` 403, `bound_to_other_repo` 403, `invalid` 400. |
| `GET /api/licence/public-key` | The current Ed25519 public key (informational; the CLI uses keys built into it). |
| `/api/admin/licences/:key` (`GET`), `…/revoke`, `…/rebind`, `…/resend-email` (`POST`) | Support tools, behind `Authorization: Bearer $ADMIN_TOKEN`. |
| `GET /healthz` | `{ok, stripe_mode}` |
| everything else | Static pack site from `../site` (`vercel.json` is excluded via `.assetsignore`). |

**Webhook events handled:**
- `checkout.session.completed`: issues the key if `payment_status` is `paid`. Otherwise it waits.
- `checkout.session.async_payment_succeeded`: issues the key for delayed payment methods.
- `checkout.session.async_payment_failed`: logged.
- `charge.refunded`: a **full** refund revokes the licence. Partial refunds don't.

Sessions from other products on the same Stripe account are ignored (`metadata.product` must be `modelmigrate-repo`).
If the email fails, the webhook returns 500, so Stripe retries, for up to 3 days. The retry sends the email
without creating a second key. Resend also gets an idempotency key, so a duplicate email isn't possible.

**Licence keys** are `BTM-XXXX-XXXX-XXXX`, using 32 symbols (A–Z without I/O, plus 2–9), which gives
60 random bits. They're stored with the buyer's email, the Stripe session, payment intent and customer ids,
the amount, test/live mode, email status and the bound repo. There's an audit table (`licence_events`).

**Tokens** take the form `v1.<payload>.<Ed25519 signature>`. The payload is
`{v, kid, iss, lic: sha256(key)[:32], repo, plan, features, test, iat, exp}`. The raw key isn't in the token.

**Email** is pluggable via `EMAIL_PROVIDER`:
- `resend` posts to `api.resend.com/emails`;
- `log` writes to the Worker log, for development;
- `none` sends nothing.

Adding a provider means implementing `send(msg)` in `src/email.js`.

### CLI side (`migration_kit/licence.py`)

- The only request it makes is `POST {key, repo}` to `https://packs.burntandtoast.com/api/licence/verify`.
  Override it with `MODELMIGRATE_LICENCE_URL`.
- The token is checked against `PUBLIC_KEYS` built into the CLI and cached in `~/.cache/modelmigrate/licence/`.
- No request is made while the cached token is less than a day old. After that it re-checks when online.
- If the server can't be reached, the token works until it expires (7 days), then for a **14-day grace period**.
- `--offline` / `MODELMIGRATE_OFFLINE=1` never contacts the server. It accepts a cached token, plus the grace period.
- `scan` never touches licensing.
- "Unknown", "revoked" and "bound to another repo" clear the cache immediately.
- Repo identity comes from `GITHUB_REPOSITORY`, then the git `origin` remote, then `MODELMIGRATE_REPO`.
- `modelmigrate licence status|buy|forget`.

### Tests

- `cd server && npm test` runs 16 tests, using sql.js as D1 and fake Stripe and Resend. They cover:
  - signature edge cases;
  - checkout params, including amount, currency, price id and promo codes;
  - idempotency and duplicate events;
  - async payments;
  - an email-failure retry;
  - first-activation binding and other-repo rejection;
  - refunds;
  - the success page racing the webhook;
  - admin;
  - static fall-through.
- `pytest` has 18 licence tests, including an **end-to-end** run:
  - the real Worker in Node, with a signed webhook issuing a key;
  - the CLI verifying it over HTTP;
  - the key binding to the repo, and the token being cached;
  - a second repo being refused.

  The end-to-end test is skipped if Node 20+ or `server/node_modules` is missing.
- Also checked by hand under `wrangler dev` (workerd and local D1): webhook → key → verify → bound → `--offline` from cache.
- `npm run check` runs `wrangler deploy --dry-run`, which builds the bundle without deploying.

## What Leigh needs to supply

### Stripe (start in test mode)

| What | Where | Goes into |
|---|---|---|
| **Test secret key** `sk_test_…`. A restricted key `rk_test_…` is better, with **Checkout Sessions: Write** (that covers create and retrieve) and nothing else. | Dashboard → Developers → API keys (test mode toggle on, or a Sandbox) | `wrangler secret put STRIPE_SECRET_KEY` |
| **Webhook signing secret** `whsec_…` | Dashboard → Developers → Webhooks (Workbench → Event destinations) → Add endpoint, as below | `wrangler secret put STRIPE_WEBHOOK_SECRET` |
| (optional) **Price ID** `price_…` | Product catalogue → "ModelMigrate licence: one repository", one-off £149 | `STRIPE_PRICE_ID` in `wrangler.toml` (otherwise the Worker uses inline `price_data` from `PRICE_AMOUNT`/`CURRENCY`) |

**Webhook endpoint settings:**
- URL: `https://packs.burntandtoast.com/api/stripe/webhook`, or the `*.workers.dev` URL until DNS is ready.
- Events: `checkout.session.completed`, `checkout.session.async_payment_succeeded`,
  `checkout.session.async_payment_failed`, `charge.refunded`.
- Payload style: snapshot (the default). The API version can stay as the account default; the Worker only reads stable fields.
- For local testing, the Stripe CLI prints a **different** `whsec_` for `stripe listen`. Use that one in `.dev.vars`, not the Dashboard one.

**Stripe account settings worth checking:**
- Business name and logo (shown on Checkout).
- Customer emails → "Successful payments" on (Stripe's receipt).
- Statement descriptor.
- UK VAT: if registered, set up Stripe Tax and set `STRIPE_AUTOMATIC_TAX = "true"`.
- `STRIPE_INVOICE_CREATION = "true"` emails a proper invoice, which agencies' clients often want.

### Resend

- Verify the sending domain (`burntandtoast.com`, or a subdomain such as `mail.burntandtoast.com`) by adding the DKIM/SPF records Resend gives you.
- Create an API key with **Sending access**, restricted to that domain. Then run `wrangler secret put RESEND_API_KEY`, and set `EMAIL_PROVIDER = "resend"`.
- Set `EMAIL_FROM` to an address on the verified domain (default `ModelMigrate <licences@burntandtoast.com>`).
- Optionally set `EMAIL_REPLY_TO` / `SUPPORT_EMAIL` to the inbox that handles repo moves.

### Cloudflare

- An account with `burntandtoast.com` as a zone, which is needed for the custom domain. Without it, the
  `*.workers.dev` URL works and `brand.SERVICE_URL` can point there temporarily.
- `npx wrangler login` on the machine you deploy from.

### Two things only Leigh should generate

1. **Licence signing key:** `cd server && npm run keys`.
   - Store the printed JSON line with `wrangler secret put LICENCE_SIGNING_KEY`.
   - Paste the printed public entry into `PUBLIC_KEYS` in `migration_kit/licence.py`, then commit and release the CLI.
   - Until that's done, released CLIs can't verify any token. They fail with "this build has no licence public key embedded".
2. **Admin token:** `openssl rand -base64 32`, then `wrangler secret put ADMIN_TOKEN`.

## Deploy steps (when you're ready; none of this has been run)

```bash
cd server
npm ci
npx wrangler login
npx wrangler d1 create modelmigrate-licences        # paste database_id into wrangler.toml
npm run db:migrate:remote                           # creates the tables
npm run keys                                        # see above: secret + PUBLIC_KEYS
npx wrangler secret put LICENCE_SIGNING_KEY
npx wrangler secret put STRIPE_SECRET_KEY           # sk_test_ / rk_test_ first
npx wrangler secret put STRIPE_WEBHOOK_SECRET       # whsec_ from the Dashboard endpoint
npx wrangler secret put RESEND_API_KEY
npx wrangler secret put ADMIN_TOKEN
# wrangler.toml: EMAIL_PROVIDER="resend", PUBLIC_BASE_URL="https://packs.burntandtoast.com",
#                uncomment the routes line for the custom domain
cd .. && modelmigrate packs build-site --out site && cd server   # refresh the pack site
npm test && npm run check
npx wrangler deploy
```

**Then:**

1. `curl https://packs.burntandtoast.com/healthz` returns `{"ok":true,"stripe_mode":"test"}`.
   `curl …/v1/index.json` returns the packs.
2. Open `https://packs.burntandtoast.com/buy?repo=github.com/you/test-repo` and pay with `4242 4242 4242 4242`
   (any future date, any CVC). The success page should show a key and the email should arrive.
3. `MODELMIGRATE_LICENCE=<key> modelmigrate licence status` in that repo should say "verified online".
   In another repo it should say "bound to …".
4. Refund in the Dashboard. The next `licence status` after the cached token's daily refresh says "revoked".
   Use `licence forget` to check straight away.
5. Point the landing page's buy button at `/buy` (or `POST /api/checkout`). That's the other agent's file, so it's left alone here.

**Local trial without any accounts:** `cd server && node scripts/local-server.mjs`. It prints a URL, a dev
public key and a test-issued key. Point the CLI at it with:
- `MODELMIGRATE_LICENCE_URL=<url>/api/licence/verify`;
- `MODELMIGRATE_LICENCE_DEV_PUBLIC_KEYS='{"dev":"<x>"}'`, which is honoured only for localhost URLs.

**Local trial with real Stripe test mode:**
1. Copy `.dev.vars.example` to `.dev.vars`.
2. Run `npm run db:migrate:local`, then `npm run dev`.
3. Run `stripe listen --forward-to localhost:8787/api/stripe/webhook`.
4. Open `http://localhost:8787/buy`.

`stripe trigger checkout.session.completed --add checkout_session:metadata.product=modelmigrate-repo` also works
(without the metadata, the event is ignored as "not this product").

## Going live

1. In Stripe live mode, create the same webhook endpoint. It gets a **new** `whsec_`.
2. `wrangler secret put STRIPE_SECRET_KEY` (`sk_live_` / `rk_live_`) and `STRIPE_WEBHOOK_SECRET` (the live `whsec_`).
3. Optional: remove test licences with
   `npx wrangler d1 execute modelmigrate-licences --remote --command "UPDATE licences SET status='revoked', revoke_reason='test mode' WHERE livemode = 0"`.
4. `/healthz` should report `"stripe_mode":"live"`. Do one real purchase and refund it.

## Operations

- **Move a licence to another repo:**
  `curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -d '{"repo":"github.com/owner/new"}' https://…/api/admin/licences/BTM-…/rebind`.
  Use `{"repo":null}` to unbind, so the next use binds.
- **Revoke** (for example after a chargeback): `…/revoke` with `{"reason":"chargeback"}`. Disputes aren't automatic.
- **Resend the email:** `…/resend-email`.
- **Roll the webhook secret:** Stripe keeps the old one valid for up to 24 hours.
  Set `STRIPE_WEBHOOK_SECRET="whsec_new,whsec_old"`, then drop the old one.
- **Rotate the signing key:**
  1. Generate a new kid.
  2. Release a CLI containing **both** public keys.
  3. Switch the Worker secret.
  4. Remove the old key from the CLI a release later.
- **Optional:** a Cloudflare WAF rate-limit rule on `/api/licence/verify` (for example 30 requests per minute per IP).
  Keys have 60 random bits, so guessing isn't practical anyway.
- **Logs:** `npx wrangler tail`.
- This is honest-customer licensing for an open CLI, not DRM. Anyone can patch Python. The aim is to make
  paying the easy path and to stop keys being casually shared across repos.
