// Tiny server-rendered pages for the Checkout return URLs.
import { escapeHtml } from "./util.js";
import { COMPANY, TERMS_VERSION } from "./terms.js";

// Studio chrome: the same header, footer, stylesheets, logo and favicon as burntandtoast.com (loaded from the
// studio site, which serves them with CORS). Page bodies use the Kits ".prose" pattern.
const STUDIO = "https://burntandtoast.com";
export const LANDING_URL = "https://lastorders.burntandtoast.com";
const BRAND_SVG = `<svg viewBox="40 40 220 220" aria-hidden="true" focusable="false"><defs><linearGradient id="hm-char" x1="0.2" y1="0.95" x2="0.95" y2="0.05"><stop offset="0%" stop-color="#4A1E0C" stop-opacity="0"/><stop offset="22%" stop-color="#4A1E0C" stop-opacity="0.92"/><stop offset="58%" stop-color="#8A3A1E"/><stop offset="84%" stop-color="#C4551F"/><stop offset="100%" stop-color="#F0873A"/></linearGradient><clipPath id="hm-clip"><path d="M82 250 Q72 250 72 240 L72 138 C40 132 40 92 66 76 C88 62 112 56 150 56 C188 56 212 62 234 76 C260 92 260 132 228 138 L228 240 Q228 250 218 250 Z"/></clipPath></defs><g class="mark-slice"><g clip-path="url(#hm-clip)"><path d="M300 214 C262 208 252 178 234 161 C216 144 208 127 191 111 C175 95 160 85 149 62 C141 45 138 25 133 0 L300 0 Z" fill="url(#hm-char)"/><path d="M300 214 C262 208 252 178 234 161 C216 144 208 127 191 111 C175 95 160 85 149 62 C141 45 138 25 133 0" fill="none" stroke="#F0873A" stroke-width="5" stroke-opacity="0.6"/></g><path d="M82 250 Q72 250 72 240 L72 138 C40 132 40 92 66 76 C88 62 112 56 150 56 C188 56 212 62 234 76 C260 92 260 132 228 138 L228 240 Q228 250 218 250 Z" fill="none" stroke="#2B1D14" stroke-width="13" stroke-linejoin="round" stroke-linecap="round"/></g></svg>`;
const HEADER = `<header class="site-head"><div class="head-row">
<a class="brand" href="${STUDIO}/" aria-label="Burnt and Toast Studios, home">${BRAND_SVG}<span>Burnt &amp; Toast</span></a>
<nav class="nav" aria-label="Main"><ul class="nav-wide">
<li><a href="${STUDIO}/#games">Games</a></li><li><a href="${STUDIO}/#studio">Studio</a></li><li><a href="${STUDIO}/blog">Journal</a></li>
<li><a class="nav-play" href="${LANDING_URL}/">Last Orders</a></li><li><a class="nav-hello" href="${STUDIO}/#contact">Say hello</a></li></ul>
<details class="menu"><summary><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><path d="M4 7 H20 M4 12 H20 M4 17 H20" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/></svg><span>Menu</span></summary>
<ul><li><a class="menu-play" href="${LANDING_URL}/">Last Orders</a></li><li><a href="${STUDIO}/#games">Games</a></li><li><a href="${STUDIO}/#studio">Studio</a></li><li><a href="${STUDIO}/blog">Journal</a></li><li><a href="${STUDIO}/#contact">Say hello</a></li></ul></details>
</nav></div></header>`;
const FOOTER = `<footer class="site-foot"><div class="foot-wrap"><div class="foot-top">
<div class="foot-brand"><img src="${STUDIO}/assets/logo.svg" alt="" width="84" height="84"><p>Burnt &amp; Toast<span class="signoff">Burnt at the edges. Still good.</span></p></div>
<div class="foot-cols">
<nav aria-labelledby="f-lo"><h2 id="f-lo">Last Orders</h2><ul><li><a href="${LANDING_URL}/#scan">Free scan</a></li><li><a href="${LANDING_URL}/#pricing">Pricing</a></li><li><a href="https://github.com/burntandtoast/lastorders" rel="noopener">Source on GitHub</a></li><li><a href="mailto:${COMPANY.email}">${COMPANY.email}</a></li></ul></nav>
<nav aria-labelledby="f-studio"><h2 id="f-studio">Studio</h2><ul><li><a href="${STUDIO}/">burntandtoast.com</a></li><li><a href="${STUDIO}/blog">Journal</a></li><li><a href="https://kits.burntandtoast.com/">Kits</a></li></ul></nav>
<nav aria-labelledby="f-legal"><h2 id="f-legal">Legal</h2><ul><li><a href="/terms">Last Orders terms and refunds</a></li><li><a href="${STUDIO}/privacy/">Website privacy</a></li><li><a href="${STUDIO}/legal/">All privacy policies</a></li></ul></nav>
</div></div>
<div class="foot-bottom"><p>© 2026 Burnt &amp; Toast Studios Ltd.<br>Registered in the United Kingdom, company no. ${COMPANY.number}.<br>71-75 Shelton Street, London, WC2H 9JQ.</p><a href="#top">Back to top</a></div>
</div></footer>`;
// Kits' .prose rules (they live in the Kits bundle, not in the studio CSS) plus the licence-key bits.
const PAGE_CSS = `.prose{max-width:46rem}.prose li,.prose p{margin-bottom:.8em;font-size:1.0625rem}.prose ol,.prose ul{padding-left:1.3em;margin-bottom:1em}.prose ul{list-style:disc}.prose h1{font-size:clamp(2.2rem,6vw,3.6rem);letter-spacing:-.04em;margin-bottom:.4em}.prose h2{font-size:clamp(1.6rem,3.4vw,2.3rem);margin:1.4em 0 .5em}.prose a{color:var(--crust);font-weight:650;text-underline-offset:3px}.prose .small,.prose .muted{font-size:.9rem;color:var(--muted)}
.prose code,.prose pre,.key{font-family:ui-monospace,Menlo,Consolas,monospace}.key{font-size:1.4rem;font-weight:700;background:var(--card);border:2.5px solid var(--ink);border-radius:var(--radius);box-shadow:4px 5px 0 var(--ink);padding:12px 18px;display:inline-block;user-select:all}
.prose pre{background:var(--card);border:2px solid var(--ink);border-radius:10px;padding:12px 16px;overflow:auto;margin-bottom:1em}`;

