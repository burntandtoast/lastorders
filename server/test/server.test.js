import { test } from "node:test";
import assert from "node:assert/strict";
import { fakeNetwork, harness, makeEnv, paidSessionEvent, WHSEC } from "./helpers.js";
import { generateKey, KEY_RE, verifyToken } from "../src/keys.js";
import { formEncode, signStripePayload, verifyStripeSignature } from "../src/stripe.js";
import { applyManagedPayments } from "../src/managed-payments.js";
import { normaliseRepo } from "../src/util.js";

const KEY_IN = (s) => (s.match(/BTM-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}/) || [])[0];

test("generated keys match the CLI format and avoid ambiguous characters", () => {
  const seen = new Set();
  for (let i = 0; i < 2000; i++) {
    const k = generateKey();
    assert.match(k, KEY_RE);
    assert.doesNotMatch(k.slice(4), /[IO01]/);
    seen.add(k);
  }
  assert.equal(seen.size, 2000);
});

test("repo identity normalisation", () => {
  assert.equal(normaliseRepo("github.com/Leigh/App"), "github.com/leigh/app");
  assert.equal(normaliseRepo("https://github.com/leigh/app.git"), "github.com/leigh/app");
  assert.equal(normaliseRepo("git@github.com:leigh/app.git"), "github.com/leigh/app");
  assert.equal(normaliseRepo("leigh/app"), "github.com/leigh/app");
  assert.equal(normaliseRepo("not a repo"), null);
  assert.equal(normaliseRepo(""), null);
});

test("Stripe signature: valid, wrong secret, tampered body, stale, v0-only, rolled secrets", async () => {
  const raw = '{"id":"evt_1"}';
  const now = Date.now();
  const t = Math.floor(now / 1000);
  const h = await signStripePayload(raw, WHSEC, t);
  assert.equal((await verifyStripeSignature(raw, h, WHSEC, { now })).ok, true);
  assert.equal((await verifyStripeSignature(raw, h, "whsec_other", { now })).ok, false);
  assert.equal((await verifyStripeSignature(raw + " ", h, WHSEC, { now })).ok, false);
  assert.equal((await verifyStripeSignature(raw, h, WHSEC, { now: now + 301_000 })).reason, "timestamp outside tolerance");
  assert.equal((await verifyStripeSignature(raw, h.replace("v1=", "v0="), WHSEC, { now })).ok, false);
  assert.equal((await verifyStripeSignature(raw, h, `whsec_old,${WHSEC}`, { now })).ok, true);
  assert.equal((await verifyStripeSignature(raw, null, WHSEC, { now })).ok, false);
});

test("form encoding matches Stripe's bracket syntax", () => {
  const f = formEncode({ mode: "payment", line_items: [{ price_data: { currency: "gbp", unit_amount: 14900 }, quantity: 1 }], metadata: { a: "b" }, skip: undefined });
  assert.equal(f.get("line_items[0][price_data][unit_amount]"), "14900");
  assert.equal(f.get("metadata[a]"), "b");
  assert.equal(f.has("skip"), false);
});

