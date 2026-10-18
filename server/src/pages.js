// Tiny server-rendered pages for the Checkout return URLs.
import { escapeHtml } from "./util.js";
import { COMPANY, TERMS_VERSION } from "./terms.js";

// Studio chrome: the same header, footer, stylesheets, logo and favicon as burntandtoast.com (loaded from the
// studio site, which serves them with CORS). Page bodies use the Kits ".prose" pattern.
const STUDIO = "https://burntandtoast.com";
// Studio CSS/fonts/logo are proxied same-origin by the landing Worker (lastorders host) for a faster first paint.
const STUDIO_ASSETS = "https://lastorders.burntandtoast.com/studio-assets";
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
// Studio footer, copied from burntandtoast.com (15 Oct 2026); Last Orders added under "More from us" and "Help".
const FOOTER = `<footer class="site-foot">
  <div class="foot-wrap">
    <div class="foot-top">
      <div class="foot-brand">
        <img src="${STUDIO_ASSETS}/logo.svg" alt="" width="84" height="84" decoding="async">
        <p>Burnt &amp; Toast<span class="signoff">Burnt at the edges. Still good.</span></p>
        <nav class="foot-social" aria-label="Social">
        <ul><li><a href="https://www.youtube.com/@burntandtoaststudios" rel="noopener"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M23.5 6.2a3 3 0 0 0-2.1-2.1C19.5 3.5 12 3.5 12 3.5s-7.5 0-9.4.5a3 3 0 0 0-2.1 2.1C0 8.1 0 12 0 12s0 3.9.5 5.8a3 3 0 0 0 2.1 2.1c1.9.5 9.4.5 9.4.5s7.5 0 9.4-.5a3 3 0 0 0 2.1-2.1c.5-1.9.5-5.8.5-5.8s0-3.9-.5-5.8zM9.5 15.6V8.4L15.8 12l-6.3 3.6z"/></svg><span class="sr-only">YouTube</span></a></li><li><a href="https://x.com/burntandtoastuk" rel="noopener"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M18.2 2h3.3l-7.3 8.3L23 22h-6.8l-5.3-7L5.4 22H2.1l7.8-8.9L1 2h7l4.8 6.4L18.2 2zm-1.2 18h1.8L7.1 3.9H5.1L17 20z"/></svg><span class="sr-only">Burnt and Toast on X</span></a></li><li><a href="https://www.linkedin.com/company/137304224/" rel="noopener"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M20.4 20.5h-3.6v-5.6c0-1.3 0-3-1.8-3s-2.1 1.4-2.1 2.9v5.7H9.4V9h3.4v1.6h.1c.5-.9 1.6-1.9 3.4-1.9 3.6 0 4.3 2.4 4.3 5.5v6.3zM5.3 7.4a2.1 2.1 0 1 1 0-4.2 2.1 2.1 0 0 1 0 4.2zM7.1 20.5H3.6V9h3.5v11.5zM22.2 0H1.8C.8 0 0 .8 0 1.7v20.5C0 23.2.8 24 1.8 24h20.4c1 0 1.8-.8 1.8-1.7V1.7C24 .8 23.2 0 22.2 0z"/></svg><span class="sr-only">LinkedIn</span></a></li></ul>
      </nav>
      </div>
      <div class="foot-cols">
        <nav aria-labelledby="f-games"><h2 id="f-games">Games</h2><ul><li><a href="https://burntandtoast.com/inland-light/">Inland Light <span class="foot-badge">Out 31 Oct</span></a></li><li><a href="https://burntandtoast.com/halt-branch-line/">Halt! Branch Line</a></li><li><a href="https://dartistry.app/" rel="noopener">Dartistry</a></li><li><a href="https://hawfold.com/" rel="noopener">Hawfold</a></li><li><a href="https://burntandtoast.com/#games">All games</a></li></ul></nav>
        <nav aria-labelledby="f-studio"><h2 id="f-studio">Studio</h2><ul><li><a href="https://burntandtoast.com/blog">Journal</a></li><li><a href="https://burntandtoast.com/press/">Press kits</a></li><li><a href="mailto:hello@burntandtoast.com">Contact</a></li></ul></nav>
        <nav aria-labelledby="f-more-from-us"><h2 id="f-more-from-us">More from us</h2><ul><li><a class="foot-with-note" href="https://lastorders.burntandtoast.com/"><span class="foot-label">Last Orders</span><span class="foot-desc">Retiring AI model scan</span></a></li><li><a class="foot-with-note" href="https://deals.burntandtoast.com/" rel="noopener"><span class="foot-label">Burnt Deals</span><span class="foot-desc">PC game deals</span></a></li><li><a class="foot-with-note" href="https://kits.burntandtoast.com/" rel="noopener"><span class="foot-label">Kits</span><span class="foot-desc">AI kits for estate agents</span></a></li></ul></nav>
        <nav aria-labelledby="f-help"><h2 id="f-help">Help</h2><ul><li><a href="https://burntandtoast.com/support/">Support</a></li><li><a href="https://burntandtoast.com/legal/">Privacy</a></li><li><a href="https://lastorders.burntandtoast.com/terms">Last Orders terms and refunds</a></li></ul></nav>
      </div>
    </div>
    <div class="foot-bottom">
      <div><p>© 2026 Burnt and Toast Studios Ltd · Company no. 17334149 · 71-75 Shelton Street, London WC2H 9JQ</p><p class="foot-note">We count visits anonymously. No cookies, no ads, no tracking across sites. <a href="https://burntandtoast.com/privacy/#analytics">Privacy</a></p></div>
      <a href="#top">Back to top</a>
    </div>
  </div>
</footer>`;
// Kits' .prose rules (they live in the Kits bundle, not in the studio CSS) plus the licence-key bits.
const PAGE_CSS = `/* Metric-matched fallback for Bricolage Grotesque (Arial/Helvetica sized to match), so the font swap doesn't shift text. */@font-face{font-family:"Bricolage fallback";src:local("Arial"),local("Helvetica"),local("Liberation Sans");size-adjust:103.3%;ascent-override:90.1%;descent-override:26.1%;line-gap-override:0%}:root{--display:"Bricolage Grotesque","Bricolage fallback",ui-rounded,"Arial Rounded MT Bold",system-ui,sans-serif;--body:"Bricolage Grotesque","Bricolage fallback",ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}.prose{max-width:46rem}.prose li,.prose p{margin-bottom:.8em;font-size:1.0625rem}.prose ol,.prose ul{padding-left:1.3em;margin-bottom:1em}.prose ul{list-style:disc}.prose h1{font-size:clamp(2.2rem,6vw,3.6rem);letter-spacing:-.04em;margin-bottom:.4em}.prose h2{font-size:clamp(1.6rem,3.4vw,2.3rem);margin:1.4em 0 .5em}.prose a{color:var(--crust);font-weight:650;text-underline-offset:3px}.prose .small,.prose .muted{font-size:.9rem;color:var(--muted)}
.prose code,.prose pre,.key{font-family:ui-monospace,Menlo,Consolas,monospace}.key{font-size:1.4rem;font-weight:700;background:var(--card);border:2.5px solid var(--ink);border-radius:var(--radius);box-shadow:4px 5px 0 var(--ink);padding:12px 18px;display:inline-block;user-select:all}
.prose pre{background:var(--card);border:2px solid var(--ink);border-radius:10px;padding:12px 16px;overflow:auto;margin-bottom:1em}`;

