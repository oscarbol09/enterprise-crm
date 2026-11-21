-- ============================================================================
-- ENTERPRISE CRM DATABASE SCHEMA (PostgreSQL 16+ with pgvector & Forced RLS)
-- Multi-tenancy Model: Shared Database, Shared Tables with Forced RLS
-- ============================================================================

-- 1. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- 2. TENANTS & IDENTITY SCHEMAS
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    plan_tier VARCHAR(50) NOT NULL DEFAULT 'enterprise',
    is_active BOOLEAN NOT NULL DEFAULT true,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_tenants_slug ON tenants(slug);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'sales_rep', -- admin, sales_manager, sales_rep, readonly
    team_id UUID,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_tenant_user_email UNIQUE (tenant_id, email)
);

CREATE INDEX idx_users_tenant_role ON users(tenant_id, role);
CREATE INDEX idx_users_tenant_email ON users(tenant_id, email);
CREATE INDEX idx_users_tenant_team ON users(tenant_id, team_id);

-- Refresh Token Family Ledger (Supports Rotation & Reuse Detection)
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    family_id UUID NOT NULL,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    is_revoked BOOLEAN NOT NULL DEFAULT false,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_refresh_tokens_tenant_user ON refresh_tokens(tenant_id, user_id);
CREATE INDEX idx_refresh_tokens_family ON refresh_tokens(tenant_id, family_id);

-- 3. ACCOUNTS (COMPANIES) & HIERARCHIES
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
    merged_into_id UUID,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_accounts_tenant_owner ON accounts(tenant_id, owner_id);
CREATE INDEX idx_accounts_tenant_parent ON accounts(tenant_id, parent_account_id);
CREATE INDEX idx_accounts_tenant_name_trgm ON accounts USING gin (name gin_trgm_ops);
CREATE INDEX idx_accounts_metadata_gin ON accounts USING gin (metadata jsonb_path_ops);

-- 4. CONTACTS & MULTI-COMPANY AFFILIATIONS
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
    lifecycle_stage VARCHAR(50) NOT NULL DEFAULT 'lead', -- lead, marketing_qualified, sales_qualified, customer, churned
    source_channel VARCHAR(100), -- organic, outbound, paid_search, referral, partner, event, inbound
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    merged_into_id UUID,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_tenant_contact_email UNIQUE (tenant_id, email)
);

CREATE INDEX idx_contacts_tenant_account ON contacts(tenant_id, account_id);
CREATE INDEX idx_contacts_tenant_owner ON contacts(tenant_id, owner_id);
CREATE INDEX idx_contacts_tenant_email ON contacts(tenant_id, email);
CREATE INDEX idx_contacts_tenant_score ON contacts(tenant_id, lead_score DESC);
CREATE INDEX idx_contacts_metadata_gin ON contacts USING gin (metadata jsonb_path_ops);

CREATE TABLE company_affiliations (
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
);

CREATE INDEX idx_affiliations_tenant_account ON company_affiliations(tenant_id, account_id);
CREATE INDEX idx_affiliations_tenant_contact ON company_affiliations(tenant_id, contact_id);

-- 5. PIPELINES, STAGES, DEALS, BUYING COMMITTEE & SCD TYPE 2 STAGE HISTORY
CREATE TABLE pipelines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_pipelines_tenant ON pipelines(tenant_id);

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
);

CREATE INDEX idx_pipeline_stages_tenant_pipeline ON pipeline_stages(tenant_id, pipeline_id, position);

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
    exchange_rate_to_usd NUMERIC(14, 6) NOT NULL DEFAULT 1.000000,
    normalized_amount_usd NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    expected_close_date DATE,
    forecast_category VARCHAR(50) NOT NULL DEFAULT 'pipeline', -- pipeline, best_case, commit, closed, omitted
    win_probability NUMERIC(5, 2) NOT NULL,
    is_won BOOLEAN NOT NULL DEFAULT false,
    is_lost BOOLEAN NOT NULL DEFAULT false,
    loss_reason TEXT,
    loss_category VARCHAR(50),
    competitor_name VARCHAR(120),
    missing_feature_tag VARCHAR(120),
    source_channel VARCHAR(100),
    closed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    stage_entered_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    last_interaction_at TIMESTAMPTZ,
    last_inbound_activity_at TIMESTAMPTZ,
    last_outbound_activity_at TIMESTAMPTZ,
    close_date_push_count INT NOT NULL DEFAULT 0,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_deals_tenant_owner ON deals(tenant_id, owner_id);
