// Stripe Managed Payments: Link is the merchant of record.
//
// Disallowed Checkout Session parameters are the union of the one-time and
// subscription tables on
// https://docs.stripe.com/payments/managed-payments/update-checkout
// (fetched 2026-10-16). This product is mode=payment; subscription keys are
// stripped too so a later edit cannot send them.
//
// Kept on purpose. They are not in that table, and How Managed Payments works
// still lets you add your own terms of service in Checkout settings:
//   consent_collection, custom_fields
// custom_text IS rejected on Checkout Sessions too ("You cannot use custom_text
// with Managed Payments", sandbox probe 2026-10-16), so it is stripped. The
// 14-day waiver stays on the Stripe page as the required custom_fields dropdown.
//
// Not stripped. The Managed Payments changelog allows them, and the
// update-checkout table does not list them:
//   payment_method_collection, payment_method_options, saved_payment_method_options
//
// tax_behavior "inclusive" is allowed. Managed Payments uses the price's tax
// behavior. If it is omitted, tax is added on top of the price, so the buyer
// would pay more than the unit amount.

export const MANAGED_PAYMENTS_API_VERSION = "2025-03-31.basil";

/** Downloadable Software — business use. Eligible for Managed Payments. */
export const TAX_CODE = "txcd_10202003";

/** Tax is included in the unit amount, so a £179 price charges £179 in total. */
export const TAX_BEHAVIOR = "inclusive";

export const PRODUCT_DESCRIPTION =
  "Automatic fixes, verified patches and client reports for one repo (monorepos count as one).";

export function licenceProductName(productName) {
  return `${productName} licence: one repository`;
}

export const DISALLOWED_CHECKOUT_PARAMS = [
  "automatic_tax",
  "tax_id_collection",
  "adaptive_pricing",
  "excluded_payment_method_types",
  "payment_method_configuration",
  "payment_method_types",
  "shipping_address_collection",
  "shipping_options",
  "invoice_creation",
  "custom_text",
];

/** customer_update[name] and customer_update[address]. */
export const DISALLOWED_CUSTOMER_UPDATE_KEYS = ["name", "address"];

export const DISALLOWED_PAYMENT_INTENT_KEYS = [
  "shipping",
  "application_fee_amount",
  "on_behalf_of",
  "transfer_data",
  "transfer_group",
  "statement_descriptor",
  "statement_descriptor_suffix",
  "receipt_email",
];

export const DISALLOWED_SUBSCRIPTION_DATA_KEYS = [
  "default_tax_rates",
  "application_fee_percent",
  "on_behalf_of",
  "transfer_data",
  "invoice_settings",
];

/** Stripe-Version for a Managed Payments Checkout Session: the pin, or a later explicit version. */
export function checkoutApiVersion(configured) {
  const v = String(configured || "").trim();
  const date = v.slice(0, 10);
  if (/^\d{4}-\d{2}-\d{2}$/.test(date) && date >= "2025-03-31") return v;
  return MANAGED_PAYMENTS_API_VERSION;
}

function stripKeys(obj, keys) {
  if (!obj || typeof obj !== "object") return;
  for (const key of keys) delete obj[key];
}

/** Enable Managed Payments and drop every parameter the Checkout table disallows. */
export function applyManagedPayments(params) {
  params.managed_payments = { enabled: true };
  for (const key of DISALLOWED_CHECKOUT_PARAMS) delete params[key];
  if (params.customer_update) {
    stripKeys(params.customer_update, DISALLOWED_CUSTOMER_UPDATE_KEYS);
    if (!Object.keys(params.customer_update).length) delete params.customer_update;
  }
  if (params.payment_intent_data) stripKeys(params.payment_intent_data, DISALLOWED_PAYMENT_INTENT_KEYS);
  if (params.subscription_data) {
    stripKeys(params.subscription_data, DISALLOWED_SUBSCRIPTION_DATA_KEYS);
    if (!Object.keys(params.subscription_data).length) delete params.subscription_data;
  }
  return params;
}
