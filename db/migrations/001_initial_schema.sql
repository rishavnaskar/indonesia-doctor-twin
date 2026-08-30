-- The durable side of one deployment.
--
-- Three tables, matching the three things a run produces: what the workflow
-- saw at each step, who signed what, and what is waiting to be sent. All three
-- are append-only logs rather than mutable rows, which is the same shape the
-- file backend uses and for the same reason — the question asked of this data
-- later is "what did the system see at the time", and a row you can overwrite
-- cannot answer it.
--
-- Migrations are numbered and applied in filename order, tracked in
-- schema_migrations. Postgres also runs this directory itself on a fresh
-- container (docker-entrypoint-initdb.d), so a first `docker compose up` and a
-- later application start converge on the same schema by two different paths.
-- Every statement is therefore written to be safe to run twice.

CREATE TABLE IF NOT EXISTS schema_migrations (
  name       TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- checkpoints

-- One row per workflow step. `sequence` is the position within a thread, and
-- is NOT unique here on purpose: re-running a thread after a crash rewrites
-- positions that already exist, and the log keeps both so the earlier attempt
-- stays visible. Readers take the newest row per (thread_id, sequence) via
-- DISTINCT ON, which reproduces the file backend's "later entries win".
--
-- `id` is BIGSERIAL rather than a timestamp because created_at collides at
-- sub-millisecond granularity — a workflow writes several checkpoints inside
-- one millisecond — and ordering the audit trail by a colliding key is how
-- steps get replayed out of order.
CREATE TABLE IF NOT EXISTS checkpoints (
  id         BIGSERIAL PRIMARY KEY,
  thread_id  TEXT NOT NULL,
  sequence   INTEGER NOT NULL,
  step       TEXT NOT NULL,
  state      JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_replay
  ON checkpoints (thread_id, sequence, id DESC);

-- ----------------------------------------------------------------- signatures

-- The artefact that makes an output lawful. Never updated, never deleted.
--
-- `decision` is constrained here as well as in the application because this
-- table outlives the process that wrote it: a later tool, a migration script
-- or a psql session is not going to import our enum.
CREATE TABLE IF NOT EXISTS signatures (
  id                  BIGSERIAL PRIMARY KEY,
  practitioner_id     TEXT NOT NULL,
  role                TEXT NOT NULL,
  licence_expires     DATE NOT NULL,
  decision            TEXT NOT NULL CHECK (decision IN ('accepted', 'edited', 'rejected')),
  proposal_provenance JSONB NOT NULL,
  signed_at           TIMESTAMPTZ NOT NULL,
  rejection_reason    TEXT,
  edit_diff           TEXT,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_signatures_practitioner
  ON signatures (practitioner_id, signed_at DESC);

-- ------------------------------------------------------------------- outbound

-- One row per state transition, not one row per item. Enqueue writes 'pending';
-- a drain writes 'sent' or another 'pending' carrying the error. The current
-- state of an item is its newest row.
--
-- Nothing is ever deleted from here either. "How many times did this bundle
-- fail before it went out, and with what error" is a question the operator of a
-- site with one bar of signal will ask, and a queue that erases its own
-- attempts cannot answer it.
CREATE TABLE IF NOT EXISTS outbound (
  id              BIGSERIAL PRIMARY KEY,
  idempotency_key TEXT NOT NULL,
  kind            TEXT NOT NULL,
  payload         JSONB NOT NULL,
  status          TEXT NOT NULL CHECK (status IN ('pending', 'sent', 'failed')),
  attempts        INTEGER NOT NULL DEFAULT 0,
  last_error      TEXT,
  enqueued_at     TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_outbound_latest
  ON outbound (idempotency_key, id DESC);

-- ------------------------------------------------------- append-only, enforced

-- The reason this is worth having a database for.
--
-- A JSONL audit log is append-only by convention: any text editor can rewrite a
-- signature after the fact and nothing in the file records that it happened.
-- Here the constraint is the database's, not the application's. An UPDATE or
-- DELETE against a signature or a checkpoint raises, whoever issues it and
-- however they connect.
--
-- This is deliberately a trigger that fails loudly rather than a rule that
-- discards the write. A silently ignored UPDATE looks to the caller exactly
-- like a successful one, which is the worst available outcome for a table whose
-- entire job is being trustworthy.
CREATE OR REPLACE FUNCTION refuse_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'append-only table: % on % is refused', TG_OP, TG_TABLE_NAME
    USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS signatures_append_only ON signatures;
CREATE TRIGGER signatures_append_only
  BEFORE UPDATE OR DELETE ON signatures
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();

DROP TRIGGER IF EXISTS checkpoints_append_only ON checkpoints;
CREATE TRIGGER checkpoints_append_only
  BEFORE UPDATE OR DELETE ON checkpoints
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();

DROP TRIGGER IF EXISTS outbound_append_only ON outbound;
CREATE TRIGGER outbound_append_only
  BEFORE UPDATE OR DELETE ON outbound
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();