CREATE INDEX idx_deals_tenant_pipeline ON deals(tenant_id, pipeline_id);
CREATE INDEX idx_deals_tenant_stage ON deals(tenant_id, stage_id);
CREATE INDEX idx_deals_tenant_account ON deals(tenant_id, account_id);
CREATE INDEX idx_deals_tenant_contact ON deals(tenant_id, contact_id);
CREATE INDEX idx_deals_tenant_close_date ON deals(tenant_id, expected_close_date);
CREATE INDEX idx_deals_tenant_forecast ON deals(tenant_id, forecast_category);
CREATE INDEX idx_deals_metadata_gin ON deals USING gin (metadata jsonb_path_ops);

CREATE TABLE deal_participants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    deal_id UUID NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    buying_role VARCHAR(50) NOT NULL DEFAULT 'stakeholder', -- champion, economic_buyer, technical_evaluator, legal_blocker, executive_sponsor, stakeholder
    is_primary BOOLEAN NOT NULL DEFAULT false,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_tenant_deal_participant UNIQUE (tenant_id, deal_id, contact_id)
);

CREATE INDEX idx_deal_participants_tenant_deal ON deal_participants(tenant_id, deal_id);
CREATE INDEX idx_deal_participants_tenant_contact ON deal_participants(tenant_id, contact_id);

CREATE TABLE deal_stage_history (
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
);

CREATE INDEX idx_deal_stage_history_tenant_deal ON deal_stage_history(tenant_id, deal_id, entered_at ASC);

-- 5B. DYNAMIC CUSTOM FIELDS METADATA REGISTRY
CREATE TABLE custom_field_definitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    entity_type VARCHAR(50) NOT NULL, -- account, contact, deal
    field_key VARCHAR(100) NOT NULL,
    label VARCHAR(150) NOT NULL,
    field_type VARCHAR(50) NOT NULL, -- text, number, boolean, date, select, multi_select
    is_required BOOLEAN NOT NULL DEFAULT false,
    min_stage_position INT,
    allowed_values JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_indexed BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_tenant_entity_custom_field UNIQUE (tenant_id, entity_type, field_key)
);

CREATE INDEX idx_custom_fields_tenant_entity ON custom_field_definitions(tenant_id, entity_type);

-- 6. INTERACTIONS, EMAIL SYNC & SYSTEM AUDIT LOGS
CREATE TABLE interactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL,
    account_id UUID REFERENCES accounts(id) ON DELETE SET NULL,
    deal_id UUID REFERENCES deals(id) ON DELETE SET NULL,
    type VARCHAR(50) NOT NULL, -- email, call, meeting, note, task_completed, stage_change
    direction VARCHAR(20) NOT NULL DEFAULT 'outbound', -- inbound, outbound, internal
    subject VARCHAR(255) NOT NULL,
    content_body TEXT NOT NULL,
    encrypted_payload BYTEA, -- Optional application-level encrypted content (AES-256-GCM)
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_interactions_tenant_contact ON interactions(tenant_id, contact_id, occurred_at DESC, id DESC);
CREATE INDEX idx_interactions_tenant_deal ON interactions(tenant_id, deal_id, occurred_at DESC, id DESC);
CREATE INDEX idx_interactions_tenant_account ON interactions(tenant_id, account_id, occurred_at DESC, id DESC);

CREATE TABLE synced_email_messages (
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
);

CREATE INDEX idx_synced_emails_tenant_thread ON synced_email_messages(tenant_id, thread_id);

CREATE TABLE entity_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    action VARCHAR(50) NOT NULL, -- CREATE, UPDATE, SOFT_DELETE, MERGE, STAGE_CHANGE
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    changes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_entity_audit_tenant_entity ON entity_audit_logs(tenant_id, entity_type, entity_id, created_at DESC);

-- 7. TASKS & REMINDERS
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    assigned_to UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL,
    deal_id UUID REFERENCES deals(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    priority VARCHAR(20) NOT NULL DEFAULT 'medium', -- low, medium, high, urgent
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending, in_progress, completed, cancelled
    due_date TIMESTAMPTZ NOT NULL,
    reminder_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_tasks_tenant_assignee_status ON tasks(tenant_id, assigned_to, status, due_date);
CREATE INDEX idx_tasks_tenant_contact ON tasks(tenant_id, contact_id);
CREATE INDEX idx_tasks_tenant_deal ON tasks(tenant_id, deal_id);

-- 8. PGVECTOR SEMANTIC KNOWLEDGE STORE (Contact / Deal Profile Embeddings)
CREATE TABLE lead_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    entity_type VARCHAR(50) NOT NULL, -- contact, deal, account, interaction_note
    entity_id UUID NOT NULL,
    chunk_index INT NOT NULL DEFAULT 0,
    text_content TEXT NOT NULL,
    embedding vector(768) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_entity_chunk UNIQUE (tenant_id, entity_type, entity_id, chunk_index)
);

