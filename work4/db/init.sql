-- Payments schema shared by all three services.
CREATE TABLE IF NOT EXISTS payments (
  id           text PRIMARY KEY,                -- client-supplied idempotency key
  merchant     text NOT NULL,
  amount       bigint NOT NULL,
  currency     text NOT NULL,
  status       text NOT NULL,                   -- pending | captured | failed
  provider_ref text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz
);
CREATE TABLE IF NOT EXISTS balances (
  merchant text PRIMARY KEY,
  total    bigint NOT NULL DEFAULT 0,
  count    bigint NOT NULL DEFAULT 0
);
