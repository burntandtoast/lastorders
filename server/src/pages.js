// Tiny server-rendered pages for the Checkout return URLs.
import { escapeHtml } from "./util.js";
import { COMPANY, TERMS_VERSION } from "./terms.js";

function page(title, body, status = 200, { index = false } = {}) {
  return new Response(`<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
${index ? "" : '<meta name="robots" content="noindex">'}<title>${escapeHtml(title)}</title>
<style>body{font:16px/1.55 system-ui,sans-serif;max-width:640px;margin:48px auto;padding:0 20px;color:#1b1b1b}
code,pre,.key{font-family:ui-monospace,Menlo,monospace}.key{font-size:22px;font-weight:600;background:#f4f1ea;padding:12px 16px;border-radius:6px;display:inline-block;user-select:all}
pre{background:#f4f1ea;padding:12px 16px;border-radius:6px;overflow:auto}.muted{color:#666;font-size:14px}</style></head>
<body>${body}</body></html>`, { status, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store", "referrer-policy": "no-referrer" } });
}

export function successPage({ key, email, productName, cliName, baseUrl }) {
  return page(`Your ${productName} licence`, `<h1>Thanks — you're licensed</h1>
<p>Your licence key:</p><p class="key">${escapeHtml(key)}</p>
<p>We're also emailing it to <strong>${escapeHtml(email)}</strong>. It covers one repository (a monorepo counts as one), bound the first time you use it.</p>
<pre>export LASTORDERS_LICENCE=${escapeHtml(key)}
${escapeHtml(cliName)} fix . --verify --apply</pre>
<p>In GitHub Actions, add it as a repository secret named <code>LASTORDERS_LICENCE</code>.</p>
<p class="muted">Keep this key private. <a href="${escapeHtml(baseUrl)}">Back to ${escapeHtml(productName)}</a></p>`);
}

export function pendingPage({ productName }) {
  return page(`${productName}: payment processing`, `<h1>Payment processing</h1>
<p>Your payment hasn't cleared yet (some payment methods take a little while). We'll email your licence key as soon as it does.</p>`, 202);
}

export function cancelPage({ productName, baseUrl }) {
  return page(`${productName}: checkout cancelled`, `<h1>Checkout cancelled</h1><p>No payment was taken. The free scan keeps working without a licence.</p>
<p><a href="${escapeHtml(baseUrl)}">Back to ${escapeHtml(productName)}</a></p>`);
}

export function errorPage(message, status = 400) {
  return page("Something went wrong", `<h1>Something went wrong</h1><p>${escapeHtml(message)}</p>`, status);
}

export function termsPage({ productName, cliName, amount, currency, baseUrl }) {
  const price = currency === "gbp" ? `£${(amount / 100).toFixed(2).replace(/\.00$/, "")}` : `${(amount / 100).toFixed(2)} ${currency.toUpperCase()}`;
  const e = escapeHtml, mail = `<a href="mailto:${e(COMPANY.email)}">${e(COMPANY.email)}</a>`;
  return page(`${productName}: licence terms and refund policy`, `<h1>${e(productName)}: licence terms and refund policy</h1>
<p class="muted">Version ${e(TERMS_VERSION)}. These terms apply to ${e(productName)} licences bought at ${e(baseUrl || "")}/buy.</p>
<h2>Who we are</h2>
<p>${e(COMPANY.name)}, a company registered in England and Wales, company no. ${e(COMPANY.number)}. Registered office: ${e(COMPANY.address)}. ${e(COMPANY.vat)}. Contact: ${mail}.</p>
<h2>What you get</h2>
<ul><li>A licence key for one GitHub repository (a monorepo counts as one), for ${e(price)}, paid once.</li>
<li>The repository is bound to the key the first time the key is used (activated) with the <code>${e(cliName)}</code> tool. We can move a licence to another repository on request, for example after a rename or transfer.</li>
<li>The licence unlocks the paid features (automatic fixes, verified patches and reports) for that repository, including updates for future model retirements. The free scan never needs a licence.</li>
<li>The key is for your organisation's use on that repository. Please don't share it for use on other repositories.</li></ul>
<h2>Refund policy</h2>
<ul><li><b>Never activated:</b> a full refund on request, as long as the licence key has never been activated (we record when it is first used).</li>
<li><b>Activated:</b> a refund if the fix fails on your repository and we can't resolve it within 5 working days of you telling us.</li></ul>
<p>To ask for a refund, email ${mail} with your licence key or the email address you paid with. Refunds go back to the original payment method. A refunded licence stops working.</p>
<h2>Your right to cancel (consumers)</h2>
<p>If you buy as a consumer, you would normally have 14 days to cancel. Because the licence key is digital content supplied straight away, at checkout you expressly ask for immediate supply and acknowledge that you lose the 14-day right to cancel once the key is used (Consumer Contracts Regulations 2013, regulation 37). Until the key is used, you can cancel and get a full refund. The refund policy above still applies after that. Businesses have no statutory cooling-off right; the refund policy above applies to them too.</p>
<p>Nothing in these terms affects your statutory rights, for example if the licence or the software isn't as described.</p>
<h2>Liability</h2>
<p>${e(productName)} proposes code changes for you to review. You're responsible for reviewing, testing and deploying them. Our total liability for a licence is limited to the price you paid for it, except where the law doesn't allow liability to be limited.</p>
<h2>Governing law</h2>
<p>These terms are governed by the law of England and Wales, and the courts of England and Wales have jurisdiction. If you're a consumer living in Scotland or Northern Ireland, you can also bring proceedings in your local courts.</p>
<p class="muted">Questions: ${mail}. ${e(COMPANY.name)}, ${e(COMPANY.address)}.</p>`, 200, { index: true });
}
