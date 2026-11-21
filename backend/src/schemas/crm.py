"""
Pydantic v2 Schemas for Enterprise CRM (Strict Validation & Type Safety).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ============================================================================
# AUTHENTICATION & WORKSPACE IDENTITY SCHEMAS
# ============================================================================
class AuthenticatedUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: EmailStr
    full_name: str
    role: str
    team_id: uuid.UUID | None = None


class RegisterWorkspaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_name: str = Field(..., min_length=2, max_length=255)
    tenant_slug: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    admin_full_name: str = Field(..., min_length=2, max_length=255)
    admin_email: EmailStr = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(..., max_length=255)
    password: str = Field(..., min_length=1, max_length=128)
    tenant_slug: str | None = Field(None, min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str | None = Field(None, min_length=16, max_length=512)


class WorkspaceSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_visibility_mode: Literal["all", "team", "owner_only"] | None = None
    enforce_owner_write_guard: bool | None = None
    internal_domains: list[str] | None = None


class WorkspaceSettingsResponse(BaseModel):
    tenant_id: uuid.UUID
    record_visibility_mode: str = "all"
    enforce_owner_write_guard: bool = False
    internal_domains: list[str] = Field(default_factory=list)


class TenantInfoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    plan_tier: str


class UserInfoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: EmailStr
    full_name: str
    role: str
    tenant_name: str | None = None
    tenant_slug: str | None = None


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
    refresh_token: str
    user: UserInfoResponse


# ============================================================================
# ACCOUNT & COMPANY AFFILIATION SCHEMAS
# ============================================================================
class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255)
    industry: str | None = Field(None, max_length=100)
    website: str | None = Field(None, max_length=255)
    annual_revenue: Decimal | None = Field(None, ge=Decimal("0.00"))
    employee_count: int | None = Field(None, ge=1)
    parent_account_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=255)
    industry: str | None = Field(None, max_length=100)
    website: str | None = Field(None, max_length=255)
    annual_revenue: Decimal | None = Field(None, ge=Decimal("0.00"))
    employee_count: int | None = Field(None, ge=1)
    parent_account_id: uuid.UUID | None = None
    metadata: dict[str, Any] | None = None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    parent_account_id: uuid.UUID | None
    name: str
    industry: str | None
    website: str | None
    annual_revenue: Decimal | None
    employee_count: int | None
    owner_id: uuid.UUID
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    merged_into_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class AccountMergeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_account_id: uuid.UUID = Field(..., description="Duplicate account UUID to merge into target")


class CompanyAffiliationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_id: uuid.UUID
    role_title: str | None = Field(None, max_length=150)
    department: str | None = Field(None, max_length=100)
    is_primary: bool = False
    is_active: bool = True
    started_at: date | None = None
    ended_at: date | None = None


class CompanyAffiliationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    account_id: uuid.UUID
    contact_id: uuid.UUID
    role_title: str | None
    department: str | None
    is_primary: bool
    is_active: bool
    started_at: date | None
    ended_at: date | None
    created_at: datetime
    updated_at: datetime


# ============================================================================
# CONTACT & MERGE SCHEMAS
# ============================================================================
class ContactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr = Field(..., max_length=255)
    phone: str | None = Field(None, max_length=50)
    job_title: str | None = Field(None, max_length=150)
    account_id: uuid.UUID | None = None
    lifecycle_stage: str = Field(
        default="lead",
        pattern="^(lead|marketing_qualified|sales_qualified|customer|churned)$",
    )
    source_channel: str | None = Field(default=None, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("first_name", "last_name", "job_title", "source_channel")
    @classmethod
    def sanitize_strings(cls, v: str | None) -> str | None:
        return v.strip() if v else v


class ContactUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    phone: str | None = Field(None, max_length=50)
    job_title: str | None = Field(None, max_length=150)
    account_id: uuid.UUID | None = None
    lifecycle_stage: str | None = Field(
        None,
        pattern="^(lead|marketing_qualified|sales_qualified|customer|churned)$",
    )
    source_channel: str | None = Field(default=None, max_length=100)
    lead_score: Decimal | None = Field(None, ge=Decimal("0.00"), le=Decimal("100.00"))
    metadata: dict[str, Any] | None = None


class ContactMergeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_contact_id: uuid.UUID = Field(..., description="Duplicate contact UUID to merge into target")


class ContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    account_id: uuid.UUID | None
    owner_id: uuid.UUID
    first_name: str
    last_name: str
    email: EmailStr
    phone: str | None
    job_title: str | None
    lead_score: Decimal
    lifecycle_stage: str
    source_channel: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    merged_into_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


# ============================================================================
# DEAL, BUYING COMMITTEE & PIPELINE SCHEMAS
# ============================================================================
class DealCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=255)
    stage_id: uuid.UUID
    amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))
    currency: str = Field(default="USD", min_length=3, max_length=3, pattern="^[A-Z]{3}$")
    exchange_rate_to_usd: Decimal | None = Field(default=None, gt=Decimal("0.0"))
    account_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    expected_close_date: date | None = None
    source_channel: str | None = Field(default=None, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Deal title cannot be blank")
        return cleaned


class DealUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(None, min_length=1, max_length=255)
    amount: Decimal | None = Field(None, ge=Decimal("0.00"))
    currency: str | None = Field(None, min_length=3, max_length=3, pattern="^[A-Z]{3}$")
    exchange_rate_to_usd: Decimal | None = Field(default=None, gt=Decimal("0.0"))
    account_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    expected_close_date: date | None = None
    source_channel: str | None = Field(default=None, max_length=100)
    metadata: dict[str, Any] | None = None


class DealStageMoveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_stage_id: uuid.UUID = Field(..., description="Target pipeline stage UUID")
    loss_reason: str | None = Field(None, max_length=500, description="Mandatory if stage is closed_lost")
    loss_category: Literal[
        "price",
        "missing_feature",
        "competitor",
        "ghosting",
        "timing",
        "other",
    ] | None = None
    competitor_name: str | None = Field(None, max_length=120)
    missing_feature_tag: str | None = Field(None, max_length=120)
    notes: str | None = Field(None, max_length=2000, description="Optional explanation note for stage change")


class DealResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    pipeline_id: uuid.UUID
    stage_id: uuid.UUID
    account_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    owner_id: uuid.UUID
    title: str
    amount: Decimal
    currency: str
    exchange_rate_to_usd: Decimal = Decimal("1.000000")
    normalized_amount_usd: Decimal = Decimal("0.00")
    expected_close_date: date | None
    forecast_category: str
    win_probability: Decimal
    is_won: bool
    is_lost: bool
    loss_reason: str | None
    loss_category: str | None = None
    competitor_name: str | None = None
    missing_feature_tag: str | None = None
    source_channel: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    stage_entered_at: datetime | None = None
    last_interaction_at: datetime | None = None
    last_inbound_activity_at: datetime | None = None
    last_outbound_activity_at: datetime | None = None
    close_date_push_count: int = 0
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DealPlaybookResponse(BaseModel):
    deal_id: uuid.UUID | None = None
    deal_title: str
    stage_name: str
    normalized_amount_usd: Decimal = Decimal("0.00")
    suggested_email_subject: str
    suggested_email_body: str
    follow_up_email_subject: str = ""
    follow_up_email_body: str = ""
    recommended_actions: list[str]


class DealParticipantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_id: uuid.UUID
    buying_role: Literal[
        "champion",
        "economic_buyer",
        "technical_evaluator",
        "legal_blocker",
        "executive_sponsor",
        "stakeholder",
    ] = "stakeholder"
    is_primary: bool = False
    notes: str | None = Field(None, max_length=1000)


class DealParticipantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    deal_id: uuid.UUID
    contact_id: uuid.UUID
    buying_role: str
    is_primary: bool
    notes: str | None
    created_at: datetime


class DealStageHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    deal_id: uuid.UUID
    from_stage_id: uuid.UUID | None
    to_stage_id: uuid.UUID
    amount_at_transition: Decimal
    win_probability_at_transition: Decimal
    expected_close_date_at_transition: date | None
    changed_by: uuid.UUID | None
    entered_at: datetime
    exited_at: datetime | None
    duration_seconds: int | None


class PipelineStageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pipeline_id: uuid.UUID
    name: str
    position: int
    default_probability: Decimal
    is_closed_won: bool
    is_closed_lost: bool


# ============================================================================
# CUSTOM FIELD REGISTRY SCHEMAS
# ============================================================================
class CustomFieldDefinitionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: Literal["account", "contact", "deal"]
    field_key: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(..., min_length=1, max_length=150)
    field_type: Literal["text", "number", "boolean", "date", "select", "multi_select"]
    is_required: bool = False
    min_stage_position: int | None = Field(default=None, ge=1, le=20)
    allowed_values: list[str] = Field(default_factory=list)
    is_indexed: bool = False


class CustomFieldDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    entity_type: str
    field_key: str
    label: str
    field_type: str
    is_required: bool
    min_stage_position: int | None = None
    allowed_values: list[str]
    is_indexed: bool
    created_at: datetime
    updated_at: datetime


class TaskPruneZombiesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_overdue_days: int = Field(default=14, ge=1, le=365)


class TaskPruneZombiesResponse(BaseModel):
    pruned_count: int
    pruned_task_ids: list[uuid.UUID] = Field(default_factory=list)


# ============================================================================
# TASK, INTERACTION, ROLLUP TIMELINE & AUDIT SCHEMAS
# ============================================================================
class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    due_date: datetime
    contact_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    assigned_to: uuid.UUID | None = None


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["pending", "in_progress", "completed", "cancelled"] | None = None
    priority: Literal["low", "medium", "high", "urgent"] | None = None
    title: str | None = Field(None, min_length=1, max_length=255)


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    assigned_to: uuid.UUID
    created_by: uuid.UUID
    contact_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    title: str
    description: str | None
    priority: str
    status: str
    due_date: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InteractionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    type: Literal["email", "call", "meeting", "note", "task_completed", "stage_change"] = "note"
    direction: Literal["inbound", "outbound", "internal"] = "outbound"
    subject: str = Field(..., min_length=1, max_length=255)
    content_body: str = Field(..., min_length=1, max_length=15000)
    occurred_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InteractionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    contact_id: uuid.UUID | None
    account_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    type: str
    direction: str
    subject: str
    content_body: str
    occurred_at: datetime
    created_at: datetime


class CursorPaginatedTimelineResponse(BaseModel):
    items: list[InteractionResponse]
    next_cursor: str | None = None


class EntityAuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    action: str
    actor_user_id: uuid.UUID | None
    changes: dict[str, Any]
    created_at: datetime


# ============================================================================
# EMAIL & CALENDAR SYNC INGESTION SCHEMAS
# ============================================================================
class EmailSyncIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rfc_message_id: str = Field(..., min_length=3, max_length=255)
    thread_id: str | None = Field(None, max_length=255)
    in_reply_to: str | None = Field(None, max_length=255)
    mailbox_email: EmailStr = Field(..., max_length=255)
    sender_email: EmailStr = Field(..., max_length=255)
    recipient_emails: list[EmailStr] = Field(..., min_length=1)
    subject: str = Field(..., min_length=1, max_length=255)
    body_text: str = Field(..., min_length=1, max_length=30000)
    occurred_at: datetime | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class EmailSyncIngestResponse(BaseModel):
    status: Literal[
        "ingested",
        "deduplicated",
        "filtered_noise",
        "excluded_internal_or_sensitive",
        "unmatched_external",
    ]
    rfc_message_id: str
    interaction_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    synced_mailboxes: list[str] = Field(default_factory=list)
    reason: str | None = None


# ============================================================================
# AI AGENT, HITL PROPOSALS & SEMANTIC SEARCH SCHEMAS
# ============================================================================
class InteractionSummarizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction_id: uuid.UUID | None = Field(None, description="Existing interaction ID to summarize")
    contact_id: uuid.UUID = Field(..., description="Contact to whom interaction belongs")
    deal_id: uuid.UUID | None = Field(None, description="Optional associated deal")
    raw_notes_or_transcript: str = Field(
        ..., min_length=10, max_length=15000, description="Raw interaction text"
    )
    interaction_type: str = Field(default="meeting", pattern="^(call|meeting|email|note)$")


class ActionProposal(BaseModel):
    action_type: str = Field(..., description="e.g. schedule_followup, send_email, update_deal_stage")
    summary: str
    suggested_due_date: datetime | None = None
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    requires_human_approval: bool = True
    target_stage_name: str | None = None


class LLMAnalysisOutput(BaseModel):
    """Strict validation contract for structured JSON returned by any LLM provider."""

    executive_summary: str = Field(..., min_length=1)
    key_commitments_identified: list[str] = Field(default_factory=list)
    detected_sentiment: Literal["positive", "neutral", "negative", "hesitant"] = "neutral"
    suggested_next_step: str = Field(..., min_length=1)
    action_proposals: list[ActionProposal] = Field(default_factory=list)


class InteractionSummarizeResponse(BaseModel):
    executive_summary: str
    key_commitments_identified: list[str]
    detected_sentiment: str
    suggested_next_step: str
    action_proposals: list[ActionProposal]
    proposal_id: uuid.UUID | None = None
    proposal_ids: list[uuid.UUID] = Field(default_factory=list)
    ai_audit_id: uuid.UUID
    model_used: str
    key_source: str
    is_stub: bool = False


class AIProposalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    agent_name: str
    action_type: str
    target_entity_type: str
    target_entity_id: uuid.UUID
    proposed_payload: dict[str, Any]
    reasoning_summary: str
    status: str
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    created_at: datetime


class AIProposalRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rejection_reason: str = Field(..., min_length=3, max_length=1000)


class AIAuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None
    model_provider: str
    model_name: str
    tokens_prompt: int
    tokens_completion: int
    latency_ms: int
    is_safe_eval: bool
    created_at: datetime


class SemanticSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=2, max_length=1000)
    entity_type: Literal["contact", "deal", "account", "interaction_note"] | None = None
    limit: int = Field(default=5, ge=1, le=20)


class SemanticSearchResult(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    text_content: str
    similarity: float


class SemanticSearchResponse(BaseModel):
    results: list[SemanticSearchResult]
    source: str


# ============================================================================
# TENANT LLM CREDENTIAL (BYOK) & MCP SCHEMAS
# ============================================================================
class LLMCredentialCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(..., pattern="^(gemini|claude|openai)$", description="LLM provider name")
    raw_api_key: str = Field(
        ..., min_length=12, max_length=256, description="Plaintext API key to be encrypted"
    )


class LLMCredentialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    provider: str
    key_last_four: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class MCPToolResponse(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    requires_approval: bool


class MCPExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., min_length=2, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# REVENUE INTELLIGENCE, ATTRIBUTION & DATA TRANSFER SCHEMAS
# ============================================================================
class ForecastPeriodBreakdown(BaseModel):
    period: str  # YYYY-MM or 'unscheduled'
    closed_won_usd: Decimal
    commit_usd: Decimal
    best_case_usd: Decimal
    pipeline_usd: Decimal
    weighted_open_usd: Decimal
    deal_count: int


class AtRiskDealItem(BaseModel):
    deal_id: uuid.UUID
    title: str
    normalized_amount_usd: Decimal
    expected_close_date: date | None
    close_date_push_count: int
    days_in_stage: int
    risk_reasons: list[str]


class ForecastAnalyticsResponse(BaseModel):
    closed_won_usd: Decimal
    closed_lost_usd: Decimal
    open_pipeline_usd: Decimal
    commit_usd: Decimal
    best_case_usd: Decimal
    weighted_open_usd: Decimal
    total_projected_usd: Decimal
    open_deals_count: int
    won_deals_count: int
    lost_deals_count: int
    win_rate: Decimal
    avg_won_deal_usd: Decimal
    avg_sales_cycle_days: Decimal
    sales_velocity_usd_per_day: Decimal
    quota_usd: Decimal | None = None
    pipeline_coverage_ratio: Decimal | None = None
    usd_at_risk: Decimal
    at_risk_deals: list[AtRiskDealItem]
    by_period: list[ForecastPeriodBreakdown]


class FunnelStageMetric(BaseModel):
    stage_id: uuid.UUID
    stage_name: str
    position: int
    is_closed_won: bool
    is_closed_lost: bool
    deals_entered: int
    current_open_deals: int
    conversion_to_next_pct: Decimal
    avg_dwell_days: Decimal


class FunnelAnalyticsResponse(BaseModel):
    stages: list[FunnelStageMetric]
    bottleneck_stage_name: str | None = None


class ChannelAttributionMetric(BaseModel):
    source_channel: str
    leads_count: int
    opportunities_count: int
    won_deals_count: int
    win_rate: Decimal
    pipeline_generated_usd: Decimal
    closed_won_revenue_usd: Decimal
    avg_deal_size_usd: Decimal
    revenue_share_pct: Decimal


class AttributionAnalyticsResponse(BaseModel):
    total_leads: int
    total_closed_won_usd: Decimal
    channels: list[ChannelAttributionMetric]


class CSVImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csv_content: str = Field(..., min_length=1, max_length=2_000_000)
    dry_run: bool = True
    dedupe_strategy: Literal["skip", "update"] = "skip"
    column_map: dict[str, str] | None = None


class CSVImportRowError(BaseModel):
    row: int
    email: str | None = None
    reason: str


class CSVImportResponse(BaseModel):
    dry_run: bool
    import_batch_id: uuid.UUID | None = None
    total_rows: int
    would_create: int
    would_update: int
    would_skip: int
    would_create_deals: int = 0
    created_count: int
    updated_count: int
    skipped_count: int
    deals_created_count: int = 0
    quarantined_count: int
    accounts_auto_created: int
    detected_columns: dict[str, str]
    errors: list[CSVImportRowError]


class ImportBatchRollbackResponse(BaseModel):
    batch_id: uuid.UUID
    status: str
    reverted_accounts: int
    reverted_contacts: int
    reverted_deals: int


class PipelineSnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_date: date | None = None


class PipelineSnapshotResponse(BaseModel):
    snapshot_date: date
    captured_deals: int
    total_open_usd: Decimal


class WaterfallBridgeResponse(BaseModel):
    from_date: date
    to_date: date
    starting_open_usd: Decimal
    new_deals_usd: Decimal
    expansion_usd: Decimal
    contraction_usd: Decimal
    closed_won_usd: Decimal
    closed_lost_usd: Decimal
    ending_open_usd: Decimal
    slipped_deals_count: int


class WinLossCategoryBucket(BaseModel):
    category: str
    lost_deals_count: int
    lost_usd: Decimal


class WinLossNamedBucket(BaseModel):
    name: str
    lost_deals_count: int
    lost_usd: Decimal


class WinLossAnalyticsResponse(BaseModel):
    total_lost_deals: int
    total_lost_usd: Decimal
    by_category: list[WinLossCategoryBucket]
    by_competitor: list[WinLossNamedBucket]
    by_missing_feature: list[WinLossNamedBucket]
