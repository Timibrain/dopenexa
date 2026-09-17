-- Dopenexa Payment Phase 5B: Paystack sandbox transfer identifiers.
ALTER TABLE payout_accounts ADD COLUMN IF NOT EXISTS bank_code VARCHAR(20);
ALTER TABLE payout_accounts ADD COLUMN IF NOT EXISTS provider_recipient_code VARCHAR(160);
ALTER TABLE payouts ADD COLUMN IF NOT EXISTS dopenexa_reference VARCHAR(160);

CREATE UNIQUE INDEX IF NOT EXISTS payouts_dopenexa_reference_idx
  ON payouts(dopenexa_reference) WHERE dopenexa_reference IS NOT NULL;
CREATE INDEX IF NOT EXISTS payout_accounts_recipient_idx
  ON payout_accounts(provider, provider_recipient_code) WHERE provider_recipient_code IS NOT NULL;
