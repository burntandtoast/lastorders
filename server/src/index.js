// Last Orders licence server: Cloudflare Worker + D1 (+ static pack site via assets).
//
//   GET  /buy?repo=&email=          -> 303 to Stripe Checkout
//   POST /api/checkout               -> {id, url}
//   POST /api/stripe/webhook         <- Stripe events (signed)
//   GET  /success?session_id=        -> shows the key (fulfils idempotently if the webhook hasn't landed yet)
//   GET  /cancel
//   POST /api/licence/verify         <- CLI: {key, repo} -> short-lived signed token
//   GET  /api/licence/public-key
//   GET|POST /api/admin/licences/:key[/revoke|/rebind|/resend-email]   (Bearer ADMIN_TOKEN)
//   GET  /healthz
//   anything else -> static assets (the pack site, packs.<domain>/v1/...)
import { json, normaliseRepo, nowIso, sha256hex, timingSafeEqual } from "./util.js";
import { generateKey, KEY_RE, loadSigningKey, signToken } from "./keys.js";
import { Store } from "./store.js";
import { Stripe, StripeError, verifyStripeSignature } from "./stripe.js";
import { licenceEmail, makeMailer } from "./email.js";
import { cancelPage, errorPage, pendingPage, successPage } from "./pages.js";

const DAY = 86400;

function config(env) {
  return {
    productName: env.PRODUCT_NAME || "Last Orders",
    cliName: env.CLI_NAME || "lastorders",
    productCode: env.PRODUCT_CODE || "lastorders-repo",
    currency: (env.CURRENCY || "gbp").toLowerCase(),
    amount: Number.parseInt(env.PRICE_AMOUNT || "14900", 10),     // minor units: 14900 = £149.00
    priceId: env.STRIPE_PRICE_ID || "",
    tokenTtl: Number.parseInt(env.TOKEN_TTL_DAYS || "7", 10) * DAY,
    features: (env.LICENCE_FEATURES || "*").split(",").map((s) => s.trim()).filter(Boolean),
    allowPromo: env.ALLOW_PROMOTION_CODES === "true",
    automaticTax: env.STRIPE_AUTOMATIC_TAX === "true",
    invoice: env.STRIPE_INVOICE_CREATION === "true",
    supportEmail: env.SUPPORT_EMAIL || "",
  };
}

