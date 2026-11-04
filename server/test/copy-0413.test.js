import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { WAIVER_FIELD } from "../src/terms.js";
import { PRODUCT_DESCRIPTION } from "../src/managed-payments.js";
import { cancelPage } from "../src/pages.js";

test("waiver dropdown: clearer copy, same key/value and still required", () => {
  assert.equal(WAIVER_FIELD.label.custom, "Before you pay: your right to cancel");
  assert.ok(WAIVER_FIELD.label.custom.length <= 50);
  const [opt] = WAIVER_FIELD.dropdown.options;
  assert.equal(WAIVER_FIELD.dropdown.options.length, 1);
  assert.equal(opt.value, "agree");
  assert.ok(opt.label.length <= 100);
  assert.equal(WAIVER_FIELD.optional, false);
});

test("checkout description says one-off, tax included", () => {
  assert.match(PRODUCT_DESCRIPTION, /^A reviewable patch plus a must-review list for one GitHub repo/);
  assert.match(PRODUCT_DESCRIPTION, /One-off, tax included\.$/);
});

test("cancel page offers a person to email", async () => {
  const res = cancelPage({ productName: "Last Orders", baseUrl: "https://lastorders.example" });
  const html = typeof res === "string" ? res : await res.text();
  assert.match(html, /Questions before you buy\? Email <a href="mailto:hello@burntandtoast.com">/);
});

test("replies and support go to hello@", () => {
  const toml = readFileSync(new URL("../wrangler.toml", import.meta.url), "utf8");
  assert.match(toml, /^EMAIL_REPLY_TO = "hello@burntandtoast.com"$/m);
  assert.match(toml, /^SUPPORT_EMAIL = "hello@burntandtoast.com"$/m);
});
