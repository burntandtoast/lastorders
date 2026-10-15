// Pluggable licence-email delivery. Provider chosen by EMAIL_PROVIDER: resend | log | none.
import { escapeHtml } from "./util.js";

export function licenceEmail({ key, productName, cliName, buyerEmail, baseUrl, supportEmail }) {
  const subject = `Your ${productName} licence key`;
  const text = [
    `Thanks for buying ${productName}.`,
    "",
    `Your licence key: ${key}`,
    "",
    "It covers one repository (a monorepo counts as one). The repo is bound the first time you use the key:",
    "",
    `  export LASTORDERS_LICENCE=${key}`,
    `  ${cliName} fix . --verify --apply`,
    "",
    "In GitHub Actions, store it as a repository secret named LASTORDERS_LICENCE.",
    "",
    `Receipt and docs: ${baseUrl}`,
    supportEmail ? `Questions or a repo move: reply to this email or write to ${supportEmail}.` : "Questions or a repo move: reply to this email.",
    "",
    "Burnt & Toast Studios",
  ].join("\n");
  const html = `<!doctype html><html><body style="font-family:system-ui,sans-serif;line-height:1.5;color:#1b1b1b">
<p>Thanks for buying ${escapeHtml(productName)}.</p>
<p>Your licence key:</p>
<p style="font:600 20px/1.4 ui-monospace,Menlo,monospace;background:#f4f1ea;padding:12px 16px;border-radius:6px;display:inline-block">${escapeHtml(key)}</p>
<p>It covers one repository (a monorepo counts as one). The repo is bound the first time you use the key:</p>
<pre style="background:#f4f1ea;padding:12px 16px;border-radius:6px">export LASTORDERS_LICENCE=${escapeHtml(key)}
${escapeHtml(cliName)} fix . --verify --apply</pre>
<p>In GitHub Actions, store it as a repository secret named <code>LASTORDERS_LICENCE</code>.</p>
<p>Docs: <a href="${escapeHtml(baseUrl)}">${escapeHtml(baseUrl)}</a><br>
${supportEmail ? `Questions or a repo move: reply, or write to ${escapeHtml(supportEmail)}.` : "Questions or a repo move: reply to this email."}</p>
<p>Burnt &amp; Toast Studios</p></body></html>`;
  return { to: buyerEmail, subject, text, html };
}

export function makeMailer(env, fetchImpl = fetch) {
  const provider = (env.EMAIL_PROVIDER || "log").toLowerCase();
  if (provider === "resend") return new ResendMailer(env, fetchImpl);
  if (provider === "none") return { name: "none", async send() { return { ok: true, skipped: true }; } };
  return new LogMailer();
}

export class ResendMailer {
  constructor(env, fetchImpl) {
    this.name = "resend";
    this.apiKey = env.RESEND_API_KEY;
    this.from = env.EMAIL_FROM;
    this.replyTo = env.EMAIL_REPLY_TO || undefined;
    this.apiBase = (env.RESEND_API_BASE || "https://api.resend.com").replace(/\/$/, "");
    this.fetch = fetchImpl;
  }
  async send(msg, idempotencyKey) {
    if (!this.apiKey || !this.from) return { ok: false, error: "RESEND_API_KEY / EMAIL_FROM not configured" };
    const headers = { authorization: `Bearer ${this.apiKey}`, "content-type": "application/json" };
    if (idempotencyKey) headers["idempotency-key"] = idempotencyKey;
    const res = await this.fetch(`${this.apiBase}/emails`, {
      method: "POST",
      headers,
      body: JSON.stringify({ from: this.from, to: [msg.to], subject: msg.subject, text: msg.text, html: msg.html, reply_to: this.replyTo }),
    });
    if (!res.ok) return { ok: false, error: `resend ${res.status}: ${(await res.text()).slice(0, 200)}` };
    return { ok: true, id: (await res.json().catch(() => ({}))).id };
  }
}

export class LogMailer {
  constructor() { this.name = "log"; this.sent = []; }
  async send(msg) {
    this.sent.push(msg);
    console.log(`[email:log] to=${msg.to} subject=${JSON.stringify(msg.subject)}`);
    return { ok: true, logged: true };
  }
}
