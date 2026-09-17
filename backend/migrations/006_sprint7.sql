-- Sprint 7: marketplace personalization + realtime messaging support
CREATE TABLE IF NOT EXISTS recommendation_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    professional_id uuid REFERENCES professional_profiles(id) ON DELETE CASCADE,
    reason varchar(255) NOT NULL,
    score integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_recommendation_events_user ON recommendation_events(user_id, created_at DESC);
