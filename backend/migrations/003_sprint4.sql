CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS disputes (
 id UUID PRIMARY KEY, booking_id UUID UNIQUE NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
 opened_by UUID NOT NULL REFERENCES users(id), reason VARCHAR(500) NOT NULL, details TEXT NOT NULL,
 status VARCHAR(40) NOT NULL DEFAULT 'open', resolution TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS project_attachments (
 id UUID PRIMARY KEY, booking_id UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
 uploaded_by UUID NOT NULL REFERENCES users(id), filename VARCHAR(255) NOT NULL, mime_type VARCHAR(120) NOT NULL,
 size_bytes BIGINT NOT NULL, storage_key VARCHAR(255) UNIQUE NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE payments ADD COLUMN IF NOT EXISTS paid_at TIMESTAMPTZ;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS failure_reason TEXT;
ALTER TABLE professional_profiles ADD COLUMN IF NOT EXISTS embedding vector(64);
CREATE INDEX IF NOT EXISTS project_attachments_booking_idx ON project_attachments(booking_id, created_at DESC);
CREATE INDEX IF NOT EXISTS disputes_status_idx ON disputes(status, created_at DESC);
CREATE INDEX IF NOT EXISTS professional_embedding_idx ON professional_profiles USING ivfflat (embedding vector_cosine_ops) WITH (lists = 20);
