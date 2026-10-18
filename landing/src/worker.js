// Landing page Worker for lastorders.burntandtoast.com.
// Static files come from ./public (Workers assets). The only dynamic route is POST /subscribe, the
// "Remind me" form: it adds the address to Buttondown tagged lastorders-waitlist, the same way the
// Kits site does (cloudflare/handlers.js in the burntandtoast site). Secret: BUTTONDOWN_API_KEY.
const TAG = "lastorders-waitlist";
const LICENCE_PATHS = new Set(["/buy", "/terms", "/success", "/cancel"]);
const EMAIL_RE = /^[^\s@<>()",;:]+@[^\s@<>()",;:]+\.[^\s@<>()",;:]{2,}$/;
const MSG = {
  ok: "Thanks, you're on the list. Check your inbox for a confirmation email from Burnt & Toast.",
  invalid: "Please enter a valid email address.",
  down: "Sorry, sign-ups aren't working right now. Please email hello@burntandtoast.com instead.",
};

const json = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

// No-JS fallback: a small page in the landing page's colours with the message and a link back.
function htmlResult(ok, message, status) {
  return new Response(`<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>Last Orders</title>
<style>body{margin:0;background:#fbf5ea;color:#2a1d14;font:17px/1.6 Georgia,serif}main{max-width:560px;margin:80px auto;padding:0 22px}
h1{font:700 26px/1.2 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;color:${ok ? "#3f6b3a" : "#a2461f"}}a{color:#8a4b22}</style></head>
<body><main><h1>${ok ? "You're on the list" : "That didn't work"}</h1><p>${esc(message)}</p><p><a href="/#remind">Back to Last Orders</a></p></main></body></html>`,
    { status, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
}

async function readForm(request) {
  const type = request.headers.get("content-type") || "";
  if (Number(request.headers.get("content-length") || 0) > 4096) return null;
  try {
    if (type.includes("application/json")) return await request.json();
    if (type.includes("form")) return Object.fromEntries(await request.formData());
  } catch {}
  return null;
}

async function subscribe(request, env) {
  const wantsJson = (request.headers.get("accept") || "").includes("application/json");
  const reply = (ok, message, status) => (wantsJson ? json(ok ? { ok, message } : { ok, error: message }, status) : htmlResult(ok, message, status));
  const body = await readForm(request);
  if (!body) return reply(false, MSG.invalid, 400);
  // Honeypot: a field people never see. Bots that fill it get a normal-looking success and nothing is stored.
  if (String(body.website || "").trim()) return reply(true, MSG.ok, 200);
  const email = String(body.email || "").trim().toLowerCase();
  if (!EMAIL_RE.test(email) || email.length > 254) return reply(false, MSG.invalid, 400);
  if (!env.BUTTONDOWN_API_KEY) { console.error("[subscribe] BUTTONDOWN_API_KEY not set"); return reply(false, MSG.down, 503); }
  try {
    const r = await fetch("https://api.buttondown.com/v1/subscribers", {
      method: "POST",
      headers: { Authorization: `Token ${env.BUTTONDOWN_API_KEY}`, "content-type": "application/json", "X-Buttondown-Collision-Behavior": "add" },
      body: JSON.stringify({ email_address: email, tags: [TAG], referrer_url: request.headers.get("referer") || "https://lastorders.burntandtoast.com", ip_address: request.headers.get("cf-connecting-ip") || undefined }),
    });
    if (r.ok || r.status === 409) return reply(true, MSG.ok, 200);
    const text = (await r.text()).slice(0, 300);
    console.error("[subscribe] buttondown", r.status, text);
    if (r.status === 400 || r.status === 422) return reply(false, MSG.invalid, 400);   // Buttondown rejected the address
    return reply(false, MSG.down, 502);
  } catch (e) {
    console.error("[subscribe] buttondown", e?.message || e);
    return reply(false, MSG.down, 502);
  }
}

// Studio stylesheets, fonts and logo, proxied from burntandtoast.com so they load from this origin
// (no extra DNS/TLS connection before first paint). Allowlisted; short CSS cache so studio updates show quickly.
const STUDIO_ORIGIN = "https://burntandtoast.com";
const STUDIO_ASSETS = new Map([
  ["chrome.css", 600], ["site.css", 600], ["logo.svg", 86400],
  ["fonts/bricolage-grotesque-latin.woff2", 86400], ["fonts/NothingYouCouldDo-Regular.ttf", 86400],
]);
async function studioAsset(url, request) {
  const rel = url.pathname.slice("/studio-assets/".length);
  const ttl = STUDIO_ASSETS.get(rel);
  if (!ttl || (request.method !== "GET" && request.method !== "HEAD")) return new Response("Not found", { status: 404 });
  const upstream = await fetch(`${STUDIO_ORIGIN}/assets/${rel}`, { cf: { cacheEverything: true, cacheTtl: ttl } });
  if (!upstream.ok) return new Response("Upstream error", { status: 502 });
  const headers = new Headers();
  for (const h of ["content-type", "etag", "last-modified"]) if (upstream.headers.get(h)) headers.set(h, upstream.headers.get(h));
  headers.set("cache-control", `public, max-age=${ttl}`);
  headers.set("access-control-allow-origin", "*");
  return new Response(request.method === "HEAD" ? null : upstream.body, { status: 200, headers });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/subscribe") {
      if (request.method === "POST") return subscribe(request, env);
      return Response.redirect(`${url.origin}/#remind`, 303);
    }
    // The studio-styled preview became the live page on 15 Oct 2026.
    if (url.pathname === "/preview" || url.pathname.startsWith("/preview/")) {
      return new Response(null, { status: 301, headers: { location: `${url.origin}/${url.search}` } });
    }
    if (url.pathname.startsWith("/studio-assets/")) return studioAsset(url, request);
    // The FAQ is a section of the home page, not its own page.
    if (url.pathname === "/faq" || url.pathname === "/faq/") {
      return new Response(null, { status: 301, headers: { location: `${url.origin}/#faq` } });
    }
    // Customer-facing licence pages are served by the licence Worker (service binding), on this host.
    const path = url.pathname.replace(/\/+$/, "") || "/";
    // Until live payments are switched on (env BUY_OPEN = "1"), /buy goes to the sign-up box instead of checkout.
    if (path === "/buy" && env.BUY_OPEN !== "1") return Response.redirect(`${url.origin}/#remind`, 302);
    if (LICENCE_PATHS.has(path)) return env.LICENCE.fetch(request);
    return env.ASSETS.fetch(request);
  },
};