test("checkout: £149 inline price by default, configurable amount, price id, redirect", async () => {
  const net = fakeNetwork();
  const env = await makeEnv();
  const h = harness(env, net);
  const r = await h.postJson("/api/checkout", { repo: "https://github.com/Acme/Shop", email: "dev@acme.test" });
  assert.equal(r.status, 200);
  const { url, id } = await r.json();
  assert.match(id, /^cs_test_/);
  assert.ok(url.startsWith("https://checkout.stripe.test/"));
  const p = new URLSearchParams(net.calls[0].body);
  assert.equal(net.calls[0].headers.authorization, "Bearer sk_test_dummy");
  assert.equal(p.get("mode"), "payment");
  assert.equal(p.get("line_items[0][price_data][currency]"), "gbp");
  assert.equal(p.get("line_items[0][price_data][unit_amount]"), "14900");
  assert.equal(p.get("line_items[0][price_data][tax_behavior]"), "inclusive");
  assert.equal(p.get("line_items[0][price_data][product_data][tax_code]"), "txcd_10202003");
  assert.equal(p.get("managed_payments[enabled]"), null);
  assert.equal(net.calls[0].headers["stripe-version"], undefined);
  assert.equal(p.get("line_items[0][quantity]"), "1");
  assert.equal(p.get("success_url"), "https://licence.example.test/success?session_id={CHECKOUT_SESSION_ID}");
  assert.equal(p.get("cancel_url"), "https://licence.example.test/cancel");
  assert.equal(p.get("metadata[product]"), "lastorders-repo");
  assert.equal(p.get("metadata[repo_hint]"), "github.com/acme/shop");
  assert.equal(p.get("customer_email"), "dev@acme.test");

  const env2 = await makeEnv({ PRICE_AMOUNT: "9900", CURRENCY: "EUR", ALLOW_PROMOTION_CODES: "true" });
  const net2 = fakeNetwork();
  const r2 = await harness(env2, net2).call("/buy?repo=acme/shop");
  assert.equal(r2.status, 303);
  assert.ok(r2.headers.get("location").startsWith("https://checkout.stripe.test/pay/cs_test_"));
  const p2 = new URLSearchParams(net2.calls[0].body);
  assert.equal(p2.get("line_items[0][price_data][unit_amount]"), "9900");
  assert.equal(p2.get("line_items[0][price_data][currency]"), "eur");
  assert.equal(p2.get("allow_promotion_codes"), "true");

  const net3 = fakeNetwork();
  await harness(await makeEnv({ STRIPE_PRICE_ID: "price_123" }), net3).postJson("/api/checkout", {});
  const p3 = new URLSearchParams(net3.calls[0].body);
  assert.equal(p3.get("line_items[0][price]"), "price_123");
  assert.equal(p3.has("line_items[0][price_data][unit_amount]"), false);
  assert.equal(p3.has("customer_email"), false);

  const netOff = fakeNetwork();
  await harness(await makeEnv({ STRIPE_AUTOMATIC_TAX: "true", STRIPE_INVOICE_CREATION: "true" }), netOff).call("/buy");
  const off = new URLSearchParams(netOff.calls[0].body);
  assert.equal(off.get("automatic_tax[enabled]"), "true");
  assert.equal(off.get("invoice_creation[enabled]"), "true");
  assert.equal(off.get("managed_payments[enabled]"), null);
  assert.equal(netOff.calls[0].headers["stripe-version"], undefined);
});

test("webhook: bad signature rejected and nothing stored", async () => {
  const net = fakeNetwork();
  const env = await makeEnv();
  const h = harness(env, net);
  const r = await h.webhook(paidSessionEvent("cs_test_bad"), { secret: "whsec_wrong" });
  assert.equal(r.status, 400);
  assert.equal(await env.DB.prepare("SELECT COUNT(*) AS n FROM licences").first().then((x) => x.n), 0);
});

test("webhook: payment issues a key, stores email, emails it once; retries and duplicates are idempotent", async () => {
  const net = fakeNetwork();
  const env = await makeEnv();
  const h = harness(env, net);
  const ev = paidSessionEvent("cs_test_paid1", { email: "Buyer@Example.com" });
  const r = await h.webhook(ev);
  assert.equal(r.status, 200);
  const row = await env.DB.prepare("SELECT * FROM licences").first();
  assert.match(row.key, KEY_RE);
  assert.equal(row.email, "Buyer@Example.com");
  assert.equal(row.repo, null);                // bound on first activation, not at purchase
  assert.equal(row.status, "active");
  assert.equal(row.email_status, "sent");
  assert.equal(row.amount, 14900);
  const emails = net.calls.filter((c) => c.url.startsWith("https://resend.test/"));
  assert.equal(emails.length, 1);
  const sent = JSON.parse(emails[0].body);
  assert.deepEqual(sent.to, ["Buyer@Example.com"]);
  assert.ok(sent.text.includes(row.key) && sent.html.includes(row.key));
  assert.equal(emails[0].headers["idempotency-key"], `licence-email-${row.key}`);

  assert.equal((await (await h.webhook(ev)).json()).duplicate, true);                   // same event redelivered
  await h.webhook({ ...paidSessionEvent("cs_test_paid1"), type: "checkout.session.async_payment_succeeded" }); // different event, same session
  assert.equal(await env.DB.prepare("SELECT COUNT(*) AS n FROM licences").first().then((x) => x.n), 1);
  assert.equal(net.calls.filter((c) => c.url.startsWith("https://resend.test/")).length, 1);
});

