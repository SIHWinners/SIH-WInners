"""postgres-only features: PostGIS geometry, GiST/BRIN/trigram/partial indexes,
monthly partitions, row level security, append-only audit trigger

On SQLite (local profile, ADR-001) this migration is a no-op.

Revision ID: c2e8f1a90b11
Revises: b1d7d200abb5
Create Date: 2026-09-16 21:05:00
"""
from collections.abc import Sequence

from alembic import op

revision: str = "c2e8f1a90b11"
down_revision: str | None = "b1d7d200abb5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _run(script: str) -> None:
    """asyncpg runs one statement per call, so split on semicolons outside $$ bodies."""
    statement, in_dollar = [], False
    for line in script.splitlines():
        if not in_dollar and line.lstrip().startswith("--"):
            continue  # whole-line comments outside function bodies
        in_dollar ^= line.count("$$") % 2 == 1
        statement.append(line)
        if not in_dollar and line.rstrip().endswith(";"):
            sql = "\n".join(statement).strip()
            if sql.strip(";").strip():
                op.execute(sql)
            statement = []
    rest = "\n".join(statement).strip()
    if rest:
        op.execute(rest)


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


GEO_AND_INDEXES = """
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE partners ADD COLUMN geom geometry(Point, 4326)
  GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lng, lat), 4326)) STORED;
ALTER TABLE applicants ADD COLUMN geom geometry(Point, 4326)
  GENERATED ALWAYS AS (CASE WHEN lat IS NULL OR lng IS NULL THEN NULL
                       ELSE ST_SetSRID(ST_MakePoint(lng, lat), 4326) END) STORED;
CREATE INDEX ix_partners_geom ON partners USING gist (geom);
CREATE INDEX ix_applicants_geom ON applicants USING gist (geom);
CREATE INDEX ix_applicants_name_trgm ON applicants USING gin (name_normalized gin_trgm_ops);

DROP INDEX IF EXISTS ix_applications_status_open;
CREATE INDEX ix_applications_status_open ON applications (status)
  WHERE status IN ('submitted', 'under_review');
"""

# Partitioned tables need the partition key inside every unique constraint.
PARTITIONS = """
ALTER TABLE analytics_events RENAME TO analytics_events_old;
CREATE TABLE analytics_events (LIKE analytics_events_old INCLUDING DEFAULTS) PARTITION BY RANGE (ts);
ALTER TABLE analytics_events ADD PRIMARY KEY (id, ts);
-- LIKE ... INCLUDING DEFAULTS keeps nextval() on the original sequence; move its ownership
-- so dropping the old table does not take the sequence with it.
ALTER SEQUENCE analytics_events_id_seq OWNED BY analytics_events.id;
CREATE TABLE analytics_events_default PARTITION OF analytics_events DEFAULT;
INSERT INTO analytics_events SELECT * FROM analytics_events_old;
DROP TABLE analytics_events_old;
CREATE INDEX ix_analytics_events_ts_brin ON analytics_events USING brin (ts);

ALTER TABLE audit_log RENAME TO audit_log_old;
CREATE TABLE audit_log (LIKE audit_log_old INCLUDING DEFAULTS) PARTITION BY RANGE (at);
ALTER TABLE audit_log ADD PRIMARY KEY (seq, at);
ALTER TABLE audit_log ADD CONSTRAINT uq_audit_log_id_at UNIQUE (id, at);
ALTER SEQUENCE audit_log_seq_seq OWNED BY audit_log.seq;
CREATE TABLE audit_log_default PARTITION OF audit_log DEFAULT;
INSERT INTO audit_log SELECT * FROM audit_log_old;
DROP TABLE audit_log_old;
CREATE INDEX ix_audit_log_entity ON audit_log (entity);

-- Creates next month's partitions; run monthly by the worker (and once now).
CREATE OR REPLACE FUNCTION sm_ensure_month_partitions(target date) RETURNS void AS $$
DECLARE
  start_d date := date_trunc('month', target);
  end_d date := (date_trunc('month', target) + interval '1 month')::date;
  suffix text := to_char(start_d, 'YYYY_MM');
BEGIN
  EXECUTE format('CREATE TABLE IF NOT EXISTS analytics_events_%s PARTITION OF analytics_events
                  FOR VALUES FROM (%L) TO (%L)', suffix, start_d, end_d);
  EXECUTE format('CREATE TABLE IF NOT EXISTS audit_log_%s PARTITION OF audit_log
                  FOR VALUES FROM (%L) TO (%L)', suffix, start_d, end_d);
END $$ LANGUAGE plpgsql;
"""

