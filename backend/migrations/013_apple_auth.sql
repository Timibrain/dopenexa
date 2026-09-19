-- Sign in with Apple identities. Existing email accounts remain unchanged.
ALTER TABLE users ALTER COLUMN email DROP NOT NULL;
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;

CREATE TABLE IF NOT EXISTS auth_identities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider VARCHAR(40) NOT NULL,
  provider_subject VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT auth_identities_provider_subject_key UNIQUE (provider, provider_subject)
);
CREATE INDEX IF NOT EXISTS auth_identities_user_id_idx ON auth_identities(user_id);
