// Licence terms, refund policy and the consumer-rights waiver (Consumer Contracts Regulations 2013, reg. 37).
// One place for the wording used at Checkout, on /terms and in the licence email.
export const COMPANY = {
  name: "Burnt and Toast Studios Ltd",
  number: "17334149",
  address: "71-75 Shelton Street, London WC2H 9JQ",
  vat: "Not VAT registered",
  email: "hello@burntandtoast.com",
};
export const TERMS_VERSION = "2026-10-15";
export const COMPANY_LINE = `${COMPANY.name}, company no. ${COMPANY.number}, ${COMPANY.address}. ${COMPANY.vat}.`;
export const REFUND_LINE =
  "Refunds: a full refund on request if your licence key has never been activated. Once activated, a refund if the fix fails on your repo and we can't resolve it within 5 working days.";

// Stripe custom_fields has no checkbox type (text, numeric or dropdown only), and consent_collection.terms_of_service
// needs a Terms URL set in the Stripe Dashboard. A required dropdown with a single, unselected "I agree" option is the
// express-consent box that works today; set STRIPE_TOS_CONSENT="true" once the Dashboard URL is set to use Stripe's
// own terms checkbox instead.
export const WAIVER_FIELD_KEY = "waiver";
export const WAIVER_FIELD = {
  key: WAIVER_FIELD_KEY,
  type: "dropdown",
  optional: false,
  label: { type: "custom", custom: "Immediate supply and your right to cancel" },
  dropdown: { options: [{ label: "I agree to immediate supply and lose my 14-day right to cancel once the key is used", value: "agree" }] },
};

export function submitMessage(baseUrl) {
  const host = String(baseUrl || "https://packs.burntandtoast.com").replace(/^https?:\/\//, "");
  return `Digital licence key, supplied immediately after payment. You asked for immediate supply and agree that you lose your 14-day right to cancel once the key is used (Consumer Contracts Regulations 2013, reg. 37). ${REFUND_LINE} ${COMPANY_LINE} Terms: ${host}/terms`;
}

export function tosAcceptanceMessage(baseUrl) {
  return `I agree to the [licence terms and refund policy](${baseUrl}/terms), to immediate supply of the licence key, and that I lose my 14-day right to cancel once the key is used.`;
}

/** How the buyer consented, read from a completed Checkout Session (null if no consent is recorded). */
export function waiverFromSession(session) {
  const f = (session?.custom_fields || []).find((x) => x.key === WAIVER_FIELD_KEY);
  if (f?.dropdown?.value === "agree") return "checkout_custom_field";
  if (session?.consent?.terms_of_service === "accepted") return "checkout_terms_of_service";
  return null;
}
