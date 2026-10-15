// Licence storage on Cloudflare D1 (SQLite). All writes are idempotent / conditional.
import { nowIso } from "./util.js";

export class Store {
  constructor(db, clock = () => Date.now()) {
    this.db = db;
    this.clock = clock;
  }

  now() { return nowIso(this.clock()); }

  async get(key) {
    return (await this.db.prepare("SELECT * FROM licences WHERE key = ?").bind(key).first()) || null;
  }

  async bySession(sessionId) {
    return (await this.db.prepare("SELECT * FROM licences WHERE stripe_session_id = ?").bind(sessionId).first()) || null;
  }

  async byPaymentIntent(pi) {
    const r = await this.db.prepare("SELECT * FROM licences WHERE stripe_payment_intent = ?").bind(pi).all();
    return r.results || [];
  }

  /** Insert a licence for a paid Checkout Session. Returns the existing row if the session was already fulfilled. */
  async createForSession({ key, email, sessionId, paymentIntent, customer, amount, currency, livemode }) {
    const res = await this.db.prepare(
      `INSERT INTO licences (key, email, stripe_session_id, stripe_payment_intent, stripe_customer, amount, currency, livemode, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(stripe_session_id) DO NOTHING`
    ).bind(key, email, sessionId, paymentIntent, customer, amount, currency, livemode ? 1 : 0, this.now()).run();
    const row = await this.bySession(sessionId);
    const created = (res.meta?.changes ?? 0) > 0 && row?.key === key;
    if (created) await this.event(key, "issued", sessionId);
    return { row, created };
  }

  /** Bind on first activation. Returns the row after the attempt. */
  async activate(key, repo) {
    await this.db.prepare("UPDATE licences SET repo = ?, activated_at = ? WHERE key = ? AND repo IS NULL AND status = 'active'")
      .bind(repo, this.now(), key).run();
    return this.get(key);
  }

  async setEmailStatus(key, status) {
    await this.db.prepare("UPDATE licences SET email_status = ? WHERE key = ?").bind(status, key).run();
  }

  async revoke(key, reason) {
    await this.db.prepare("UPDATE licences SET status = 'revoked', revoked_at = ?, revoke_reason = ? WHERE key = ? AND status = 'active'")
      .bind(this.now(), reason, key).run();
    await this.event(key, "revoked", reason);
  }

  async rebind(key, repo) {
    await this.db.prepare("UPDATE licences SET repo = ?, activated_at = CASE WHEN ? IS NULL THEN NULL ELSE ? END WHERE key = ?")
      .bind(repo, repo, this.now(), key).run();
    await this.event(key, "rebound", repo ?? "(unbound)");
  }

  /** true if this Stripe event id is new (and records it). */
  async claimEvent(id, type) {
    const r = await this.db.prepare("INSERT INTO stripe_events (id, type, received_at) VALUES (?, ?, ?) ON CONFLICT(id) DO NOTHING")
      .bind(id, type, this.now()).run();
    return (r.meta?.changes ?? 0) > 0;
  }

  async releaseEvent(id) {
    await this.db.prepare("DELETE FROM stripe_events WHERE id = ?").bind(id).run();
  }

  async event(key, kind, detail) {
    await this.db.prepare("INSERT INTO licence_events (key, kind, detail, at) VALUES (?, ?, ?, ?)").bind(key, kind, detail ?? null, this.now()).run();
  }
}
