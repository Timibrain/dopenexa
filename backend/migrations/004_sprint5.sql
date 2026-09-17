-- Dopenexa Sprint 5: production boundaries, sessions, trust, payouts, device registration and AI provider support.
CREATE TABLE IF NOT EXISTS refresh_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash VARCHAR(128) UNIQUE NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS refresh_sessions_user_idx ON refresh_sessions(user_id, expires_at DESC);

CREATE TABLE IF NOT EXISTS device_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token VARCHAR(512) UNIQUE NOT NULL,
  platform VARCHAR(20) NOT NULL DEFAULT 'ios',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS device_tokens_user_idx ON device_tokens(user_id, is_active);

CREATE TABLE IF NOT EXISTS verification_submissions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  professional_id UUID NOT NULL REFERENCES professional_profiles(id) ON DELETE CASCADE,
  document_type VARCHAR(60) NOT NULL,
  document_reference VARCHAR(255) NOT NULL,
  status VARCHAR(40) NOT NULL DEFAULT 'pending',
  reviewer_id UUID REFERENCES users(id),
  reviewer_note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  reviewed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS verification_status_idx ON verification_submissions(status, created_at DESC);

CREATE TABLE IF NOT EXISTS payout_accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  professional_id UUID NOT NULL REFERENCES professional_profiles(id) ON DELETE CASCADE,
  provider VARCHAR(50) NOT NULL,
  account_name VARCHAR(160) NOT NULL,
  account_reference VARCHAR(255) NOT NULL,
  is_default BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS payout_accounts_prof_default_idx ON payout_accounts(professional_id) WHERE is_default = TRUE;

CREATE TABLE IF NOT EXISTS payouts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  professional_id UUID NOT NULL REFERENCES professional_profiles(id),
  amount_ngn BIGINT NOT NULL,
  status VARCHAR(40) NOT NULL DEFAULT 'pending',
  provider VARCHAR(50) NOT NULL DEFAULT 'pending',
  provider_reference VARCHAR(160) UNIQUE,
  failure_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  paid_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS payouts_professional_idx ON payouts(professional_id, created_at DESC);

CREATE TABLE IF NOT EXISTS payment_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider VARCHAR(50) NOT NULL,
  event_id VARCHAR(255) NOT NULL,
  event_type VARCHAR(80) NOT NULL,
  payload JSONB NOT NULL,
  processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(provider, event_id)
);

CREATE TABLE IF NOT EXISTS professional_ai_embeddings (
  professional_id UUID PRIMARY KEY REFERENCES professional_profiles(id) ON DELETE CASCADE,
  model VARCHAR(120) NOT NULL,
  dimensions INTEGER NOT NULL,
  embedding vector(1536) NOT NULL,
  source_hash VARCHAR(64) NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS professional_ai_embeddings_hnsw_idx ON professional_ai_embeddings USING hnsw (embedding vector_cosine_ops);