export function createApp(deps = {}) {
  const fetchImpl = deps.fetch || ((...a) => fetch(...a));
  const clock = deps.clock || (() => Date.now());

  function ctxFor(request, env) {
    const cfg = config(env);
    const baseUrl = (env.PUBLIC_BASE_URL || new URL(request.url).origin).replace(/\/$/, "");
    const store = new Store(env.DB, clock);
    const stripe = () => new Stripe({ secretKey: env.STRIPE_SECRET_KEY, apiBase: env.STRIPE_API_BASE, apiVersion: env.STRIPE_API_VERSION, fetchImpl });
    const mailer = deps.mailer || makeMailer(env, fetchImpl);
    return { env, cfg, baseUrl, store, stripe, mailer };
  }

  // ---- Checkout -------------------------------------------------------------------------------
  async function createCheckout(c, { repo, email }) {
    const { cfg, baseUrl } = c;
    const metadata = { product: cfg.productCode };
    const repoHint = repo ? normaliseRepo(repo) : null;
    if (repoHint) metadata.repo_hint = repoHint;       // informational; binding happens on first activation
    const lineItem = cfg.priceId
      ? { price: cfg.priceId, quantity: 1 }
      : {
          quantity: 1,
          price_data: {
            currency: cfg.currency,
            unit_amount: cfg.amount,
            product_data: { name: `${cfg.productName} licence: one repository`, description: "Automatic fixes, verified patches and client reports for one repo (monorepos count as one)." },
          },
        };
    const params = {
      mode: "payment",
      line_items: [lineItem],
      success_url: `${baseUrl}/success?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${baseUrl}/cancel`,
      customer_creation: "always",
      metadata,
      payment_intent_data: { metadata },
    };
    if (email && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) && email.length <= 254) params.customer_email = email;
    if (cfg.allowPromo) params.allow_promotion_codes = true;
    if (cfg.automaticTax) params.automatic_tax = { enabled: true };
    if (cfg.invoice) params.invoice_creation = { enabled: true };
    return c.stripe().createCheckoutSession(params);
  }

  // ---- Fulfilment (shared by webhook and success page; idempotent per Checkout Session) ---------
  function isOurs(c, session) {
    return session?.metadata?.product === c.cfg.productCode && session.mode === "payment";
  }
  function isPaid(session) {
    return session.status === "complete" && (session.payment_status === "paid" || session.payment_status === "no_payment_required");
  }

  async function fulfil(c, session, { sendEmail }) {
    const email = session.customer_details?.email || session.customer_email;
    if (!email) throw new Error(`session ${session.id} has no customer email`);
    let row = await c.store.bySession(session.id);
    if (!row) {
      for (let attempt = 0; attempt < 3 && !row; attempt++) {
        try {
          ({ row } = await c.store.createForSession({
            key: generateKey(), email, sessionId: session.id,
            paymentIntent: typeof session.payment_intent === "string" ? session.payment_intent : session.payment_intent?.id ?? null,
            customer: typeof session.customer === "string" ? session.customer : session.customer?.id ?? null,
            amount: session.amount_total ?? null, currency: session.currency ?? null, livemode: !!session.livemode,
          }));
        } catch (e) {
          if (!/UNIQUE|constraint/i.test(String(e?.message))) throw e;   // key collision (60-bit keys; practically never): retry
        }
      }
    }
    if (!row) throw new Error("could not create licence");
    if (sendEmail && row.email_status !== "sent" && row.status === "active") {
      const msg = licenceEmail({ key: row.key, productName: c.cfg.productName, cliName: c.cfg.cliName, buyerEmail: row.email, baseUrl: c.baseUrl, supportEmail: c.cfg.supportEmail });
      const r = await c.mailer.send(msg, `licence-email-${row.key}`);
      if (r.ok) {
        await c.store.setEmailStatus(row.key, r.skipped ? "skipped" : "sent");
        await c.store.event(row.key, "email_sent", c.mailer.name);
      } else {
        await c.store.setEmailStatus(row.key, "failed");
        await c.store.event(row.key, "email_failed", r.error);
        const err = new Error(`licence email failed: ${r.error}`);
        err.retryable = true;
        throw err;
      }
    }
    return row;
  }

  // ---- Webhook --------------------------------------------------------------------------------
  async function webhook(c, request) {
    const raw = await request.text();
    const sig = await verifyStripeSignature(raw, request.headers.get("stripe-signature"), c.env.STRIPE_WEBHOOK_SECRET, { now: clock() });
    if (!sig.ok) {
      console.error(`[webhook] rejected: ${sig.reason}`);   // usually a STRIPE_WEBHOOK_SECRET from a different endpoint or mode
      return json({ error: "invalid_signature", detail: sig.reason }, 400);
    }
    let event;
    try { event = JSON.parse(raw); } catch { return json({ error: "invalid_json" }, 400); }
    if (!event?.id || !event?.type) return json({ error: "invalid_event" }, 400);
    if (!(await c.store.claimEvent(event.id, event.type))) return json({ received: true, duplicate: true });
    try {
      const obj = event.data?.object || {};
      switch (event.type) {
        case "checkout.session.completed":
        case "checkout.session.async_payment_succeeded":
          if (!isOurs(c, obj)) return json({ received: true, ignored: "not this product" });
          if (!isPaid(obj)) return json({ received: true, pending: obj.payment_status });   // async methods: wait for async_payment_succeeded
          if (!(obj.customer_details?.email || obj.customer_email)) {
            console.error(`[webhook] paid session ${obj.id} has no customer email; not fulfilled (check it in the Dashboard)`);
            return json({ received: true, ignored: "no customer email" });
          }
          await fulfil(c, obj, { sendEmail: true });
          break;
        case "checkout.session.async_payment_failed":
          console.log(`[webhook] async payment failed for ${obj.id}`);
          break;
        case "charge.refunded": {
          // Full refunds revoke the licence; partial refunds (goodwill discounts) don't.
          const fullyRefunded = obj.refunded === true || (obj.amount_refunded ?? 0) >= (obj.amount ?? Infinity);
          const pi = typeof obj.payment_intent === "string" ? obj.payment_intent : obj.payment_intent?.id;
          if (fullyRefunded && pi) for (const row of await c.store.byPaymentIntent(pi)) await c.store.revoke(row.key, "refunded");
          break;
        }
        default:
          break;
      }
      return json({ received: true });
    } catch (e) {
      await c.store.releaseEvent(event.id);       // let Stripe retry (it retries for up to 3 days)
      console.error(`[webhook] ${event.type} ${event.id}: ${e?.message}`);
      return json({ error: "processing_failed" }, 500);
    }
  }

  // ---- Success page ---------------------------------------------------------------------------
  async function success(c, url) {
    const id = url.searchParams.get("session_id") || "";
    if (!/^cs_(test|live)_[A-Za-z0-9]+$/.test(id)) return errorPage("Missing or invalid checkout session.", 400);
    let row = await c.store.bySession(id);
    if (!row) {
      let session;
      try { session = await c.stripe().retrieveCheckoutSession(id); }
      catch (e) { return errorPage(e instanceof StripeError && e.status === 404 ? "Checkout session not found." : "Couldn't reach the payment provider. Please refresh in a moment.", e?.status === 404 ? 404 : 502); }
      if (!isOurs(c, session)) return errorPage("Checkout session not found.", 404);
      if (!isPaid(session)) return pendingPage(c.cfg);
      row = await fulfil(c, session, { sendEmail: false });
    }
    // Normally the webhook sends the email. If it hasn't yet (webhook late, misconfigured or failing), send it
    // from here too, so a buyer always gets the key by email. Resend's idempotency key (licence-email-<key>)
    // stops a duplicate if the webhook sends at the same moment. A failure here doesn't break the page; the
    // webhook's retries still apply.
    if (row.status === "active" && row.email_status !== "sent" && row.email_status !== "skipped") {
      try { await fulfil(c, { id: row.stripe_session_id, customer_details: { email: row.email } }, { sendEmail: true }); }
      catch (e) { console.error(`[success] licence email for session ${id} failed: ${e?.message}`); }
    }
    if (row.status !== "active") return errorPage("This licence has been revoked (refunded).", 410);
    return successPage({ key: row.key, email: row.email, productName: c.cfg.productName, cliName: c.cfg.cliName, baseUrl: c.baseUrl });
  }

  // ---- Verify (the CLI's only licence call: sends key + repo identity, nothing else) -------------
  async function verify(c, request) {
    let body;
    try { body = await request.json(); } catch { return json({ status: "invalid", error: "invalid_json" }, 400); }
    const key = String(body?.key || "").trim().toUpperCase();
    const repo = normaliseRepo(body?.repo);
    if (!KEY_RE.test(key)) return json({ status: "invalid", error: "malformed_key" }, 400);
    if (!repo) return json({ status: "invalid", error: "invalid_repo", detail: "repo must look like github.com/owner/name" }, 400);
    let row = await c.store.get(key);
    if (!row) return json({ status: "not_found", error: "unknown licence key" }, 404);
    if (row.status !== "active") return json({ status: "revoked", error: `licence revoked${row.revoke_reason ? ` (${row.revoke_reason})` : ""}` }, 403);
    if (!row.repo) {
      row = await c.store.activate(key, repo);       // atomic: only binds while unbound
      if (row.repo === repo) await c.store.event(key, "activated", repo);
    }
    if (row.repo !== repo) {
      await c.store.event(key, "rejected_repo", repo);
      return json({ status: "bound_to_other_repo", error: `this licence is bound to ${row.repo}`, bound_repo: row.repo }, 403);
    }
    const signing = await loadSigningKey(c.env.LICENCE_SIGNING_KEY);
    const iat = Math.floor(clock() / 1000);
    const exp = iat + c.cfg.tokenTtl;
    const token = await signToken(signing, {
      v: 1, iss: c.baseUrl, lic: (await sha256hex(key)).slice(0, 32), repo, plan: row.plan, features: c.cfg.features,
      test: !row.livemode, iat, exp,
    });
    return json({ status: "ok", repo, token, expires_at: nowIso(exp * 1000), kid: signing.kid });
  }

  // ---- Admin ----------------------------------------------------------------------------------
  async function admin(c, request, path) {
    const expected = c.env.ADMIN_TOKEN || "";
    const got = (request.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
    if (!expected || expected.length < 24 || !timingSafeEqual(got, expected)) return json({ error: "unauthorised" }, 401);
    const m = path.match(/^\/api\/admin\/licences\/(BTM-[A-Z0-9-]{14})(?:\/(revoke|rebind|resend-email))?$/);
    if (!m) return json({ error: "not_found" }, 404);
    const [, key, action] = m;
    const row = await c.store.get(key);
    if (!row) return json({ error: "not_found" }, 404);
    if (!action && request.method === "GET") return json({ licence: row });
    if (request.method !== "POST") return json({ error: "method_not_allowed" }, 405);
    const body = await request.json().catch(() => ({}));
    if (action === "revoke") await c.store.revoke(key, String(body.reason || "admin"));
    if (action === "rebind") {
      const repo = body.repo == null ? null : normaliseRepo(body.repo);
      if (body.repo != null && !repo) return json({ error: "invalid_repo" }, 400);
      await c.store.rebind(key, repo);
    }
    if (action === "resend-email") {
      await c.store.setEmailStatus(key, "pending");
      try { await fulfil(c, { id: row.stripe_session_id, customer_details: { email: row.email } }, { sendEmail: true }); }
      catch (e) { return json({ error: e.message }, 502); }
    }
    return json({ licence: await c.store.get(key) });
  }

  // ---- Router ---------------------------------------------------------------------------------
  async function handle(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    const c = ctxFor(request, env);
    try {
      if (path === "/healthz") return json({ ok: true, stripe_mode: (env.STRIPE_SECRET_KEY || "").includes("_live_") ? "live" : "test" });
      if (path === "/api/stripe/webhook" && request.method === "POST") return await webhook(c, request);
      if (path === "/api/licence/verify" && request.method === "POST") return await verify(c, request);
      if (path === "/api/licence/public-key" && request.method === "GET") {
        const s = await loadSigningKey(env.LICENCE_SIGNING_KEY);
        return json({ keys: [{ kid: s.kid, alg: "Ed25519", x: s.x }] }, 200, { "cache-control": "public, max-age=3600" });
      }
      if (path === "/api/checkout" && request.method === "POST") {
        const body = await request.json().catch(() => ({}));
        const s = await createCheckout(c, body || {});
        return json({ id: s.id, url: s.url });
      }
      if (path === "/buy" && request.method === "GET") {
        const s = await createCheckout(c, { repo: url.searchParams.get("repo"), email: url.searchParams.get("email") });
        return Response.redirect(s.url, 303);
      }
      if (path === "/success" && request.method === "GET") return await success(c, url);
      if (path === "/cancel" && request.method === "GET") return cancelPage({ productName: c.cfg.productName, baseUrl: c.baseUrl });
      if (path.startsWith("/api/admin/")) return await admin(c, request, path);
      if (path.startsWith("/api/")) return json({ error: "not_found" }, 404);
      if (env.ASSETS) return env.ASSETS.fetch(request);
      return new Response("Not found", { status: 404 });
    } catch (e) {
      console.error(`[${request.method} ${path}] ${e?.stack || e}`);
      if (e instanceof StripeError) return path === "/buy" ? errorPage("Couldn't start checkout. Please try again.", 502) : json({ error: "payment_provider_error" }, 502);
      return json({ error: "internal_error" }, 500);
    }
  }

  return { fetch: handle };
}

export default createApp();
