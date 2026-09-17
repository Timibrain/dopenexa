-- Dopenexa Payment Hardening Phase 2: race-safe webhook event processing.

ALTER TABLE payment_events
  ADD COLUMN IF NOT EXISTS processing_status VARCHAR(20) NOT NULL DEFAULT 'received',
  ADD COLUMN IF NOT EXISTS failure_reason TEXT;

ALTER TABLE payment_events
  ALTER COLUMN processed_at DROP NOT NULL;

UPDATE payment_events
SET processing_status = 'processed'
WHERE processing_status IS NULL;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'payment_events_processing_status_check') THEN
    ALTER TABLE payment_events DROP CONSTRAINT payment_events_processing_status_check;
  END IF;
  ALTER TABLE payment_events
    ADD CONSTRAINT payment_events_processing_status_check
    CHECK (processing_status IN ('received', 'processed', 'failed'));
END;
$$;

CREATE INDEX IF NOT EXISTS payment_events_status_idx
  ON payment_events(processing_status, processed_at);
