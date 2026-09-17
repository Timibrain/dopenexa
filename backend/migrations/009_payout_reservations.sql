-- Dopenexa Payment Hardening Phase 3: race-safe payout reservations.
ALTER TABLE payouts ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(160);

CREATE UNIQUE INDEX IF NOT EXISTS payouts_professional_idempotency_idx
  ON payouts(professional_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'payouts_id_professional_key'
      AND conrelid = 'payouts'::regclass
  ) THEN
    ALTER TABLE payouts ADD CONSTRAINT payouts_id_professional_key UNIQUE (id, professional_id);
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS payout_reservations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  payout_id UUID NOT NULL,
  professional_id UUID NOT NULL,
  amount_ngn BIGINT NOT NULL CHECK (amount_ngn > 0),
  status VARCHAR(20) NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  released_at TIMESTAMPTZ,
  CONSTRAINT payout_reservation_status_check CHECK (status IN ('active', 'consumed', 'released')),
  CONSTRAINT payout_reservation_payout_unique UNIQUE (payout_id),
  CONSTRAINT payout_reservation_payout_professional_fk
    FOREIGN KEY (payout_id, professional_id) REFERENCES payouts(id, professional_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS payout_reservations_professional_status_idx
  ON payout_reservations(professional_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS payout_reservations_payout_idx
  ON payout_reservations(payout_id);