test("webhook: unpaid (async) sessions wait; other products are ignored", async () => {
  const net = fakeNetwork();
  const env = await makeEnv();
  const h = harness(env, net);
  assert.equal((await (await h.webhook(paidSessionEvent("cs_test_async", { payment_status: "unpaid" }))).json()).pending, "unpaid");
  assert.equal((await (await h.webhook(paidSessionEvent("cs_test_other", { product: "something-else" }))).json()).ignored, "not this product");
  assert.equal(await env.DB.prepare("SELECT COUNT(*) AS n FROM licences").first().then((x) => x.n), 0);
  await h.webhook(paidSessionEvent("cs_test_async", { type: "checkout.session.async_payment_succeeded" }));
  assert.equal(await env.DB.prepare("SELECT COUNT(*) AS n FROM licences").first().then((x) => x.n), 1);
});

test("webhook: email failure returns 500 so Stripe retries; the retry sends it without a second key", async () => {
  const net = fakeNetwork({ resendFails: 1 });
  const env = await makeEnv();
  const h = harness(env, net);
  const ev = paidSessionEvent("cs_test_mailfail");
  assert.equal((await h.webhook(ev)).status, 500);
  let row = await env.DB.prepare("SELECT * FROM licences").first();
  assert.equal(row.email_status, "failed");
  const r = await h.webhook(ev);                 // Stripe redelivers the same event id
  assert.equal(r.status, 200);
  const row2 = await env.DB.prepare("SELECT * FROM licences").first();
  assert.equal(row2.key, row.key);
  assert.equal(row2.email_status, "sent");
});

test("email provider is pluggable: log provider records instead of sending", async () => {
  const net = fakeNetwork();
  const env = await makeEnv({ EMAIL_PROVIDER: "log" });
  const h = harness(env, net);
  await h.webhook(paidSessionEvent("cs_test_log"));
  assert.equal(net.calls.filter((c) => c.url.startsWith("https://resend.test/")).length, 0);
  assert.equal((await env.DB.prepare("SELECT email_status FROM licences").first()).email_status, "sent");
});

async function issue(env, net, id = "cs_test_v") {
  await harness(env, net).webhook(paidSessionEvent(id));
  return (await env.DB.prepare("SELECT key FROM licences WHERE stripe_session_id = ?").bind(id).first()).key;
}

test("verify: binds on first activation, returns a signed short-lived token, rejects other repos", async () => {
  const net = fakeNetwork();
  const t0 = Date.parse("2026-10-15T12:00:00Z");
  const env = await makeEnv({ TOKEN_TTL_DAYS: "7" });
  const key = await issue(env, net);
  const h = harness(env, net, { clock: () => t0 });
  const r = await h.postJson("/api/licence/verify", { key, repo: "github.com/Acme/Shop" });
  assert.equal(r.status, 200);
  const body = await r.json();
  assert.equal(body.status, "ok");
  assert.equal(body.repo, "github.com/acme/shop");
  const pub = JSON.parse(env.LICENCE_SIGNING_KEY).x;
  const claims = await verifyToken(body.token, pub);
  assert.equal(claims.repo, "github.com/acme/shop");
  assert.equal(claims.kid, "test");
  assert.equal(claims.exp - claims.iat, 7 * 86400);
  assert.equal(claims.iat, t0 / 1000);
  assert.ok(!JSON.stringify(claims).includes(key), "token must not carry the raw key");
  // The last two base64url characters of a 64-byte signature can decode to the same
  // byte as "AA" (about 1 in 256 signatures). Flip the first signature character instead.
  const sigAt = body.token.lastIndexOf(".") + 1;
  const flipped = body.token[sigAt] === "A" ? "B" : "A";
  const tampered = body.token.slice(0, sigAt) + flipped + body.token.slice(sigAt + 1);
  assert.equal(await verifyToken(tampered, pub), null);

  const row = await env.DB.prepare("SELECT * FROM licences WHERE key = ?").bind(key).first();
  assert.equal(row.repo, "github.com/acme/shop");
  assert.ok(row.activated_at);

  assert.equal((await h.postJson("/api/licence/verify", { key, repo: "acme/shop" })).status, 200);   // same repo, other spelling
  const other = await h.postJson("/api/licence/verify", { key, repo: "github.com/acme/other" });
  assert.equal(other.status, 403);
  assert.equal((await other.json()).status, "bound_to_other_repo");
});

