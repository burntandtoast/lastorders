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
