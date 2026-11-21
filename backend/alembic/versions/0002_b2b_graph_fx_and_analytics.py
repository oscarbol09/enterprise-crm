"""B2B multi-entity graph, custom fields registry, SCD Type 2 stage history,
FX normalization, email sync ledger, entity audit logs, and attribution fields.

Revision ID: 0002_b2b_graph_fx
Revises: 0001_initial_crm
Create Date: 2026-11-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002_b2b_graph_fx"
down_revision: Union[str, None] = "0001_initial_crm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_users_tenant_team ON users(tenant_id, team_id)",
    "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS merged_into_id UUID",
    "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ",
    "CREATE INDEX IF NOT EXISTS idx_accounts_metadata_gin ON accounts USING gin (metadata jsonb_path_ops)",
    "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS source_channel VARCHAR(100)",
    "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS merged_into_id UUID",
    "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ",
    "CREATE INDEX IF NOT EXISTS idx_contacts_metadata_gin ON contacts USING gin (metadata jsonb_path_ops)",
    "ALTER TABLE deals ADD COLUMN IF NOT EXISTS source_channel VARCHAR(100)",
    "ALTER TABLE deals ADD COLUMN IF NOT EXISTS loss_category VARCHAR(50)",
    "ALTER TABLE deals ADD COLUMN IF NOT EXISTS competitor_name VARCHAR(120)",
    "ALTER TABLE deals ADD COLUMN IF NOT EXISTS missing_feature_tag VARCHAR(120)",
    "ALTER TABLE deals ADD COLUMN IF NOT EXISTS last_inbound_activity_at TIMESTAMPTZ",
    "ALTER TABLE deals ADD COLUMN IF NOT EXISTS last_outbound_activity_at TIMESTAMPTZ",
    "ALTER TABLE deals ADD COLUMN IF NOT EXISTS exchange_rate_to_usd NUMERIC(14, 6) NOT NULL DEFAULT 1.000000",
    "ALTER TABLE deals ADD COLUMN IF NOT EXISTS normalized_amount_usd NUMERIC(15, 2) NOT NULL DEFAULT 0.00",
    "ALTER TABLE deals ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ",
    "ALTER TABLE deals ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE deals ADD COLUMN IF NOT EXISTS stage_entered_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()",
    "ALTER TABLE deals ADD COLUMN IF NOT EXISTS last_interaction_at TIMESTAMPTZ",
    "ALTER TABLE deals ADD COLUMN IF NOT EXISTS close_date_push_count INT NOT NULL DEFAULT 0",
    "ALTER TABLE deals ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ",
    "CREATE INDEX IF NOT EXISTS idx_deals_metadata_gin ON deals USING gin (metadata jsonb_path_ops)",
    """
    CREATE TABLE IF NOT EXISTS company_affiliations (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
        role_title VARCHAR(150),
        department VARCHAR(100),
        is_primary BOOLEAN NOT NULL DEFAULT false,
        is_active BOOLEAN NOT NULL DEFAULT true,
        started_at DATE,
        ended_at DATE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        CONSTRAINT uq_tenant_account_contact_affiliation UNIQUE (tenant_id, account_id, contact_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_affiliations_tenant_account ON company_affiliations(tenant_id, account_id)",
    "CREATE INDEX IF NOT EXISTS idx_affiliations_tenant_contact ON company_affiliations(tenant_id, contact_id)",
    """
    CREATE TABLE IF NOT EXISTS deal_participants (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        deal_id UUID NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
        contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
        buying_role VARCHAR(50) NOT NULL DEFAULT 'stakeholder',
        is_primary BOOLEAN NOT NULL DEFAULT false,
        notes TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        CONSTRAINT uq_tenant_deal_participant UNIQUE (tenant_id, deal_id, contact_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_deal_participants_tenant_deal ON deal_participants(tenant_id, deal_id)",
    "CREATE INDEX IF NOT EXISTS idx_deal_participants_tenant_contact ON deal_participants(tenant_id, contact_id)",
    """
    CREATE TABLE IF NOT EXISTS deal_stage_history (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        deal_id UUID NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
        from_stage_id UUID REFERENCES pipeline_stages(id) ON DELETE SET NULL,
        to_stage_id UUID NOT NULL REFERENCES pipeline_stages(id) ON DELETE RESTRICT,
        amount_at_transition NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
        win_probability_at_transition NUMERIC(5, 2) NOT NULL DEFAULT 0.10,
        expected_close_date_at_transition DATE,
        changed_by UUID REFERENCES users(id) ON DELETE SET NULL,
        entered_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        exited_at TIMESTAMPTZ,
        duration_seconds INT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_deal_stage_history_tenant_deal ON deal_stage_history(tenant_id, deal_id, entered_at ASC)",
    """
    CREATE TABLE IF NOT EXISTS custom_field_definitions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        entity_type VARCHAR(50) NOT NULL,
        field_key VARCHAR(100) NOT NULL,
        label VARCHAR(150) NOT NULL,
        field_type VARCHAR(50) NOT NULL,
        is_required BOOLEAN NOT NULL DEFAULT false,
        min_stage_position INT,
        allowed_values JSONB NOT NULL DEFAULT '[]'::jsonb,
        is_indexed BOOLEAN NOT NULL DEFAULT false,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        CONSTRAINT uq_tenant_entity_custom_field UNIQUE (tenant_id, entity_type, field_key)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_custom_fields_tenant_entity ON custom_field_definitions(tenant_id, entity_type)",
    """
    CREATE TABLE IF NOT EXISTS synced_email_messages (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        rfc_message_id VARCHAR(255) NOT NULL,
        thread_id VARCHAR(255),
        in_reply_to VARCHAR(255),
        sender_email VARCHAR(255) NOT NULL,
        recipient_emails JSONB NOT NULL DEFAULT '[]'::jsonb,
        synced_mailboxes JSONB NOT NULL DEFAULT '[]'::jsonb,
        interaction_id UUID REFERENCES interactions(id) ON DELETE SET NULL,
        contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL,
        account_id UUID REFERENCES accounts(id) ON DELETE SET NULL,
        deal_id UUID REFERENCES deals(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        CONSTRAINT uq_tenant_rfc_message_id UNIQUE (tenant_id, rfc_message_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_synced_emails_tenant_thread ON synced_email_messages(tenant_id, thread_id)",
    """
    CREATE TABLE IF NOT EXISTS entity_audit_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        entity_type VARCHAR(50) NOT NULL,
        entity_id UUID NOT NULL,
        action VARCHAR(50) NOT NULL,
        actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        changes JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_entity_audit_tenant_entity ON entity_audit_logs(tenant_id, entity_type, entity_id, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS import_batches (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        created_by UUID REFERENCES users(id) ON DELETE SET NULL,
        entity_scope VARCHAR(50) NOT NULL DEFAULT 'contacts_bundle',
        created_account_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_contact_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_deal_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
        status VARCHAR(30) NOT NULL DEFAULT 'committed',
        rolled_back_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_import_batches_tenant_created ON import_batches(tenant_id, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS pipeline_snapshots (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        snapshot_date DATE NOT NULL,
        deal_id UUID NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
        stage_id UUID NOT NULL,
        normalized_amount_usd NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
        forecast_category VARCHAR(50) NOT NULL DEFAULT 'pipeline',
        expected_close_date DATE,
        is_won BOOLEAN NOT NULL DEFAULT false,
        is_lost BOOLEAN NOT NULL DEFAULT false,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        CONSTRAINT uq_tenant_snapshot_date_deal UNIQUE (tenant_id, snapshot_date, deal_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_pipeline_snapshots_tenant_date ON pipeline_snapshots(tenant_id, snapshot_date)",
]

_NEW_RLS_TABLES = [
    "company_affiliations",
    "deal_participants",
    "deal_stage_history",
    "custom_field_definitions",
    "synced_email_messages",
    "entity_audit_logs",
    "import_batches",
    "pipeline_snapshots",
]


def upgrade() -> None:
    for stmt in _STATEMENTS:
        op.execute(stmt)

    for table in _NEW_RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"FOR ALL USING (tenant_id = get_current_tenant_id()) "
            f"WITH CHECK (tenant_id = get_current_tenant_id())"
        )

    for table in ("company_affiliations", "custom_field_definitions"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated ON {table}")
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO crm_app")


def downgrade() -> None:
    for table in reversed(_NEW_RLS_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("ALTER TABLE deals DROP COLUMN IF EXISTS deleted_at")
    op.execute("ALTER TABLE deals DROP COLUMN IF EXISTS close_date_push_count")
    op.execute("ALTER TABLE deals DROP COLUMN IF EXISTS last_interaction_at")
    op.execute("ALTER TABLE deals DROP COLUMN IF EXISTS stage_entered_at")
    op.execute("ALTER TABLE deals DROP COLUMN IF EXISTS metadata")
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS deleted_at")
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS merged_into_id")
    op.execute("ALTER TABLE accounts DROP COLUMN IF EXISTS deleted_at")
    op.execute("ALTER TABLE accounts DROP COLUMN IF EXISTS merged_into_id")