test("verify: unknown, malformed, revoked; public key endpoint", async () => {
  const net = fakeNetwork();
  const env = await makeEnv();
  const h = harness(env, net);
  assert.equal((await h.postJson("/api/licence/verify", { key: "BTM-AAAA-BBBB-CCCC", repo: "a/b" })).status, 404);
  assert.equal((await h.postJson("/api/licence/verify", { key: "nope", repo: "a/b" })).status, 400);
  const key = await issue(env, net, "cs_test_r");
  assert.equal((await h.postJson("/api/licence/verify", { key, repo: "???" })).status, 400);
  const pk = await (await h.call("/api/licence/public-key")).json();
  assert.equal(pk.keys[0].x, JSON.parse(env.LICENCE_SIGNING_KEY).x);
});

test("full refund revokes; partial refund doesn't", async () => {
  const net = fakeNetwork();
  const env = await makeEnv();
  const h = harness(env, net);
  await h.webhook(paidSessionEvent("cs_test_ref", { pi: "pi_full" }));
  await h.webhook(paidSessionEvent("cs_test_part", { pi: "pi_part" }));
  await h.webhook({ id: "evt_rp", type: "charge.refunded", data: { object: { id: "ch_2", payment_intent: "pi_part", amount: 14900, amount_refunded: 5000, refunded: false } } });
  await h.webhook({ id: "evt_rf", type: "charge.refunded", data: { object: { id: "ch_1", payment_intent: "pi_full", amount: 14900, amount_refunded: 14900, refunded: true } } });
  const full = await env.DB.prepare("SELECT * FROM licences WHERE stripe_payment_intent = 'pi_full'").first();
  const part = await env.DB.prepare("SELECT * FROM licences WHERE stripe_payment_intent = 'pi_part'").first();
  assert.equal(full.status, "revoked");
  assert.equal(full.revoke_reason, "refunded");
  assert.equal(part.status, "active");
  const r = await h.postJson("/api/licence/verify", { key: full.key, repo: "a/b" });
  assert.equal(r.status, 403);
  assert.equal((await r.json()).status, "revoked");
});

test("success page: shows the key, fulfils before the webhook and emails once, handles pending/unknown", async () => {
  const net = fakeNetwork();
  const env = await makeEnv();
  const h = harness(env, net);
  const { id } = await (await h.postJson("/api/checkout", {})).json();
  assert.equal((await h.call(`/success?session_id=${id}`)).status, 202);         // not paid yet
  Object.assign(net.sessions.get(id), { status: "complete", payment_status: "paid", customer_details: { email: "early@example.com" }, payment_intent: "pi_e" });
  const page = await (await h.call(`/success?session_id=${id}`)).text();
  const key = KEY_IN(page);
  assert.ok(key);
  // the success page emails the key itself, so a missing or failing webhook can't leave the buyer without it
  assert.equal(net.calls.filter((c) => c.url.startsWith("https://resend.test/")).length, 1);
  // the webhook lands later: same key, no second email
  await h.webhook({ ...paidSessionEvent(id, { email: "early@example.com", pi: "pi_e" }) });
  const row = await env.DB.prepare("SELECT * FROM licences").first();
  assert.equal(row.key, key);
  assert.equal(row.email_status, "sent");
  assert.equal(KEY_IN(await (await h.call(`/success?session_id=${id}`)).text()), key);
  assert.equal(net.calls.filter((c) => c.url.startsWith("https://resend.test/")).length, 1);
  assert.equal((await h.call("/success?session_id=cs_test_missing")).status, 404);
  assert.equal((await h.call("/success?session_id=<script>")).status, 400);
});

