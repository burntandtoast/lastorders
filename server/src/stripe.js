// Minimal Stripe client over fetch (no SDK): easy to mock, small bundle.
import { enc, hex, timingSafeEqual } from "./util.js";

export class StripeError extends Error {
  constructor(message, status, body) { super(message); this.status = status; this.body = body; }
}

// Flatten nested objects into Stripe's form encoding: a[b][0][c]=v
export function formEncode(obj, prefix = "", out = new URLSearchParams()) {
  for (const [k, v] of Object.entries(obj)) {
    if (v === undefined || v === null) continue;
    const name = prefix ? `${prefix}[${k}]` : k;
    if (Array.isArray(v)) v.forEach((item, i) => (typeof item === "object" ? formEncode(item, `${name}[${i}]`, out) : out.append(`${name}[${i}]`, String(item))));
    else if (typeof v === "object") formEncode(v, name, out);
    else out.append(name, String(v));
  }
  return out;
}

export class Stripe {
  constructor({ secretKey, apiBase = "https://api.stripe.com", apiVersion = "", fetchImpl = fetch }) {
    if (!secretKey) throw new StripeError("STRIPE_SECRET_KEY is not configured", 500);
    this.secretKey = secretKey;
    this.apiBase = apiBase.replace(/\/$/, "");
    this.apiVersion = apiVersion;
    this.fetch = fetchImpl;
  }

  get testMode() { return this.secretKey.startsWith("sk_test_") || this.secretKey.startsWith("rk_test_"); }

  async request(method, path, params, opts = {}) {
    // The fourth argument used to be an idempotency-key string.
    const idempotencyKey = typeof opts === "string" ? opts : opts.idempotencyKey;
    const apiVersion = (typeof opts === "string" ? "" : opts.apiVersion) || this.apiVersion;
    const headers = { authorization: `Bearer ${this.secretKey}` };
    if (apiVersion) headers["stripe-version"] = apiVersion;   // default: the account's pinned version
    let url = `${this.apiBase}${path}`;
    let body;
    if (params && method === "GET") url += `?${formEncode(params)}`;
    else if (params) { body = formEncode(params).toString(); headers["content-type"] = "application/x-www-form-urlencoded"; }
    if (idempotencyKey) headers["idempotency-key"] = idempotencyKey;
    const res = await this.fetch(url, { method, headers, body });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new StripeError(data?.error?.message || `Stripe ${res.status}`, res.status, data);
    return data;
  }

  createCheckoutSession(params, opts) { return this.request("POST", "/v1/checkout/sessions", params, opts); }
  retrieveCheckoutSession(id) { return this.request("GET", `/v1/checkout/sessions/${encodeURIComponent(id)}`); }
}

/**
 * Verify a Stripe-Signature header (t=...,v1=...[,v1=...][,v0=...]) against the raw body.
 * Only v1 is accepted (downgrade protection); tolerance defaults to Stripe's 300 s.
 * Several secrets may be given (comma-separated) to cover a secret roll.
 */
export async function verifyStripeSignature(rawBody, header, secrets, { tolerance = 300, now = Date.now() } = {}) {
  if (!header) return { ok: false, reason: "missing Stripe-Signature header" };
  let t = null;
  const v1 = [];
  for (const part of header.split(",")) {
    const i = part.indexOf("=");
    if (i < 0) continue;
    const k = part.slice(0, i).trim(), v = part.slice(i + 1).trim();
    if (k === "t") t = v;
    else if (k === "v1") v1.push(v);
  }
  if (!t || !/^\d+$/.test(t) || !v1.length) return { ok: false, reason: "malformed Stripe-Signature header" };
  const list = (Array.isArray(secrets) ? secrets : String(secrets || "").split(",")).map((s) => s.trim()).filter(Boolean);
  if (!list.length) return { ok: false, reason: "STRIPE_WEBHOOK_SECRET is not configured" };
  for (const secret of list) {
    const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    const expected = hex(await crypto.subtle.sign("HMAC", key, enc.encode(`${t}.${rawBody}`)));
    if (v1.some((s) => timingSafeEqual(s, expected))) {
      if (tolerance > 0 && Math.abs(now / 1000 - Number(t)) > tolerance) return { ok: false, reason: "timestamp outside tolerance" };
      return { ok: true, timestamp: Number(t) };
    }
  }
  return { ok: false, reason: "no matching v1 signature" };
}

/** Build a Stripe-Signature header (tests and local tooling only). */
export async function signStripePayload(rawBody, secret, t = Math.floor(Date.now() / 1000)) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return `t=${t},v1=${hex(await crypto.subtle.sign("HMAC", key, enc.encode(`${t}.${rawBody}`)))}`;
}
