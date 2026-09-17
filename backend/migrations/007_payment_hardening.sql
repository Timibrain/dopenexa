-- Dopenexa Payment Hardening Phase 1: payment state history and immutable ledger.

ALTER TABLE payments
  ADD COLUMN IF NOT EXISTS currency CHAR(3) NOT NULL DEFAULT 'NGN',
  ADD COLUMN IF NOT EXISTS captured_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS refunded_amount_ngn BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS client_idempotency_key VARCHAR(160);

UPDATE payments SET currency = 'NGN' WHERE currency IS NULL;
UPDATE payments SET refunded_amount_ngn = 0 WHERE refunded_amount_ngn IS NULL;

ALTER TABLE payments
  DROP CONSTRAINT IF EXISTS payments_status_check;
ALTER TABLE payments
  ADD CONSTRAINT payments_status_check CHECK (status IN (
    'pending', 'authorized', 'paid', 'failed', 'cancelled',
    'partially_refunded', 'refunded', 'settled'
  ));
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'payments_currency_check') THEN
    ALTER TABLE payments ADD CONSTRAINT payments_currency_check CHECK (currency = 'NGN');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'payments_refunded_amount_check') THEN
    ALTER TABLE payments ADD CONSTRAINT payments_refunded_amount_check CHECK (refunded_amount_ngn >= 0 AND refunded_amount_ngn <= amount_ngn);
  END IF;
END;
$$;

CREATE UNIQUE INDEX IF NOT EXISTS payments_client_idempotency_key_idx
  ON payments(client_idempotency_key)
  WHERE client_idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS payment_status_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  payment_id UUID NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
  from_status VARCHAR(40),
  to_status VARCHAR(40) NOT NULL,
  source VARCHAR(80) NOT NULL,
  transition_key VARCHAR(160) UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS payment_status_history_payment_idx
  ON payment_status_history(payment_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ledger_accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code VARCHAR(80) UNIQUE NOT NULL,
  name VARCHAR(160) NOT NULL,
  currency CHAR(3) NOT NULL DEFAULT 'NGN',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ledger_accounts_currency_check CHECK (currency = 'NGN')
);

CREATE TABLE IF NOT EXISTS ledger_transactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  idempotency_key VARCHAR(255) UNIQUE NOT NULL,
  transaction_type VARCHAR(80) NOT NULL,
  currency CHAR(3) NOT NULL DEFAULT 'NGN',
  source_type VARCHAR(80),
  source_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ledger_transactions_currency_check CHECK (currency = 'NGN')
);
CREATE INDEX IF NOT EXISTS ledger_transactions_source_idx
  ON ledger_transactions(source_type, source_id);

CREATE TABLE IF NOT EXISTS ledger_entries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  transaction_id UUID NOT NULL REFERENCES ledger_transactions(id) ON DELETE RESTRICT,
  account_id UUID NOT NULL REFERENCES ledger_accounts(id) ON DELETE RESTRICT,
  direction VARCHAR(6) NOT NULL,
  amount_ngn BIGINT NOT NULL CHECK (amount_ngn > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ledger_entries_direction_check CHECK (direction IN ('debit', 'credit'))
);
CREATE INDEX IF NOT EXISTS ledger_entries_transaction_idx ON ledger_entries(transaction_id);
CREATE INDEX IF NOT EXISTS ledger_entries_account_idx ON ledger_entries(account_id, created_at DESC);

INSERT INTO ledger_accounts (code, name)
VALUES
  ('processor_cash_clearing', 'Processor / cash clearing'),
  ('professional_payable', 'Professional payable'),
  ('professional_payable_reserved', 'Professional payable reserved'),
  ('platform_commission', 'Platform commission')
ON CONFLICT (code) DO NOTHING;

CREATE OR REPLACE FUNCTION dopenexa_ledger_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Ledger records are immutable';
END;
$$;

DROP TRIGGER IF EXISTS ledger_transactions_immutable ON ledger_transactions;
CREATE TRIGGER ledger_transactions_immutable
  BEFORE UPDATE OR DELETE ON ledger_transactions
  FOR EACH ROW EXECUTE FUNCTION dopenexa_ledger_immutable();

DROP TRIGGER IF EXISTS ledger_entries_immutable ON ledger_entries;
CREATE TRIGGER ledger_entries_immutable
  BEFORE UPDATE OR DELETE ON ledger_entries
  FOR EACH ROW EXECUTE FUNCTION dopenexa_ledger_immutable();

CREATE OR REPLACE FUNCTION dopenexa_check_ledger_balance()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  tx_id UUID;
  debit_total BIGINT;
  credit_total BIGINT;
BEGIN
  tx_id := COALESCE(NEW.transaction_id, OLD.transaction_id);
  SELECT
    COALESCE(SUM(CASE WHEN direction = 'debit' THEN amount_ngn ELSE 0 END), 0),
    COALESCE(SUM(CASE WHEN direction = 'credit' THEN amount_ngn ELSE 0 END), 0)
  INTO debit_total, credit_total
  FROM ledger_entries
  WHERE transaction_id = tx_id;
  IF debit_total <> credit_total THEN
    RAISE EXCEPTION 'Ledger transaction % is unbalanced: debits %, credits %', tx_id, debit_total, credit_total;
  END IF;
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS ledger_entries_balanced ON ledger_entries;
CREATE CONSTRAINT TRIGGER ledger_entries_balanced
  AFTER INSERT OR UPDATE OR DELETE ON ledger_entries
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION dopenexa_check_ledger_balance();
