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
# ACCOUNT SCHEMAS
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
    metadata: dict[str, Any] = Field(..., alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ============================================================================
# CONTACT SCHEMAS
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
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("first_name", "last_name", "job_title")
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
    lead_score: Decimal | None = Field(None, ge=Decimal("0.00"), le=Decimal("100.00"))


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
    metadata: dict[str, Any] = Field(..., alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ============================================================================
# DEAL & PIPELINE SCHEMAS
# ============================================================================
class DealCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=255)
    stage_id: uuid.UUID
    amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))
    currency: str = Field(default="USD", min_length=3, max_length=3, pattern="^[A-Z]{3}$")
    account_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    expected_close_date: date | None = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Deal title cannot be blank")
        return cleaned


class DealStageMoveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_stage_id: uuid.UUID = Field(..., description="Target pipeline stage UUID")
    loss_reason: str | None = Field(None, max_length=500, description="Mandatory if stage is closed_lost")
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
    expected_close_date: date | None
    forecast_category: str
    win_probability: Decimal
    is_won: bool
    is_lost: bool
    loss_reason: str | None
    created_at: datetime
    updated_at: datetime


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
# TASK & INTERACTION SCHEMAS
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
