import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import worker from "../src/worker.js";

function env(overrides = {}) {
  return {
    ASSETS: { fetch: async () => new Response("asset", { status: 200 }) },
    LICENCE: { fetch: async (request) => new Response(`licence:${new URL(request.url).pathname}`, { status: 200 }) },
    ...overrides,
  };
}

test("pricing button points at checkout now payments are open", () => {
  const html = readFileSync(new URL("../public/index.html", import.meta.url), "utf8");
  assert.match(html, /href="\/buy">Buy a licence · £179</);
});

test("sub-nav, footer and past-deadline badges, with the Gemini API card unchanged", () => {
  const html = readFileSync(new URL("../public/index.html", import.meta.url), "utf8");
  assert.match(html, /href="#licence">The patch</);
  assert.match(html, /href="#pricing">Get the patch · £179</);
  assert.match(html, /href="https:\/\/fieldwork\.burntandtoast\.com\/\?utm_source=lastorders&amp;utm_medium=footer"[^>]*>/);
  assert.match(html, /<span class="foot-label">AI Fieldwork<\/span><span class="foot-desc">A practical AI course<\/span>/);
  assert.match(html, /burntandtoast\/lastorders@v0\.4\.14/);
  assert.equal((html.match(/<span class="next passed">Passed<\/span>/g) || []).length, 2);
  assert.match(html, /<span class="next">Next up<\/span><b>30 Nov 2026</);
  assert.doesNotMatch(html, /That's days away/);
  const dec = html.slice(html.indexOf("<b>1 Dec 2026</b>"), html.indexOf("<b>1 Dec 2026</b>") + 700);
  assert.match(dec, /automatically routes the request and bills the replacement/);
  assert.match(dec, /gemini-2\.5-pro<\/code> routes to <code>gemini-3\.8-flash/);
});

test("/buy redirects to #remind until BUY_OPEN=1", async () => {
  const closed = await worker.fetch(new Request("https://lastorders.example/buy?repo=github.com/acme/shop"), env());
  assert.equal(closed.status, 302);
  assert.equal(closed.headers.get("location"), "https://lastorders.example/#remind");

  const slashed = await worker.fetch(new Request("https://lastorders.example/buy/"), env({ BUY_OPEN: "0" }));
  assert.equal(slashed.status, 302);
  assert.equal(slashed.headers.get("location"), "https://lastorders.example/#remind");

  const open = await worker.fetch(new Request("https://lastorders.example/buy?repo=github.com/acme/shop"), env({ BUY_OPEN: "1" }));
  assert.equal(open.status, 200);
  assert.equal(await open.text(), "licence:/buy");
});

test("terms, success and cancel still reach the licence Worker", async () => {
  for (const path of ["/terms", "/success", "/cancel"]) {
    const res = await worker.fetch(new Request(`https://lastorders.example${path}`), env());
    assert.equal(res.status, 200);
    assert.equal(await res.text(), `licence:${path}`);
  }
});

test("head carries a large share image for LinkedIn and X", () => {
  const html = readFileSync(new URL("../public/index.html", import.meta.url), "utf8");
  const head = html.slice(0, html.indexOf("</head>"));
  const meta = (attr, key) => head.match(new RegExp(`<meta ${attr}="${key}" content="([^"]*)">`))?.[1];
  assert.equal(meta("property", "og:image"), "https://lastorders.burntandtoast.com/og.png");
  assert.equal(meta("property", "og:image:type"), "image/png");
  assert.equal(meta("property", "og:image:width"), "1200");
  assert.equal(meta("property", "og:image:height"), "630");
  assert.ok(meta("property", "og:image:alt")?.length > 20);
  assert.equal(meta("name", "twitter:card"), "summary_large_image");
  assert.equal(meta("name", "twitter:image"), "https://lastorders.burntandtoast.com/og.png");
  assert.ok(meta("name", "twitter:image:alt")?.length > 20);
  const png = readFileSync(new URL("../public/og.png", import.meta.url));
  assert.equal(png.readUInt32BE(16), 1200);
  assert.equal(png.readUInt32BE(20), 630);
  assert.ok(png.length < 300 * 1024);
});

test("/faq redirects (301) to the FAQ section on the home page", async () => {
  const html = readFileSync(new URL("../public/index.html", import.meta.url), "utf8");
  assert.match(html, /<section id="faq">/);
  for (const path of ["/faq", "/faq/"]) {
    const res = await worker.fetch(new Request(`https://lastorders.example${path}`), env());
    assert.equal(res.status, 301);
    assert.equal(res.headers.get("location"), "https://lastorders.example/#faq");
  }
  const toml = readFileSync(new URL("../wrangler.toml", import.meta.url), "utf8");
  assert.match(toml, /run_worker_first = \[[^\]]*"\/faq"/);
});

test("post-scan Brief is the only button; Listing Writer is a quiet sentence under it", () => {
  const html = readFileSync(new URL("../public/index.html", import.meta.url), "utf8");
  const brief = html.slice(html.indexOf('<section id="brief"'), html.indexOf('<section class="contact">'));
  const hrefs = [...brief.matchAll(/href="([^"]+)"/g)].map((m) => m[1].replaceAll("&amp;", "&"));
  assert.deepEqual(hrefs, [
    "https://burntandtoast.com/brief/lo?utm_source=lastorders&utm_medium=web&utm_campaign=lo-scan-brief-2026-11&utm_content=post-scan",
    "https://kits.burntandtoast.com/estate-agents/kits/listing-writer?utm_source=lastorders&utm_medium=web&utm_campaign=lo-scan-brief-2026-11&utm_content=listing-writer",
  ]);
  assert.match(brief, /<h2 id="brief-title">Scan done\. Want the next one\?<\/h2>/);
  assert.match(brief, /The Burnt Brief is the studio’s free Monday note on AI that actually ships — retiring models, tools you can run yourself, and the odd kit when it’s useful\. No spam\./);
  assert.match(brief, /<a class="btn" href="[^"]+">Get The Burnt Brief<\/a>/);
  assert.match(brief, /<p class="brief-also"><a href="[^"]+">Writing Rightmove copy after the scan\? Listing Writer turns a fact sheet into portal-ready wording with a compliance check — £29, instant download\.<\/a><\/p>/);
  assert.equal((brief.match(/class="btn"/g) || []).length, 1);
  assert.doesNotMatch(brief, /waitlist/i);
  assert.ok(brief.indexOf('class="btn"') < brief.indexOf('class="brief-also"'));
});

test("public pages have a self-canonical; robots.txt points at sitemap.xml, which lists only public pages", () => {
  const read = (f) => readFileSync(new URL(`../public/${f}`, import.meta.url), "utf8");
  assert.match(read("index.html"), /<link rel="canonical" href="https:\/\/lastorders\.burntandtoast\.com\/">/);
  assert.match(read("client-report-sample.html"), /<link rel='canonical' href='https:\/\/lastorders\.burntandtoast\.com\/client-report-sample'>/);
  assert.match(read("robots.txt"), /^Sitemap: https:\/\/lastorders\.burntandtoast\.com\/sitemap\.xml$/m);
  assert.match(read("robots.txt"), /^Disallow: \/buy$/m);
  const locs = [...read("sitemap.xml").matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
  assert.deepEqual(locs, ["https://lastorders.burntandtoast.com/", "https://lastorders.burntandtoast.com/client-report-sample", "https://lastorders.burntandtoast.com/terms"]);
});
