-- Dopenexa Sprint 6: customer personalization, saved professionals, richer discovery.
CREATE TABLE IF NOT EXISTS saved_professionals (
  customer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  professional_id UUID NOT NULL REFERENCES professional_profiles(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (customer_id, professional_id)
);
CREATE INDEX IF NOT EXISTS saved_professionals_customer_idx ON saved_professionals(customer_id, created_at DESC);

CREATE TABLE IF NOT EXISTS search_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  query TEXT NOT NULL,
  category VARCHAR(100),
  result_count INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS search_events_user_idx ON search_events(user_id, created_at DESC);
