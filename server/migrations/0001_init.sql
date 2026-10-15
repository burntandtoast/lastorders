-- Licences: one row per purchased licence. One licence covers one repo (monorepos included),
-- bound on first activation.
CREATE TABLE IF NOT EXISTS licences (
  key                 TEXT PRIMARY KEY,           -- BTM-XXXX-XXXX-XXXX
  email               TEXT NOT NULL,
  status              TEXT NOT NULL DEFAULT 'active',   -- active | revoked
  repo                TEXT,                       -- host/owner/repo, lower-case; NULL until first activation
  plan                TEXT NOT NULL DEFAULT 'repo',
  amount              INTEGER,                    -- minor units (pence)
  currency            TEXT,
  stripe_session_id   TEXT UNIQUE,
  stripe_payment_intent TEXT,
  stripe_customer     TEXT,
  livemode            INTEGER NOT NULL DEFAULT 0,
  email_status        TEXT NOT NULL DEFAULT 'pending',  -- pending | sent | failed | skipped
  created_at          TEXT NOT NULL,
  activated_at        TEXT,
  revoked_at          TEXT,
  revoke_reason       TEXT
);
CREATE INDEX IF NOT EXISTS licences_email ON licences(email);
CREATE INDEX IF NOT EXISTS licences_pi ON licences(stripe_payment_intent);

-- Stripe events already handled (webhook idempotency).
CREATE TABLE IF NOT EXISTS stripe_events (
  id          TEXT PRIMARY KEY,
  type        TEXT NOT NULL,
  received_at TEXT NOT NULL
);

-- Audit trail of activations / verifications that changed state, and admin actions.
CREATE TABLE IF NOT EXISTS licence_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  key         TEXT NOT NULL,
  kind        TEXT NOT NULL,     -- issued | activated | rejected_repo | revoked | rebound | email_sent | email_failed
  detail      TEXT,
  at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS licence_events_key ON licence_events(key);
