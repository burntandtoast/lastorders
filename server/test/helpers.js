// Test doubles: a D1-compatible database on sql.js, and a fake Stripe/Resend network.
import initSqlJs from "sql.js";
import { readFileSync } from "node:fs";
import { createApp } from "../src/index.js";
import { signStripePayload } from "../src/stripe.js";

const SQL = await initSqlJs();
const MIGRATION = readFileSync(new URL("../migrations/0001_init.sql", import.meta.url), "utf8");

export function fakeD1() {
  const db = new SQL.Database();
  db.exec(MIGRATION);
  const stmt = (sql, params = []) => ({
    bind: (...p) => stmt(sql, p),
    async first() {
      const s = db.prepare(sql); s.bind(params);
      const row = s.step() ? s.getAsObject() : null; s.free(); return row;
    },
    async all() {
      const s = db.prepare(sql); s.bind(params);
      const results = []; while (s.step()) results.push(s.getAsObject()); s.free();
      return { results, success: true };
    },
    async run() {
      db.run(sql, params);
      return { success: true, meta: { changes: db.getRowsModified() } };
    },
  });
  return { prepare: (sql) => stmt(sql), _db: db };
}

export async function devSigningKey(kid = "test") {
  const { privateKey } = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
  const j = await crypto.subtle.exportKey("jwk", privateKey);
  return { kid, d: j.d, x: j.x };
}

/** Fake Stripe + Resend. Records every request; sessions are kept in a map. */
export function fakeNetwork({ resendFails = 0 } = {}) {
  const calls = [];
  const sessions = new Map();
  let n = 0;
  let failuresLeft = resendFails;
  async function fetchImpl(url, init = {}) {
    const u = new URL(url);
    const body = init.body;
    calls.push({ url: u.toString(), method: init.method || "GET", headers: init.headers || {}, body });
    const ok = (d) => new Response(JSON.stringify(d), { status: 200, headers: { "content-type": "application/json" } });
    if (u.host === "stripe.test" && u.pathname === "/v1/checkout/sessions" && init.method === "POST") {
      const id = `cs_test_${(++n).toString().padStart(6, "0")}abc`;
      const params = new URLSearchParams(body);
      const s = { id, object: "checkout.session", url: `https://checkout.stripe.test/pay/${id}`, mode: params.get("mode"), status: "open",
        payment_status: "unpaid", metadata: { product: params.get("metadata[product]") }, livemode: false, params };
      sessions.set(id, s);
      return ok(s);
    }
    const m = u.pathname.match(/^\/v1\/checkout\/sessions\/(.+)$/);
    if (u.host === "stripe.test" && m) {
      const s = sessions.get(decodeURIComponent(m[1]));
      return s ? ok(s) : new Response(JSON.stringify({ error: { message: "No such checkout.session" } }), { status: 404 });
    }
    if (u.host === "resend.test" && u.pathname === "/emails") {
      if (failuresLeft > 0) { failuresLeft--; return new Response("upstream down", { status: 503 }); }
      return ok({ id: `email_${calls.length}` });
    }
    return new Response("unexpected request in test", { status: 599 });
  }
  return { fetch: fetchImpl, calls, sessions };
}

export const WHSEC = "whsec_test_secret_for_unit_tests";

export async function makeEnv(overrides = {}) {
  return {
    DB: fakeD1(),
    STRIPE_SECRET_KEY: "sk_test_dummy",
    STRIPE_API_BASE: "https://stripe.test",
    STRIPE_WEBHOOK_SECRET: WHSEC,
    EMAIL_PROVIDER: "resend",
    RESEND_API_KEY: "re_dummy",
    RESEND_API_BASE: "https://resend.test",
    EMAIL_FROM: "ModelMigrate <licences@example.test>",
    LICENCE_SIGNING_KEY: JSON.stringify(await devSigningKey()),
    ADMIN_TOKEN: "admin-token-that-is-long-enough-123",
    PUBLIC_BASE_URL: "https://licence.example.test",
    ...overrides,
  };
}

export function harness(env, net, { clock } = {}) {
  const app = createApp({ fetch: net.fetch, clock });
  const call = (path, init = {}) => app.fetch(new Request(`https://licence.example.test${path}`, init), env);
  return {
    app, call,
    postJson: (path, data, headers = {}) => call(path, { method: "POST", headers: { "content-type": "application/json", ...headers }, body: JSON.stringify(data) }),
    async webhook(event, { secret = WHSEC, t } = {}) {
      const raw = JSON.stringify(event);
      const sig = await signStripePayload(raw, secret, t);
      return call("/api/stripe/webhook", { method: "POST", headers: { "stripe-signature": sig, "content-type": "application/json" }, body: raw });
    },
  };
}

let evN = 0;
export function paidSessionEvent(id, { email = "buyer@example.com", type = "checkout.session.completed", payment_status = "paid", product = "modelmigrate-repo", pi = "pi_123" } = {}) {
  return {
    id: `evt_${++evN}`, object: "event", type, livemode: false,
    data: { object: { id, object: "checkout.session", mode: "payment", status: "complete", payment_status, customer_details: { email },
      payment_intent: pi, customer: "cus_1", amount_total: 14900, currency: "gbp", livemode: false, metadata: { product } } },
  };
}