test("admin: auth required; rebind and revoke", async () => {
  const net = fakeNetwork();
  const env = await makeEnv();
  const h = harness(env, net);
  const key = await issue(env, net, "cs_test_adm");
  await h.postJson("/api/licence/verify", { key, repo: "acme/one" });
  assert.equal((await h.call(`/api/admin/licences/${key}`)).status, 401);
  const auth = { authorization: `Bearer ${env.ADMIN_TOKEN}` };
  assert.equal((await h.call(`/api/admin/licences/${key}`, { headers: auth })).status, 200);
  await h.postJson(`/api/admin/licences/${key}/rebind`, { repo: "acme/two" }, auth);
  assert.equal((await h.postJson("/api/licence/verify", { key, repo: "acme/two" })).status, 200);
  await h.postJson(`/api/admin/licences/${key}/rebind`, { repo: null }, auth);
  assert.equal((await h.postJson("/api/licence/verify", { key, repo: "acme/three" })).status, 200);
  await h.postJson(`/api/admin/licences/${key}/revoke`, { reason: "chargeback" }, auth);
  assert.equal((await h.postJson("/api/licence/verify", { key, repo: "acme/three" })).status, 403);
});

test("static assets fall through; unknown API is JSON 404; healthz reports test mode", async () => {
  const net = fakeNetwork();
  const env = await makeEnv({ ASSETS: { fetch: async () => new Response("asset", { status: 200 }) } });
  const h = harness(env, net);
  assert.equal(await (await h.call("/v1/index.json")).text(), "asset");
  assert.equal((await h.call("/api/nope")).status, 404);
  assert.equal((await (await h.call("/healthz")).json()).stripe_mode, "test");
});

test("success page: an email failure doesn't break the page and the webhook retries it", async () => {
  const net = fakeNetwork({ resendFails: 1 });
  const env = await makeEnv();
  const h = harness(env, net);
  const { id } = await (await h.postJson("/api/checkout", {})).json();
  Object.assign(net.sessions.get(id), { status: "complete", payment_status: "paid", customer_details: { email: "e@example.com" }, payment_intent: "pi_f" });
  const res = await h.call(`/success?session_id=${id}`);
  assert.equal(res.status, 200);
  assert.ok(KEY_IN(await res.text()));
  assert.equal((await env.DB.prepare("SELECT email_status FROM licences").first()).email_status, "failed");
  await h.webhook(paidSessionEvent(id, { email: "e@example.com", pi: "pi_f" }));
  assert.equal((await env.DB.prepare("SELECT email_status FROM licences").first()).email_status, "sent");
});

