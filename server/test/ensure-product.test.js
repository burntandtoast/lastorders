import test from "node:test";
import assert from "node:assert/strict";
import { ensureProduct } from "../scripts/ensure-product.mjs";

function memoryStripe() {
  const products = [];
  const prices = [];
  let n = 0;
  return {
    products,
    prices,
    async request(method, path, params = {}) {
      if (method === "GET" && path === "/v1/products") {
        return { data: products.filter((p) => p.active), has_more: false };
      }
      if (method === "POST" && path === "/v1/products") {
        const product = { id: `prod_${++n}`, active: true, tax_code: params.tax_code, metadata: params.metadata, name: params.name };
        products.push(product);
        return product;
      }
      const update = path.match(/^\/v1\/products\/(.+)$/);
      if (method === "POST" && update) {
        const product = products.find((row) => row.id === decodeURIComponent(update[1]));
        product.tax_code = params.tax_code;
        return product;
      }
      if (method === "GET" && path === "/v1/prices") {
        return { data: prices.filter((price) => price.product === params.product && price.active), has_more: false };
      }
      if (method === "POST" && path === "/v1/prices") {
        const price = {
          id: `price_${++n}`, active: true, type: "one_time", product: params.product,
          currency: params.currency, unit_amount: Number(params.unit_amount), tax_behavior: params.tax_behavior,
          metadata: params.metadata,
        };
        prices.push(price);
        return price;
      }
      throw new Error(`unexpected ${method} ${path}`);
    },
  };
}

test("ensure-product creates the tax code and inclusive £179 price once", async () => {
  const stripe = memoryStripe();
  const first = await ensureProduct(stripe);
  assert.equal(first.createdProduct, true);
  assert.equal(first.createdPrice, true);
  assert.equal(first.taxCode, "txcd_10202003");
  assert.equal(first.taxBehavior, "inclusive");
  assert.equal(first.unitAmount, 17900);
  assert.equal(first.currency, "gbp");
  assert.equal(stripe.products.length, 1);
  assert.equal(stripe.prices.length, 1);

  stripe.products[0].tax_code = "txcd_10000000";
  const second = await ensureProduct(stripe);
  assert.equal(second.createdProduct, false);
  assert.equal(second.createdPrice, false);
  assert.equal(second.updatedTaxCode, true);
  assert.equal(second.productId, first.productId);
  assert.equal(second.priceId, first.priceId);
  assert.equal(stripe.products[0].tax_code, "txcd_10202003");
  assert.equal(stripe.prices.length, 1);

  // A price's tax behavior cannot be edited, so a non-inclusive price gets a new inclusive one.
  stripe.prices[0].tax_behavior = "exclusive";
  const third = await ensureProduct(stripe);
  assert.equal(third.createdPrice, true);
  assert.equal(third.updatedTaxCode, false);
  assert.notEqual(third.priceId, first.priceId);
  assert.equal(third.taxBehavior, "inclusive");
  assert.equal(stripe.prices.length, 2);
  assert.equal(stripe.products.length, 1);
});