CREATE INDEX idx_lead_embeddings_hnsw ON lead_embeddings
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_lead_embeddings_tenant_entity ON lead_embeddings(tenant_id, entity_type, entity_id);

-- 9. TRANSACTIONAL OUTBOX PATTERN (Guaranteed Atomic Event Publishing)
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    aggregate_type VARCHAR(100) NOT NULL, -- contact, deal, interaction, task
    aggregate_id UUID NOT NULL,
    event_type VARCHAR(100) NOT NULL, -- ContactCreated, DealCreated, DealStageChanged, InteractionLogged
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending, published, failed
    retry_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    processed_at TIMESTAMPTZ
);

CREATE INDEX idx_outbox_tenant ON outbox_events(tenant_id, created_at DESC);
CREATE INDEX idx_outbox_pending ON outbox_events(status, created_at) WHERE status = 'pending';

-- 10. AI AGENT AUDIT LOGS & PROPOSALS (Human-in-the-Loop Guardrail)
CREATE TABLE ai_proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_name VARCHAR(100) NOT NULL,
    action_type VARCHAR(100) NOT NULL, -- update_deal_stage, send_followup_email, schedule_followup, reassign_lead
    target_entity_type VARCHAR(50) NOT NULL,
    target_entity_id UUID NOT NULL,
    proposed_payload JSONB NOT NULL,
    reasoning_summary TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending_review', -- pending_review, approved, rejected, expired
    reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    rejection_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_ai_proposals_tenant_status ON ai_proposals(tenant_id, status);
CREATE INDEX idx_ai_proposals_target ON ai_proposals(tenant_id, target_entity_type, target_entity_id);

CREATE TABLE ai_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    model_provider VARCHAR(50) NOT NULL, -- gemini, claude, openai
    model_name VARCHAR(100) NOT NULL,
    prompt_sanitized_hash VARCHAR(64) NOT NULL,
    tokens_prompt INT NOT NULL,
    tokens_completion INT NOT NULL,
    latency_ms INT NOT NULL,
    mcp_tools_invoked JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_safe_eval BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_ai_audit_tenant ON ai_audit_logs(tenant_id, created_at DESC);

-- 11. TENANT LLM CREDENTIALS (BYOK Multi-Tenant Vault)
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
);

CREATE INDEX idx_llm_creds_tenant_provider ON tenant_llm_credentials(tenant_id, provider) WHERE is_active = true;

-- 11B. CSV IMPORT BATCHES (ATOMIC ROLLBACK) & PIPELINE SNAPSHOTS (WATERFALL BRIDGE)
CREATE TABLE import_batches (
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
);

CREATE INDEX idx_import_batches_tenant_created ON import_batches(tenant_id, created_at DESC);

CREATE TABLE pipeline_snapshots (
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
);

CREATE INDEX idx_pipeline_snapshots_tenant_date ON pipeline_snapshots(tenant_id, snapshot_date);

-- ============================================================================
-- 12. ROW-LEVEL SECURITY (RLS) POLICIES & HELPER FUNCTIONS
-- Multi-Tenancy Enforced at Database Engine Level (WITH FORCE RLS)
-- ============================================================================

CREATE OR REPLACE FUNCTION get_current_tenant_id() RETURNS UUID AS $$
BEGIN
    RETURN NULLIF(current_setting('app.current_tenant_id', true), '')::UUID;
END;
$$ LANGUAGE plpgsql STABLE;