test("checkout: required waiver consent, policy message and waiver metadata; /terms page; email refund line", async () => {
  const net = fakeNetwork();
  const env = await makeEnv();
  const h = harness(env, net);
  assert.equal((await h.call("/buy")).status, 303);
  const p = new URLSearchParams(net.calls[0].body);
  assert.equal(p.get("custom_fields[0][key]"), "waiver");
  assert.equal(p.get("custom_fields[0][type]"), "dropdown");
  assert.equal(p.get("custom_fields[0][optional]"), "false");
  assert.equal(p.get("custom_fields[0][dropdown][options][0][value]"), "agree");
  assert.equal(p.get("custom_fields[0][dropdown][default_value]"), null);         // consent must not be pre-selected
  assert.equal(p.get("consent_collection[terms_of_service]"), null);
  const msg = p.get("custom_text[submit][message]");
  for (const s of ["reg. 37", "never been activated", "5 working days", "17334149", "71-75 Shelton Street", "Not VAT registered", "/terms"]) assert.ok(msg.includes(s), s);
  assert.ok(msg.length <= 1200);
  assert.equal(p.get("metadata[waiver_consent]"), "required_at_checkout");
  assert.match(p.get("metadata[waiver_at]"), /^\d{4}-\d\d-\d\dT/);
  assert.equal(p.get("payment_intent_data[metadata][waiver_consent]"), "required_at_checkout");

  const net2 = fakeNetwork();
  await harness(await makeEnv({ STRIPE_TOS_CONSENT: "true" }), net2).call("/buy");
  const p2 = new URLSearchParams(net2.calls[0].body);
  assert.equal(p2.get("consent_collection[terms_of_service]"), "required");
  assert.ok(p2.get("custom_text[terms_of_service_acceptance][message]").includes("14-day right to cancel"));
  assert.equal(p2.get("custom_fields[0][key]"), null);

  // the acceptance is read back from the completed session and logged
  const ev = paidSessionEvent("cs_test_waiver", { email: "w@example.com", pi: "pi_w" });
  ev.data.object.custom_fields = [{ key: "waiver", type: "dropdown", dropdown: { value: "agree" } }];
  ev.data.object.metadata.terms_version = "2026-10-15";
  assert.equal((await h.webhook(ev)).status, 200);
  const evRow = await env.DB.prepare("SELECT detail FROM licence_events WHERE kind = 'waiver_consent'").first();
  assert.equal(evRow.detail, "checkout_custom_field terms=2026-10-15");
  const mail = net.calls.find((c) => c.url.startsWith("https://resend.test/"));
  const body = JSON.parse(mail.body);
  assert.ok(body.text.includes("never been activated") && body.text.includes("/terms"));
  assert.ok(body.html.includes("5 working days"));

  const t = await h.call("/terms");
  assert.equal(t.status, 200);
  const html = await t.text();
  for (const s of ["17334149", "England and Wales", "regulation 37", "hello@burntandtoast.com", "never been activated", "5 working days", "£149"]) assert.ok(html.includes(s), s);
  assert.equal(html.includes("Sold through Link"), false);
});

test("applyManagedPayments strips the update-checkout disallow list and keeps the waiver", () => {
  const params = {
    mode: "payment",
    automatic_tax: { enabled: true },
    tax_id_collection: { enabled: true },
    adaptive_pricing: { enabled: false },
    excluded_payment_method_types: ["sepa_debit"],
    payment_method_configuration: "pmc_1",
    payment_method_types: ["card"],
    customer_update: { name: "auto", address: "auto", shipping: "auto" },
    shipping_address_collection: { allowed_countries: ["GB"] },
    shipping_options: [{ shipping_rate: "shr_1" }],
    invoice_creation: { enabled: true },
    custom_fields: [{ key: "waiver" }],
    custom_text: { submit: { message: "waiver" } },
    consent_collection: { terms_of_service: "required" },
    payment_intent_data: {
      metadata: { product: "lastorders-repo" },
      shipping: { name: "a" },
      application_fee_amount: 1,
      on_behalf_of: "acct_1",
      transfer_data: { destination: "acct_1" },
      transfer_group: "g",
      statement_descriptor: "LASTORDERS",
      statement_descriptor_suffix: "LICENCE",
      receipt_email: "a@b.test",
    },
    subscription_data: {
      default_tax_rates: ["txr_1"],
      application_fee_percent: 10,
      on_behalf_of: "acct_1",
      transfer_data: { destination: "acct_1" },
      invoice_settings: { issuer: { type: "self" } },
    },
  };
  applyManagedPayments(params);
  assert.deepEqual(params.managed_payments, { enabled: true });
  assert.equal(params.automatic_tax, undefined);
  assert.equal(params.tax_id_collection, undefined);
  assert.equal(params.adaptive_pricing, undefined);
  assert.equal(params.excluded_payment_method_types, undefined);
  assert.equal(params.payment_method_configuration, undefined);
  assert.equal(params.payment_method_types, undefined);
  assert.deepEqual(params.customer_update, { shipping: "auto" });
  assert.equal(params.shipping_address_collection, undefined);
  assert.equal(params.shipping_options, undefined);
  assert.equal(params.invoice_creation, undefined);
  assert.equal(params.subscription_data, undefined);
  assert.deepEqual(params.payment_intent_data, { metadata: { product: "lastorders-repo" } });
  assert.equal(params.custom_fields[0].key, "waiver");
  assert.equal(params.custom_text.submit.message, "waiver");
  assert.equal(params.consent_collection.terms_of_service, "required");
});

