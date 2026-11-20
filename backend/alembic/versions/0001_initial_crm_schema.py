"""Initial Enterprise CRM schema with pgvector, forced RLS, and BYOK vault.

Revision ID: 0001_initial_crm
Revises:
Create Date: 2026-11-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0001_initial_crm"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATEMENTS = [
    'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"',
    'CREATE EXTENSION IF NOT EXISTS "pgcrypto"',
    'CREATE EXTENSION IF NOT EXISTS "vector"',
    'CREATE EXTENSION IF NOT EXISTS "pg_trgm"',
    """
    CREATE TABLE tenants (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name VARCHAR(255) NOT NULL,
        slug VARCHAR(100) NOT NULL UNIQUE,
        plan_tier VARCHAR(50) NOT NULL DEFAULT 'enterprise',
        is_active BOOLEAN NOT NULL DEFAULT true,
        settings JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
    )
    """,
    "CREATE INDEX idx_tenants_slug ON tenants(slug)",
    """
    CREATE TABLE users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        email VARCHAR(255) NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        full_name VARCHAR(255) NOT NULL,
        role VARCHAR(50) NOT NULL DEFAULT 'sales_rep',
        team_id UUID,
        is_active BOOLEAN NOT NULL DEFAULT true,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        CONSTRAINT uq_tenant_user_email UNIQUE (tenant_id, email)
    )
    """,
    "CREATE INDEX idx_users_tenant_role ON users(tenant_id, role)",
    "CREATE INDEX idx_users_tenant_email ON users(tenant_id, email)",
    """
    CREATE TABLE refresh_tokens (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        family_id UUID NOT NULL,
        token_hash VARCHAR(64) NOT NULL UNIQUE,
        is_revoked BOOLEAN NOT NULL DEFAULT false,
        expires_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
    )
    """,
    "CREATE INDEX idx_refresh_tokens_tenant_user ON refresh_tokens(tenant_id, user_id)",
    "CREATE INDEX idx_refresh_tokens_family ON refresh_tokens(tenant_id, family_id)",
    """
    CREATE TABLE accounts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        parent_account_id UUID REFERENCES accounts(id) ON DELETE SET NULL,
        name VARCHAR(255) NOT NULL,
        industry VARCHAR(100),
        website VARCHAR(255),
        annual_revenue NUMERIC(15, 2),
        employee_count INT,
        owner_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
    )
    """,
    "CREATE INDEX idx_accounts_tenant_owner ON accounts(tenant_id, owner_id)",
    "CREATE INDEX idx_accounts_tenant_parent ON accounts(tenant_id, parent_account_id)",
    "CREATE INDEX idx_accounts_tenant_name_trgm ON accounts USING gin (name gin_trgm_ops)",
    """
    CREATE TABLE contacts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        account_id UUID REFERENCES accounts(id) ON DELETE SET NULL,
        owner_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        first_name VARCHAR(100) NOT NULL,
        last_name VARCHAR(100) NOT NULL,
        email VARCHAR(255) NOT NULL,
        phone VARCHAR(50),
        job_title VARCHAR(150),
        lead_score NUMERIC(5, 2) NOT NULL DEFAULT 0.00,
        lifecycle_stage VARCHAR(50) NOT NULL DEFAULT 'lead',
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        CONSTRAINT uq_tenant_contact_email UNIQUE (tenant_id, email)
    )
    """,
    "CREATE INDEX idx_contacts_tenant_account ON contacts(tenant_id, account_id)",
    "CREATE INDEX idx_contacts_tenant_owner ON contacts(tenant_id, owner_id)",
    "CREATE INDEX idx_contacts_tenant_email ON contacts(tenant_id, email)",
    "CREATE INDEX idx_contacts_tenant_score ON contacts(tenant_id, lead_score DESC)",
    """
    CREATE TABLE pipelines (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        name VARCHAR(100) NOT NULL,
        is_default BOOLEAN NOT NULL DEFAULT false,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
    )
    """,
    "CREATE INDEX idx_pipelines_tenant ON pipelines(tenant_id)",
    """
    CREATE TABLE pipeline_stages (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        pipeline_id UUID NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
        name VARCHAR(100) NOT NULL,
        position INT NOT NULL,
        default_probability NUMERIC(5, 2) NOT NULL DEFAULT 0.10,
        is_closed_won BOOLEAN NOT NULL DEFAULT false,
        is_closed_lost BOOLEAN NOT NULL DEFAULT false,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        CONSTRAINT uq_pipeline_stage_order UNIQUE (pipeline_id, position)
    )
    """,
    "CREATE INDEX idx_pipeline_stages_tenant_pipeline ON pipeline_stages(tenant_id, pipeline_id, position)",
    """
    CREATE TABLE deals (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        pipeline_id UUID NOT NULL REFERENCES pipelines(id) ON DELETE RESTRICT,
        stage_id UUID NOT NULL REFERENCES pipeline_stages(id) ON DELETE RESTRICT,
        account_id UUID REFERENCES accounts(id) ON DELETE SET NULL,
        contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL,
        owner_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        title VARCHAR(255) NOT NULL,
        amount NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
        currency VARCHAR(3) NOT NULL DEFAULT 'USD',
        expected_close_date DATE,
        forecast_category VARCHAR(50) NOT NULL DEFAULT 'pipeline',
        win_probability NUMERIC(5, 2) NOT NULL,
        is_won BOOLEAN NOT NULL DEFAULT false,
        is_lost BOOLEAN NOT NULL DEFAULT false,
        loss_reason TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
    )
    """,
    "CREATE INDEX idx_deals_tenant_owner ON deals(tenant_id, owner_id)",
    "CREATE INDEX idx_deals_tenant_pipeline ON deals(tenant_id, pipeline_id)",
    "CREATE INDEX idx_deals_tenant_stage ON deals(tenant_id, stage_id)",
    "CREATE INDEX idx_deals_tenant_account ON deals(tenant_id, account_id)",
    "CREATE INDEX idx_deals_tenant_contact ON deals(tenant_id, contact_id)",
    "CREATE INDEX idx_deals_tenant_close_date ON deals(tenant_id, expected_close_date)",
    "CREATE INDEX idx_deals_tenant_forecast ON deals(tenant_id, forecast_category)",
    """
    CREATE TABLE interactions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        contact_id UUID REFERENCES contacts(id) ON DELETE CASCADE,
        account_id UUID REFERENCES accounts(id) ON DELETE CASCADE,
        deal_id UUID REFERENCES deals(id) ON DELETE CASCADE,
        type VARCHAR(50) NOT NULL,
        direction VARCHAR(20) NOT NULL DEFAULT 'outbound',
        subject VARCHAR(255) NOT NULL,
        content_body TEXT NOT NULL,
        encrypted_payload BYTEA,
        occurred_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
    )
    """,
    "CREATE INDEX idx_interactions_tenant_contact ON interactions(tenant_id, contact_id, occurred_at DESC)",
    "CREATE INDEX idx_interactions_tenant_deal ON interactions(tenant_id, deal_id, occurred_at DESC)",
    "CREATE INDEX idx_interactions_tenant_account ON interactions(tenant_id, account_id, occurred_at DESC)",
    """
    CREATE TABLE tasks (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        assigned_to UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        contact_id UUID REFERENCES contacts(id) ON DELETE CASCADE,
        deal_id UUID REFERENCES deals(id) ON DELETE CASCADE,
        title VARCHAR(255) NOT NULL,
        description TEXT,
        priority VARCHAR(20) NOT NULL DEFAULT 'medium',
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        due_date TIMESTAMPTZ NOT NULL,
        reminder_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
    )
    """,
    "CREATE INDEX idx_tasks_tenant_assignee_status ON tasks(tenant_id, assigned_to, status, due_date)",
    "CREATE INDEX idx_tasks_tenant_contact ON tasks(tenant_id, contact_id)",
    "CREATE INDEX idx_tasks_tenant_deal ON tasks(tenant_id, deal_id)",
    """
    CREATE TABLE lead_embeddings (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        entity_type VARCHAR(50) NOT NULL,
        entity_id UUID NOT NULL,
        chunk_index INT NOT NULL DEFAULT 0,
        text_content TEXT NOT NULL,
        embedding vector(768) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        CONSTRAINT uq_entity_chunk UNIQUE (tenant_id, entity_type, entity_id, chunk_index)
    )
    """,
    "CREATE INDEX idx_lead_embeddings_hnsw ON lead_embeddings USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)",
    "CREATE INDEX idx_lead_embeddings_tenant_entity ON lead_embeddings(tenant_id, entity_type, entity_id)",
    """
    CREATE TABLE outbox_events (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        aggregate_type VARCHAR(100) NOT NULL,
        aggregate_id UUID NOT NULL,
        event_type VARCHAR(100) NOT NULL,
        payload JSONB NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        retry_count INT NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        processed_at TIMESTAMPTZ
    )
    """,
    "CREATE INDEX idx_outbox_tenant ON outbox_events(tenant_id, created_at DESC)",
    "CREATE INDEX idx_outbox_pending ON outbox_events(status, created_at) WHERE status = 'pending'",
    """
    CREATE TABLE ai_proposals (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        agent_name VARCHAR(100) NOT NULL,
        action_type VARCHAR(100) NOT NULL,
        target_entity_type VARCHAR(50) NOT NULL,
        target_entity_id UUID NOT NULL,
        proposed_payload JSONB NOT NULL,
        reasoning_summary TEXT NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'pending_review',
        reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
        reviewed_at TIMESTAMPTZ,
        rejection_reason TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
    )
    """,
    "CREATE INDEX idx_ai_proposals_tenant_status ON ai_proposals(tenant_id, status)",
    "CREATE INDEX idx_ai_proposals_target ON ai_proposals(tenant_id, target_entity_type, target_entity_id)",
    """
    CREATE TABLE ai_audit_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        model_provider VARCHAR(50) NOT NULL,
        model_name VARCHAR(100) NOT NULL,
        prompt_sanitized_hash VARCHAR(64) NOT NULL,
        tokens_prompt INT NOT NULL,
        tokens_completion INT NOT NULL,
        latency_ms INT NOT NULL,
        mcp_tools_invoked JSONB NOT NULL DEFAULT '[]'::jsonb,
        is_safe_eval BOOLEAN NOT NULL DEFAULT true,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
    )
    """,
    "CREATE INDEX idx_ai_audit_tenant ON ai_audit_logs(tenant_id, created_at DESC)",
    """
    CREATE TABLE tenant_llm_credentials (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        provider VARCHAR(50) NOT NULL,
        encrypted_api_key BYTEA NOT NULL,
        key_last_four VARCHAR(4) NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT true,
        added_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        CONSTRAINT uq_tenant_provider UNIQUE (tenant_id, provider)
    )
    """,
    "CREATE INDEX idx_llm_creds_tenant_provider ON tenant_llm_credentials(tenant_id, provider) WHERE is_active = true",
    """
    CREATE OR REPLACE FUNCTION get_current_tenant_id() RETURNS UUID AS $$
    BEGIN
        RETURN NULLIF(current_setting('app.current_tenant_id', true), '')::UUID;
    END;
    $$ LANGUAGE plpgsql STABLE
    """,
    """
    CREATE OR REPLACE FUNCTION lookup_user_tenants_by_email(p_email VARCHAR)
    RETURNS TABLE (tenant_id UUID, tenant_slug VARCHAR, tenant_name VARCHAR)
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
    BEGIN
        RETURN QUERY
        SELECT t.id, t.slug, t.name
        FROM users u
        JOIN tenants t ON t.id = u.tenant_id
        WHERE lower(u.email) = lower(p_email)
          AND u.is_active = true
          AND t.is_active = true;
    END;
    $$
    """,
    """
    CREATE OR REPLACE FUNCTION lookup_refresh_token_tenant(p_token_hash VARCHAR)
    RETURNS UUID LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
    DECLARE v_tenant_id UUID;
    BEGIN
        SELECT rt.tenant_id INTO v_tenant_id
        FROM refresh_tokens rt
        WHERE rt.token_hash = p_token_hash
        LIMIT 1;
        RETURN v_tenant_id;
    END;
    $$
    """,
    """
    CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = clock_timestamp();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
]

