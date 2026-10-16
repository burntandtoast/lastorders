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

test("pricing button points at the sign-up box while payments are closed", () => {
  const html = readFileSync(new URL("../public/index.html", import.meta.url), "utf8");
  assert.match(html, /href="#remind">Paid fix opens soon · get notified</);
  assert.equal(html.includes('href="/buy"'), false);
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
