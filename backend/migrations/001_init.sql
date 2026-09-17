CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TYPE user_role AS ENUM ('customer','professional','agency','admin');
CREATE TYPE service_type AS ENUM ('appointment','hourly','fixed','recurring','project');
CREATE TYPE booking_status AS ENUM ('pending','confirmed','in_progress','completed','cancelled','refunded','disputed');

CREATE TABLE users (
  id UUID PRIMARY KEY,
  email VARCHAR(320) UNIQUE NOT NULL,
  phone VARCHAR(40) UNIQUE,
  password_hash TEXT NOT NULL,
  role user_role NOT NULL,
  display_name VARCHAR(120) NOT NULL,
  avatar_url TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE professional_profiles (
  id UUID PRIMARY KEY,
  user_id UUID UNIQUE NOT NULL REFERENCES users(id),
  headline VARCHAR(160),
  bio TEXT,
  years_experience INT,
  verification_status VARCHAR(40) NOT NULL DEFAULT 'unverified',
  average_rating NUMERIC(3,2) NOT NULL DEFAULT 0,
  review_count INT NOT NULL DEFAULT 0,
  completed_jobs INT NOT NULL DEFAULT 0
);

CREATE TABLE categories (
  id UUID PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  slug VARCHAR(120) UNIQUE NOT NULL
);

CREATE TABLE services (
  id UUID PRIMARY KEY,
  professional_id UUID NOT NULL REFERENCES professional_profiles(id),
  category_id UUID REFERENCES categories(id),
  name VARCHAR(160) NOT NULL,
  description TEXT,
  service_type service_type NOT NULL,
  price_ngn BIGINT NOT NULL CHECK (price_ngn >= 0),
  duration_minutes INT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE availability (
  id UUID PRIMARY KEY,
  professional_id UUID NOT NULL REFERENCES professional_profiles(id),
  weekday INT NOT NULL CHECK (weekday BETWEEN 0 AND 6),
  start_time TIME NOT NULL,
  end_time TIME NOT NULL
);

CREATE TABLE bookings (
  id UUID PRIMARY KEY,
  customer_id UUID NOT NULL REFERENCES users(id),
  professional_id UUID NOT NULL REFERENCES professional_profiles(id),
  service_id UUID NOT NULL REFERENCES services(id),
  status booking_status NOT NULL DEFAULT 'pending',
  starts_at TIMESTAMPTZ NOT NULL,
  ends_at TIMESTAMPTZ,
  total_ngn BIGINT NOT NULL CHECK (total_ngn >= 0),
  customer_note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE conversations (
  id UUID PRIMARY KEY,
  booking_id UUID REFERENCES bookings(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE conversation_members (
  conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (conversation_id,user_id)
);

CREATE TABLE messages (
  id UUID PRIMARY KEY,
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  sender_id UUID NOT NULL REFERENCES users(id),
  body TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE payments (
  id UUID PRIMARY KEY,
  booking_id UUID UNIQUE NOT NULL REFERENCES bookings(id),
  provider VARCHAR(50) NOT NULL DEFAULT 'pending',
  provider_reference VARCHAR(160) UNIQUE,
  status VARCHAR(40) NOT NULL DEFAULT 'pending',
  amount_ngn BIGINT NOT NULL,
  commission_ngn BIGINT NOT NULL DEFAULT 0,
  professional_payable_ngn BIGINT NOT NULL DEFAULT 0,
  idempotency_key VARCHAR(160) UNIQUE NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE reviews (
  id UUID PRIMARY KEY,
  booking_id UUID UNIQUE NOT NULL REFERENCES bookings(id),
  customer_id UUID NOT NULL REFERENCES users(id),
  professional_id UUID NOT NULL REFERENCES professional_profiles(id),
  rating INT NOT NULL CHECK (rating BETWEEN 1 AND 5),
  body TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_logs (
  id UUID PRIMARY KEY,
  actor_user_id UUID REFERENCES users(id),
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id UUID,
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE embeddings (
  id UUID PRIMARY KEY,
  entity_type VARCHAR(60) NOT NULL,
  entity_id UUID NOT NULL,
  embedding vector(1536),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX embeddings_hnsw_idx ON embeddings USING hnsw (embedding vector_cosine_ops);

INSERT INTO categories (id,name,slug) VALUES
(gen_random_uuid(),'Design','design'),
(gen_random_uuid(),'Technology','technology'),
(gen_random_uuid(),'Consulting','consulting'),
(gen_random_uuid(),'Education','education'),
(gen_random_uuid(),'Home Services','home-services'),
(gen_random_uuid(),'Wellness','wellness')
ON CONFLICT (slug) DO NOTHING;

-- Sprint 2 additions (safe for fresh database initialization)
ALTER TABLE professional_profiles ADD COLUMN IF NOT EXISTS service_area VARCHAR(160);
ALTER TABLE professional_profiles ADD COLUMN IF NOT EXISTS onboarding_complete BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE services ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
