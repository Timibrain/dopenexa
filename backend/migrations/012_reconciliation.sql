-- Dopenexa Payment Phase 6: reconciliation audit records.
CREATE TABLE IF NOT EXISTS reconciliation_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type VARCHAR(40) NOT NULL,
  entity_id UUID NOT NULL,
  provider VARCHAR(50) NOT NULL,
  previous_state VARCHAR(60),
  provider_state VARCHAR(60),
  resulting_state VARCHAR(60),
  action VARCHAR(120) NOT NULL,
  success BOOLEAN NOT NULL DEFAULT false,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS reconciliation_runs_entity_idx ON reconciliation_runs(entity_type, entity_id, created_at DESC);
CREATE INDEX IF NOT EXISTS reconciliation_runs_created_idx ON reconciliation_runs(created_at DESC);
