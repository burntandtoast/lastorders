// Tiny server-rendered pages for the Checkout return URLs.
import { escapeHtml } from "./util.js";

function page(title, body, status = 200) {
  return new Response(`<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>${escapeHtml(title)}</title>
<style>body{font:16px/1.55 system-ui,sans-serif;max-width:640px;margin:48px auto;padding:0 20px;color:#1b1b1b}
code,pre,.key{font-family:ui-monospace,Menlo,monospace}.key{font-size:22px;font-weight:600;background:#f4f1ea;padding:12px 16px;border-radius:6px;display:inline-block;user-select:all}
pre{background:#f4f1ea;padding:12px 16px;border-radius:6px;overflow:auto}.muted{color:#666;font-size:14px}</style></head>
<body>${body}</body></html>`, { status, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store", "referrer-policy": "no-referrer" } });
}

export function successPage({ key, email, productName, cliName, baseUrl }) {
  return page(`Your ${productName} licence`, `<h1>Thanks — you're licensed</h1>
<p>Your licence key:</p><p class="key">${escapeHtml(key)}</p>
<p>We're also emailing it to <strong>${escapeHtml(email)}</strong>. It covers one repository (a monorepo counts as one), bound the first time you use it.</p>
<pre>export MODELMIGRATE_LICENCE=${escapeHtml(key)}
${escapeHtml(cliName)} fix . --verify --apply</pre>
<p>In GitHub Actions, add it as a repository secret named <code>MODELMIGRATE_LICENCE</code>.</p>
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
