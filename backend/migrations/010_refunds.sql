-- Dopenexa Payment Hardening Phase 4: refund records and compensating postings.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'payments_id_booking_key' AND conrelid = 'payments'::regclass
  ) THEN
    ALTER TABLE payments ADD CONSTRAINT payments_id_booking_key UNIQUE (id, booking_id);
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS refunds (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  payment_id UUID NOT NULL,
  booking_id UUID NOT NULL,
  amount_ngn BIGINT NOT NULL CHECK (amount_ngn > 0),
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  idempotency_key VARCHAR(160) NOT NULL,
  provider VARCHAR(50) NOT NULL DEFAULT 'pending',
  provider_reference VARCHAR(160),
  failure_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at TIMESTAMPTZ,
  CONSTRAINT refund_status_check CHECK (status IN ('pending','processing','succeeded','failed','cancelled')),
  CONSTRAINT refunds_payment_idempotency_key UNIQUE (payment_id, idempotency_key),
  CONSTRAINT refunds_provider_reference_unique UNIQUE (provider_reference),
  CONSTRAINT refunds_payment_booking_fk FOREIGN KEY (payment_id, booking_id)
    REFERENCES payments(id, booking_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS refunds_payment_date_idx ON refunds(payment_id, created_at DESC);
CREATE INDEX IF NOT EXISTS refunds_booking_date_idx ON refunds(booking_id, created_at DESC);
CREATE INDEX IF NOT EXISTS refunds_status_idx ON refunds(status, created_at DESC);
CREATE INDEX IF NOT EXISTS refunds_provider_reference_idx ON refunds(provider_reference) WHERE provider_reference IS NOT NULL;

INSERT INTO ledger_accounts (code, name)
VALUES ('professional_receivable', 'Professional receivable')
ON CONFLICT (code) DO NOTHING;