test("managed payments: pinned Stripe version, tax code, waiver kept, disallowed params omitted", async () => {
  const net = fakeNetwork();
  const env = await makeEnv({ MANAGED_PAYMENTS: "1", STRIPE_AUTOMATIC_TAX: "true", STRIPE_INVOICE_CREATION: "true" });
  const h = harness(env, net);
  assert.equal((await h.call("/buy")).status, 303);
  assert.equal(net.calls[0].headers["stripe-version"], "2025-03-31.basil");
  const p = new URLSearchParams(net.calls[0].body);
  assert.equal(p.get("managed_payments[enabled]"), "true");
  assert.equal(p.get("line_items[0][price_data][tax_behavior]"), "inclusive");
  assert.equal(p.get("line_items[0][price_data][product_data][tax_code]"), "txcd_10202003");
  assert.equal(p.get("custom_fields[0][key]"), "waiver");
  assert.equal(p.get("custom_text[submit][message]")?.includes("reg. 37"), true);
  assert.equal(p.get("automatic_tax[enabled]"), null);
  assert.equal(p.get("invoice_creation[enabled]"), null);
  for (const key of [
    "tax_id_collection[enabled]",
    "adaptive_pricing[enabled]",
    "excluded_payment_method_types[0]",
    "payment_method_configuration",
    "payment_method_types[0]",
    "customer_update[name]",
    "customer_update[address]",
    "shipping_address_collection[allowed_countries][0]",
    "shipping_options[0][shipping_rate]",
    "payment_intent_data[shipping][address][line1]",
    "payment_intent_data[application_fee_amount]",
    "payment_intent_data[on_behalf_of]",
    "payment_intent_data[transfer_data][destination]",
    "payment_intent_data[transfer_group]",
    "payment_intent_data[statement_descriptor]",
    "payment_intent_data[statement_descriptor_suffix]",
    "payment_intent_data[receipt_email]",
    "subscription_data[default_tax_rates][0]",
    "subscription_data[application_fee_percent]",
    "subscription_data[on_behalf_of]",
    "subscription_data[transfer_data][destination]",
    "subscription_data[invoice_settings][issuer][type]",
  ]) assert.equal(p.get(key), null, key);

  const netLater = fakeNetwork();
  await harness(await makeEnv({ MANAGED_PAYMENTS: "1", STRIPE_API_VERSION: "2026-04-22.dahlia" }), netLater).call("/buy");
  assert.equal(netLater.calls[0].headers["stripe-version"], "2026-04-22.dahlia");
  const netOld = fakeNetwork();
  await harness(await makeEnv({ MANAGED_PAYMENTS: "1", STRIPE_API_VERSION: "2024-06-20.acacia" }), netOld).call("/buy");
  assert.equal(netOld.calls[0].headers["stripe-version"], "2025-03-31.basil");

  const terms = await (await h.call("/terms")).text();
  for (const s of ["Sold through Link", "LINK.COM*", "payment support", "60 days", "48 hours", "never been activated", "5 working days"]) {
    assert.ok(terms.includes(s), s);
  }
});