AUDIT_APPEND_ONLY = """
CREATE OR REPLACE FUNCTION sm_audit_append_only() RETURNS trigger AS $$
BEGIN
  -- The only permitted update fills the hash placeholders of a just-inserted row.
  IF TG_OP = 'UPDATE' AND OLD.hash = '' THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'audit_log is append-only';
END $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_audit_append_only BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION sm_audit_append_only();
"""

# Requests from citizens, operators and partner officers run as `sm_app` with the verified
# JWT claims in `request.jwt.claims` (see app/db/session.py). Admin/system work keeps the
# owner role. Policies mirror the checks the services already make (defence in depth).
RLS = """
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sm_app') THEN
    CREATE ROLE sm_app NOLOGIN;
  END IF;
END $$;
GRANT sm_app TO CURRENT_USER;
GRANT USAGE ON SCHEMA public TO sm_app;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO sm_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sm_app;

CREATE OR REPLACE FUNCTION sm_claims() RETURNS jsonb LANGUAGE sql STABLE AS
  $$ SELECT coalesce(nullif(current_setting('request.jwt.claims', true), ''), '{}')::jsonb $$;
CREATE OR REPLACE FUNCTION sm_uid() RETURNS uuid LANGUAGE sql STABLE AS
  $$ SELECT nullif(sm_claims()->>'sub', '')::uuid $$;
CREATE OR REPLACE FUNCTION sm_role() RETURNS text LANGUAGE sql STABLE AS
  $$ SELECT sm_claims()->>'app_role' $$;
CREATE OR REPLACE FUNCTION sm_partner() RETURNS uuid LANGUAGE sql STABLE AS
  $$ SELECT nullif(sm_claims()->>'partner_id', '')::uuid $$;

ALTER TABLE applicants ENABLE ROW LEVEL SECURITY;
ALTER TABLE applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE consents ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY applicants_owner ON applicants FOR ALL TO sm_app USING (
  sm_role() = 'admin'
  OR (sm_role() = 'citizen' AND user_id = sm_uid())
  OR (sm_role() = 'csc_operator' AND created_by_operator_id = sm_uid())
  OR (sm_role() = 'partner_officer' AND EXISTS (
        SELECT 1 FROM applications a WHERE a.applicant_id = applicants.id AND a.partner_id = sm_partner()))
) WITH CHECK (sm_role() IN ('admin', 'citizen', 'csc_operator'));

CREATE POLICY applications_scope ON applications FOR ALL TO sm_app USING (
  sm_role() = 'admin'
  OR (sm_role() = 'citizen' AND EXISTS (
        SELECT 1 FROM applicants p WHERE p.id = applications.applicant_id AND p.user_id = sm_uid()))
  OR (sm_role() = 'csc_operator' AND created_by_user_id = sm_uid())
  OR (sm_role() = 'partner_officer' AND partner_id = sm_partner()
      AND status NOT IN ('draft', 'ready'))
);

CREATE POLICY documents_scope ON documents FOR ALL TO sm_app USING (
  EXISTS (SELECT 1 FROM applications a WHERE a.id = documents.application_id)
);
CREATE POLICY conversations_scope ON conversations FOR ALL TO sm_app USING (
  sm_role() = 'admin' OR user_id = sm_uid()
);
CREATE POLICY consents_scope ON consents FOR ALL TO sm_app USING (
  sm_role() = 'admin' OR EXISTS (SELECT 1 FROM applicants p WHERE p.id = consents.applicant_id)
);
CREATE POLICY analytics_insert ON analytics_events FOR INSERT TO sm_app WITH CHECK (true);
CREATE POLICY analytics_read ON analytics_events FOR SELECT TO sm_app
  USING (sm_role() IN ('policy_viewer', 'admin'));
"""


def upgrade() -> None:
    if not _is_pg():
        return
    _run(GEO_AND_INDEXES)
    _run(PARTITIONS)
    op.execute("SELECT sm_ensure_month_partitions(current_date)")
    op.execute("SELECT sm_ensure_month_partitions((current_date + interval '1 month')::date)")
    _run(AUDIT_APPEND_ONLY)
    _run(RLS)


def downgrade() -> None:
    if not _is_pg():
        return
    for table in ("applicants", "applications", "documents", "consents", "conversations", "analytics_events"):
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_append_only ON audit_log")
    op.execute("ALTER TABLE partners DROP COLUMN IF EXISTS geom")
    op.execute("ALTER TABLE applicants DROP COLUMN IF EXISTS geom")