_RLS_TABLES = [
    "users",
    "refresh_tokens",
    "accounts",
    "contacts",
    "pipelines",
    "pipeline_stages",
    "deals",
    "interactions",
    "tasks",
    "lead_embeddings",
    "outbox_events",
    "ai_proposals",
    "ai_audit_logs",
    "tenant_llm_credentials",
]

_TRIGGER_TABLES = [
    "tenants",
    "users",
    "accounts",
    "contacts",
    "deals",
    "tasks",
    "pipelines",
    "tenant_llm_credentials",
]


def upgrade() -> None:
    for stmt in _STATEMENTS:
        op.execute(stmt)

    for table in _RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"FOR ALL USING (tenant_id = get_current_tenant_id()) "
            f"WITH CHECK (tenant_id = get_current_tenant_id())"
        )

    for table in _TRIGGER_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'crm_app') THEN
                CREATE ROLE crm_app LOGIN PASSWORD 'crm_app_dev_pass'
                    NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
            END IF;
        END
        $$
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO crm_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO crm_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO crm_app")
    op.execute("GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO crm_app")


def downgrade() -> None:
    for table in reversed(_RLS_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP TABLE IF EXISTS tenants CASCADE")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS lookup_refresh_token_tenant(VARCHAR) CASCADE")
    op.execute("DROP FUNCTION IF EXISTS lookup_user_tenants_by_email(VARCHAR) CASCADE")
    op.execute("DROP FUNCTION IF EXISTS get_current_tenant_id() CASCADE")