function page(title, body, status = 200, { index = false } = {}) {
  return new Response(`<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
${index ? "" : '<meta name="robots" content="noindex">'}<title>${escapeHtml(title)} | Burnt &amp; Toast</title>
<link rel="icon" href="${STUDIO}/favicon.svg" type="image/svg+xml">
<link rel="preload" href="${STUDIO}/assets/fonts/bricolage-grotesque-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="${STUDIO}/assets/chrome.css">
<link rel="stylesheet" href="${STUDIO}/assets/site.css">
<style>${PAGE_CSS}</style></head>
<body id="top">${HEADER}
<main id="main"><section class="section"><div class="wrap prose">${body}</div></section></main>
${FOOTER}</body></html>`, { status, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store", "referrer-policy": "no-referrer" } });
}

export function successPage({ key, email, productName, cliName, baseUrl }) {
  return page(`Your ${productName} licence`, `<h1>Thanks — you're licensed</h1>
<p>Your licence key:</p><p class="key">${escapeHtml(key)}</p>
<p>We're also emailing it to <strong>${escapeHtml(email)}</strong>. It covers one repository (a monorepo counts as one), bound the first time you use it.</p>
<pre>export LASTORDERS_LICENCE=${escapeHtml(key)}
${escapeHtml(cliName)} fix . --verify --apply</pre>
<p>In GitHub Actions, add it as a repository secret named <code>LASTORDERS_LICENCE</code>.</p>
<p class="muted">Keep this key private. <a href="${LANDING_URL}/">Back to ${escapeHtml(productName)}</a></p>`);
}

export function pendingPage({ productName }) {
  return page(`${productName}: payment processing`, `<h1>Payment processing</h1>
<p>Your payment hasn't cleared yet (some payment methods take a little while). We'll email your licence key as soon as it does.</p>`, 202);
}

export function cancelPage({ productName, baseUrl }) {
  return page(`${productName}: checkout cancelled`, `<h1>Checkout cancelled</h1><p>No payment was taken. The free scan keeps working without a licence.</p>
<p><a href="${LANDING_URL}/">Back to ${escapeHtml(productName)}</a></p>`);
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