-- Controlled login discovery: returns only tenant identifiers for an active email
-- so password and user queries always run inside tenant RLS scope.
CREATE OR REPLACE FUNCTION lookup_user_tenants_by_email(p_email VARCHAR)
RETURNS TABLE (
    tenant_id UUID,
    tenant_slug VARCHAR,
    tenant_name VARCHAR
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    SELECT t.id, t.slug, t.name
    FROM users u
    JOIN tenants t ON t.id = u.tenant_id
    WHERE lower(u.email) = lower(p_email)
      AND u.is_active = true
      AND t.is_active = true;
END;
$$;

-- Resolve tenant_id from a refresh token hash during cookie refresh before session binding.
CREATE OR REPLACE FUNCTION lookup_refresh_token_tenant(p_token_hash VARCHAR)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_tenant_id UUID;
BEGIN
    SELECT rt.tenant_id INTO v_tenant_id
    FROM refresh_tokens rt
    WHERE rt.token_hash = p_token_hash
    LIMIT 1;
    RETURN v_tenant_id;
END;
$$;

-- Enable AND Force RLS on all 20 tenant-isolated tables (prevents table-owner bypass)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;

ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE refresh_tokens FORCE ROW LEVEL SECURITY;

ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounts FORCE ROW LEVEL SECURITY;

ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE contacts FORCE ROW LEVEL SECURITY;

ALTER TABLE company_affiliations ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_affiliations FORCE ROW LEVEL SECURITY;

ALTER TABLE pipelines ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipelines FORCE ROW LEVEL SECURITY;

ALTER TABLE pipeline_stages ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_stages FORCE ROW LEVEL SECURITY;

ALTER TABLE deals ENABLE ROW LEVEL SECURITY;
ALTER TABLE deals FORCE ROW LEVEL SECURITY;

ALTER TABLE deal_participants ENABLE ROW LEVEL SECURITY;
ALTER TABLE deal_participants FORCE ROW LEVEL SECURITY;

ALTER TABLE deal_stage_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE deal_stage_history FORCE ROW LEVEL SECURITY;

ALTER TABLE custom_field_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE custom_field_definitions FORCE ROW LEVEL SECURITY;

ALTER TABLE interactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE interactions FORCE ROW LEVEL SECURITY;

ALTER TABLE synced_email_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE synced_email_messages FORCE ROW LEVEL SECURITY;

ALTER TABLE entity_audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE entity_audit_logs FORCE ROW LEVEL SECURITY;

ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks FORCE ROW LEVEL SECURITY;

ALTER TABLE lead_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE lead_embeddings FORCE ROW LEVEL SECURITY;

ALTER TABLE outbox_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbox_events FORCE ROW LEVEL SECURITY;

ALTER TABLE ai_proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_proposals FORCE ROW LEVEL SECURITY;

ALTER TABLE ai_audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_audit_logs FORCE ROW LEVEL SECURITY;

ALTER TABLE tenant_llm_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_llm_credentials FORCE ROW LEVEL SECURITY;

ALTER TABLE import_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE import_batches FORCE ROW LEVEL SECURITY;

ALTER TABLE pipeline_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_snapshots FORCE ROW LEVEL SECURITY;

-- Tenant Isolation Policies (USING + WITH CHECK prevent cross-tenant reads & writes)
CREATE POLICY tenant_isolation_users ON users
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_refresh_tokens ON refresh_tokens
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_accounts ON accounts
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_contacts ON contacts
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_company_affiliations ON company_affiliations
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_pipelines ON pipelines
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_pipeline_stages ON pipeline_stages
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_deals ON deals
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_deal_participants ON deal_participants
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_deal_stage_history ON deal_stage_history
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_custom_field_definitions ON custom_field_definitions
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_interactions ON interactions
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_synced_email_messages ON synced_email_messages
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_entity_audit_logs ON entity_audit_logs
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_tasks ON tasks
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_lead_embeddings ON lead_embeddings
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_outbox ON outbox_events
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_ai_proposals ON ai_proposals
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_ai_audit ON ai_audit_logs
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_llm_creds ON tenant_llm_credentials
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_import_batches ON import_batches
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

CREATE POLICY tenant_isolation_pipeline_snapshots ON pipeline_snapshots
    FOR ALL USING (tenant_id = get_current_tenant_id())
    WITH CHECK (tenant_id = get_current_tenant_id());

-- Automatic updated_at trigger function
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = clock_timestamp();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tenants_updated BEFORE UPDATE ON tenants FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_accounts_updated BEFORE UPDATE ON accounts FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_contacts_updated BEFORE UPDATE ON contacts FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_company_affiliations_updated BEFORE UPDATE ON company_affiliations FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_deals_updated BEFORE UPDATE ON deals FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_custom_field_definitions_updated BEFORE UPDATE ON custom_field_definitions FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_tasks_updated BEFORE UPDATE ON tasks FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_pipelines_updated BEFORE UPDATE ON pipelines FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_llm_creds_updated BEFORE UPDATE ON tenant_llm_credentials FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 13. LEAST-PRIVILEGE APPLICATION ROLE (NOBYPASSRLS)
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'crm_app') THEN
        CREATE ROLE crm_app LOGIN PASSWORD 'crm_app_dev_pass' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO crm_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO crm_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO crm_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO crm_app;