function page(title, body, status = 200, { index = false } = {}) {
  return new Response(`<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
${index ? "" : '<meta name="robots" content="noindex">'}<title>${escapeHtml(title)} | Burnt &amp; Toast</title>
<link rel="icon" href="${STUDIO}/favicon.svg" type="image/svg+xml">
<link rel="preload" href="${STUDIO_ASSETS}/fonts/bricolage-grotesque-latin.woff2" as="font" type="font/woff2" crossorigin fetchpriority="high">
<link rel="stylesheet" href="${STUDIO_ASSETS}/chrome.css">
<link rel="stylesheet" href="${STUDIO_ASSETS}/site.css">
<style>${PAGE_CSS}</style></head>
<body id="top">${HEADER}
<main id="main"><section class="section"><div class="wrap prose">${body}</div></section></main>
${FOOTER}</body></html>`, { status, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store", "referrer-policy": "no-referrer" } });
}

export function successPage({ key, email, productName, cliName, baseUrl, managedPayments = false }) {
  const termsUrl = `${baseUrl || LANDING_URL}/terms`;
  const link = managedPayments
    ? `<p>This purchase is <strong>Sold through Link</strong>. Your card or bank statement shows <code>LINK.COM*</code>. Link emails the receipt and handles payment support. For the licence itself, see the <a href="${escapeHtml(termsUrl)}">terms</a>.</p>`
    : "";
  return page(`Your ${productName} licence`, `<h1>Thanks — you're licensed</h1>
<p>Your licence key:</p><p class="key">${escapeHtml(key)}</p>
<p>We're also emailing it to <strong>${escapeHtml(email)}</strong>. It covers one repository (a monorepo counts as one), bound the first time you use it.</p>
<pre>export LASTORDERS_LICENCE=${escapeHtml(key)}
${escapeHtml(cliName)} fix . --verify --apply</pre>
<p>In GitHub Actions, add it as a repository secret named <code>LASTORDERS_LICENCE</code>.</p>
${link}
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

export function termsPage({ productName, cliName, amount, currency, baseUrl, managedPayments = false }) {
  const price = currency === "gbp" ? `£${(amount / 100).toFixed(2).replace(/\.00$/, "")}` : `${(amount / 100).toFixed(2)} ${currency.toUpperCase()}`;
  const e = escapeHtml, mail = `<a href="mailto:${e(COMPANY.email)}">${e(COMPANY.email)}</a>`;
  const linkSection = managedPayments ? `<h2>Who takes the payment</h2>
<p>You pay through Link. The checkout is <strong>Sold through Link</strong>, and Link (Stripe) is the merchant of record. Your card or bank statement shows <code>LINK.COM*</code> followed by our statement descriptor. Link sends the receipt and handles payment support, including questions about the charge itself. Product support (the licence, the scan, and moving a repository) stays with us at ${mail}.</p>` : "";
  const linkRefund = managedPayments ? `<p>Stripe, through Link, may also refund the payment in some cases without a separate request to us. Link support can refund within 60 days of the payment, and if we don't answer a Link support question within 48 hours Stripe may refund. That doesn't replace the refund policy above.</p>` : "";
  return page(`${productName}: licence terms and refund policy`, `<h1>${e(productName)}: licence terms and refund policy</h1>
<p class="muted">Version ${e(TERMS_VERSION)}. These terms apply to ${e(productName)} licences bought at ${e(baseUrl || "")}/buy.</p>
<h2>Who we are</h2>
<p>${e(COMPANY.name)}, a company registered in England and Wales, company no. ${e(COMPANY.number)}. Registered office: ${e(COMPANY.address)}. ${e(COMPANY.vat)}. Contact: ${mail}.</p>
${linkSection}
<h2>What you get</h2>
<ul><li>A licence key for one GitHub repository (a monorepo counts as one), for ${e(price)} including any VAT, paid once.</li>
<li>The repository is bound to the key the first time the key is used (activated) with the <code>${e(cliName)}</code> tool. We can move a licence to another repository on request, for example after a rename or transfer.</li>
<li>The licence unlocks the paid features (reviewable patches, a must-review list and reports) for that repository, including updates for future model retirements. The free scan never needs a licence.</li>
<li>The key is for your organisation's use on that repository. Please don't share it for use on other repositories.</li></ul>
<h2>Refund policy</h2>
<ul><li><b>Never activated:</b> a full refund if the licence key has never been activated (we record when it is first used) and you ask within 14 days of purchase. After 14 days, an unactivated key isn't refundable under this policy.</li>
<li><b>Activated:</b> a refund only if the fix fails on your repository and we can't resolve it within 5 working days of you telling us.</li></ul>
<p>To ask for a refund, email ${mail} with your licence key or the email address you paid with. Refunds go back to the original payment method. A refunded licence stops working.</p>
${linkRefund}
<h2>Your right to cancel (consumers)</h2>
<p>If you buy as a consumer, you would normally have 14 days to cancel. Because the licence key is digital content supplied straight away, at checkout you expressly ask for immediate supply and acknowledge that you lose the 14-day right to cancel once the key is used (Consumer Contracts Regulations 2013, regulation 37). If you haven't used the key, you can cancel within 14 days of purchase and get a full refund, the same as the never-activated refund above. Once the key is used, the 14-day right to cancel ends and the activated-key refund above applies. Businesses have no statutory cooling-off right; the refund policy above applies to them too.</p>
<p>Nothing in these terms affects your statutory rights, for example if the licence or the software isn't as described.</p>
<h2>Liability</h2>
<p>${e(productName)} proposes code changes for you to review. You're responsible for reviewing, testing and deploying them. Our total liability for a licence is limited to the price you paid for it, except where the law doesn't allow liability to be limited.</p>
<h2>Governing law</h2>
<p>These terms are governed by the law of England and Wales, and the courts of England and Wales have jurisdiction. If you're a consumer living in Scotland or Northern Ireland, you can also bring proceedings in your local courts.</p>
<p class="muted">Questions: ${mail}. ${e(COMPANY.name)}, ${e(COMPANY.address)}.</p>`, 200, { index: true });
}
