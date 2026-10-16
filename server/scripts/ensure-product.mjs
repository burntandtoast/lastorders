// Create or update the Last Orders product and its £149 one-time GBP price.
//
// The product gets tax code txcd_10202003 (Downloadable Software — business use).
// The price is unit_amount 14900, currency gbp, tax_behavior inclusive, so the
// buyer pays £149 in total. Inclusive pricing is allowed with Managed Payments:
// Stripe uses the price's tax_behavior, and if you omit it, tax is added on top.
//
// Idempotent. A second run reuses the product (metadata.product = PRODUCT_CODE)
// and the matching active price. Prices are immutable, so a price with a
// different amount or tax behavior is left in place and a new one is created.
//
//   STRIPE_SECRET_KEY=sk_test_... node scripts/ensure-product.mjs
//
// Prints the price id to set as STRIPE_PRICE_ID. Does not deploy and does not
// read live keys from wrangler. If STRIPE_PRICE_ID is already set on the Worker,
// the Dashboard product behind that price still needs this tax code; this script
// is how to set it.
import { pathToFileURL } from "node:url";
import { Stripe } from "../src/stripe.js";
import {
  MANAGED_PAYMENTS_API_VERSION,
  PRODUCT_DESCRIPTION,
  TAX_BEHAVIOR,
  TAX_CODE,
  checkoutApiVersion,
  licenceProductName,
} from "../src/managed-payments.js";

export async function listAll(stripe, path, params) {
  const out = [];
  let starting_after;
  for (;;) {
    const page = await stripe.request("GET", path, { ...params, limit: 100, starting_after });
    const data = page.data || [];
    out.push(...data);
    if (!page.has_more || !data.length) break;
    starting_after = data[data.length - 1].id;
  }
  return out;
}

function samePrice(price, { currency, unitAmount, taxBehavior }) {
  return price.currency === currency
    && Number(price.unit_amount) === Number(unitAmount)
    && price.tax_behavior === taxBehavior
    && (price.type === "one_time" || !price.recurring);
}

/**
 * @param {import("../src/stripe.js").Stripe} stripe
 * @returns {Promise<{productId: string, priceId: string, createdProduct: boolean, createdPrice: boolean, updatedTaxCode: boolean, taxCode: string, taxBehavior: string, unitAmount: number, currency: string}>}
 */
export async function ensureProduct(stripe, opts = {}) {
  const productCode = opts.productCode || "lastorders-repo";
  const name = opts.name || licenceProductName(opts.productName || "Last Orders");
  const description = opts.description || PRODUCT_DESCRIPTION;
  const taxCode = opts.taxCode || TAX_CODE;
  const currency = (opts.currency || "gbp").toLowerCase();
  const unitAmount = Number(opts.unitAmount ?? 14900);
  const taxBehavior = opts.taxBehavior || TAX_BEHAVIOR;
  if (taxBehavior !== "inclusive" && taxBehavior !== "exclusive") {
    throw new Error(`tax_behavior must be inclusive or exclusive, got ${taxBehavior}`);
  }

  const products = await listAll(stripe, "/v1/products", { active: true });
  let product = products.find((p) => p.metadata?.product === productCode);
  let createdProduct = false;
  let updatedTaxCode = false;
  if (!product) {
    product = await stripe.request("POST", "/v1/products", {
      name, description, tax_code: taxCode, metadata: { product: productCode },
    });
    createdProduct = true;
  } else if (product.tax_code !== taxCode) {
    product = await stripe.request("POST", `/v1/products/${encodeURIComponent(product.id)}`, { tax_code: taxCode });
    updatedTaxCode = true;
  }

  const prices = await listAll(stripe, "/v1/prices", { product: product.id, active: true });
  let price = prices.find((p) => samePrice(p, { currency, unitAmount, taxBehavior }));
  let createdPrice = false;
  if (!price) {
    price = await stripe.request("POST", "/v1/prices", {
      product: product.id,
      currency,
      unit_amount: unitAmount,
      tax_behavior: taxBehavior,
      metadata: { product: productCode },
    });
    createdPrice = true;
  }

  return {
    productId: product.id,
    priceId: price.id,
    createdProduct,
    createdPrice,
    updatedTaxCode,
    taxCode,
    taxBehavior,
    unitAmount,
    currency,
  };
}

async function main() {
  const secret = process.env.STRIPE_SECRET_KEY || "";
  if (!secret) {
    console.error("Set STRIPE_SECRET_KEY (sk_test_... or sk_live_...). This script does not deploy.");
    process.exit(1);
  }
  const apiVersion = checkoutApiVersion(process.env.STRIPE_API_VERSION || MANAGED_PAYMENTS_API_VERSION);
  const stripe = new Stripe({
    secretKey: secret,
    apiBase: process.env.STRIPE_API_BASE || "https://api.stripe.com",
    apiVersion,
  });
  const result = await ensureProduct(stripe, {
    productCode: process.env.PRODUCT_CODE,
    productName: process.env.PRODUCT_NAME,
    currency: process.env.CURRENCY,
    unitAmount: process.env.PRICE_AMOUNT ? Number.parseInt(process.env.PRICE_AMOUNT, 10) : undefined,
  });
  console.error(`# product ${result.productId} tax_code=${result.taxCode} (${result.createdProduct ? "created" : result.updatedTaxCode ? "tax code updated" : "unchanged"})`);
  console.error(`# price ${result.priceId} ${result.unitAmount} ${result.currency} tax_behavior=${result.taxBehavior} (${result.createdPrice ? "created" : "unchanged"})`);
  console.error("# Inclusive tax is included in the unit amount. Managed Payments allows it;");
  console.error("# omitting tax_behavior makes Managed Payments add tax on top of the price.");
  console.error("# Set STRIPE_PRICE_ID to the next line. Do not commit the secret key.");
  console.log(result.priceId);
}

const invoked = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (invoked) {
  main().catch((err) => {
    console.error(err?.message || err);
    process.exit(1);
  });
}