test("fulfilment keeps the session amount and currency; a full refund or dispute revokes", async () => {
  const net = fakeNetwork();
  const env = await makeEnv();
  const h = harness(env, net);
  await h.webhook(paidSessionEvent("cs_test_eur", { pi: "pi_eur", amount_total: 17880, currency: "eur" }));
  const issued = await env.DB.prepare("SELECT * FROM licences WHERE stripe_payment_intent = 'pi_eur'").first();
  assert.equal(issued.status, "active");
  assert.equal(issued.currency, "eur");
  assert.equal(issued.amount, 17880);
  await h.webhook({
    id: "evt_eur_rf", type: "charge.refunded",
    data: { object: { id: "ch_eur", payment_intent: "pi_eur", amount: 17880, amount_refunded: 17880, currency: "eur", refunded: true } },
  });
  const refunded = await env.DB.prepare("SELECT status, revoke_reason FROM licences WHERE stripe_payment_intent = 'pi_eur'").first();
  assert.equal(refunded.status, "revoked");
  assert.equal(refunded.revoke_reason, "refunded");

  await h.webhook(paidSessionEvent("cs_test_dp", { pi: "pi_dp", amount_total: 20000, currency: "usd" }));
  await h.webhook({
    id: "evt_dp", type: "charge.dispute.created",
    data: { object: { id: "dp_1", object: "dispute", payment_intent: { id: "pi_dp" }, amount: 20000, currency: "usd", reason: "product_unacceptable" } },
  });
  const disputed = await env.DB.prepare("SELECT * FROM licences WHERE stripe_payment_intent = 'pi_dp'").first();
  assert.equal(disputed.status, "revoked");
  assert.equal(disputed.revoke_reason, "dispute dp_1");
  assert.equal((await h.postJson("/api/licence/verify", { key: disputed.key, repo: "a/b" })).status, 403);
});

test("success page names Link only when Managed Payments is on", async () => {
  async function pageFor(overrides) {
    const net = fakeNetwork();
    const h = harness(await makeEnv(overrides), net);
    const { id } = await (await h.postJson("/api/checkout", {})).json();
    Object.assign(net.sessions.get(id), { status: "complete", payment_status: "paid", customer_details: { email: "s@example.com" }, payment_intent: "pi_s", amount_total: 17880, currency: "eur" });
    return (await h.call(`/success?session_id=${id}`)).text();
  }
  assert.equal((await pageFor()).includes("Sold through Link"), false);
  const on = await pageFor({ MANAGED_PAYMENTS: "1" });
  assert.ok(on.includes("Sold through Link"));
  assert.ok(on.includes("LINK.COM*"));
  assert.ok(on.includes("payment support"));
});

test("customer pages live on PUBLIC_SITE_URL: Checkout URLs, email, terms; API host 301s old links", async () => {
  const net = fakeNetwork();
  const env = await makeEnv({ PUBLIC_SITE_URL: "https://shop.example.test" });
  const h = harness(env, net);
  assert.equal((await h.call("/buy")).status, 301);      // harness requests the API host
  const app = (await import("../src/index.js")).createApp({ fetch: net.fetch });
  const r = await app.fetch(new Request("https://licence.example.test/success?session_id=cs_test_x"), env);
  assert.equal(r.status, 301);
  assert.equal(r.headers.get("location"), "https://shop.example.test/success?session_id=cs_test_x");
  const b = await app.fetch(new Request("https://shop.example.test/buy?repo=a/b"), env);
  assert.equal(b.status, 303);
  const p = new URLSearchParams(net.calls.at(-1).body);
  assert.equal(p.get("success_url"), "https://shop.example.test/success?session_id={CHECKOUT_SESSION_ID}");
  assert.equal(p.get("cancel_url"), "https://shop.example.test/cancel");
  assert.ok(p.get("custom_text[submit][message]").includes("shop.example.test/terms"));
  const t = await (await app.fetch(new Request("https://shop.example.test/terms"), env)).text();
  assert.ok(t.includes("https://shop.example.test/buy"));
  assert.equal((await app.fetch(new Request("https://licence.example.test/healthz"), env)).status, 200);
  assert.equal((await app.fetch(new Request("https://licence.example.test/api/stripe/webhook", { method: "POST", body: "{}" }), env)).status, 400);
});
