"""
AI Copilot & Human-in-the-Loop (HITL) Proposals Router.
Follows the Zero-I/O DB Transaction Invariant: database connections are released
prior to executing slow external LLM HTTP calls.
"""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import tenant_session_scope
from src.core.dependencies import get_current_user, get_tenant_db, require_roles
from src.core.rate_limit import rate_limit
from src.core.security import sanitize_user_input_for_llm
from src.models.entities import (
    AIAuditLog,
    AIProposal,
    Contact,
    Deal,
    Interaction,
    OutboxEvent,
    PipelineStage,
    Task,
    Tenant,
    User,
)
from src.schemas.crm import (
    AIAuditLogResponse,
    AIProposalRejectRequest,
    AIProposalResponse,
    AuthenticatedUser,
    InteractionSummarizeRequest,
    InteractionSummarizeResponse,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from src.services.ai_service import (
    AIAgentOrchestrator,
    AIConfigurationError,
    AIProviderError,
    MultiModelRouter,
    parse_llm_analysis_json,
)
from src.services.embedding_service import semantic_search, upsert_entity_embedding
from src.services.pipeline_service import apply_deal_stage_transition

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/ai", tags=["AI Agent Copilot & HITL"])


@router.post(
    "/copilot/summarize-interaction",
    response_model=InteractionSummarizeResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit("ai_copilot", limit=30, window_seconds=60))],
    summary="Summarize CRM interaction notes with prompt hardening and HITL proposals",
)
async def summarize_interaction(
    payload: InteractionSummarizeRequest,
    current_user: AuthenticatedUser = Depends(require_roles(["admin", "sales_manager", "sales_rep"])),
):
    # Phase 1: Short-lived read transaction (validate tenant/user/entities & resolve BYOK keys)
    async with tenant_session_scope(current_user.tenant_id) as read_db:
        active_row = (
            await read_db.execute(
                select(User.is_active, Tenant.is_active)
                .join(Tenant, Tenant.id == User.tenant_id)
                .where(User.id == current_user.id, User.tenant_id == current_user.tenant_id)
            )
        ).first()
        if active_row is None or not active_row[0] or not active_row[1]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account or tenant workspace is inactive",
            )

        contact_exists = await read_db.scalar(
            select(Contact.id).where(
                Contact.id == payload.contact_id,
                Contact.tenant_id == current_user.tenant_id,
            )
        )
        if not contact_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contact with ID {payload.contact_id} not found.",
            )

        if payload.deal_id:
            deal_exists = await read_db.scalar(
                select(Deal.id).where(
                    Deal.id == payload.deal_id,
                    Deal.tenant_id == current_user.tenant_id,
                )
            )
            if not deal_exists:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Deal with ID {payload.deal_id} not found.",
                )

        configured_keys = await MultiModelRouter.resolve_all_configured_keys(
            settings.DEFAULT_LLM_PROVIDER, current_user.tenant_id, read_db
        )

    # Phase 2: External I/O strictly outside any database transaction
    clean_transcript, is_suspicious = sanitize_user_input_for_llm(payload.raw_notes_or_transcript)
    system_prompt, user_content = AIAgentOrchestrator.build_prompts(payload, clean_transcript)

    try:
        response_data = await MultiModelRouter.invoke_with_resolved_keys(
            system_prompt=system_prompt,
            user_message=user_content,
            configured_keys=configured_keys,
            preferred_provider=settings.DEFAULT_LLM_PROVIDER,
        )
        analysis = parse_llm_analysis_json(response_data["content"])
    except AIConfigurationError as exc:
        logger.warning("AI Copilot unconfigured", tenant_id=str(current_user.tenant_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No active LLM provider key is configured for this tenant.",
        ) from exc
    except AIProviderError as exc:
        logger.error("AI Copilot upstream failure", tenant_id=str(current_user.tenant_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream AI provider failed to process the interaction summary.",
        ) from exc

    # Phase 3: Short-lived write transaction (persist audit log, interaction note, embedding, proposals)
    async with tenant_session_scope(current_user.tenant_id) as write_db:
        interaction = Interaction(
            id=uuid.uuid4(),
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            contact_id=payload.contact_id,
            deal_id=payload.deal_id,
            type=payload.interaction_type,
            direction="outbound",
            subject=f"Resumen Copilot ({payload.interaction_type})",
            content_body=analysis.executive_summary,
        )
        write_db.add(interaction)
        await write_db.flush()

        await upsert_entity_embedding(
            session=write_db,
            tenant_id=current_user.tenant_id,
            entity_type="interaction_note",
            entity_id=interaction.id,
            text_content=f"{analysis.executive_summary} | Next: {analysis.suggested_next_step}",
        )

        return await AIAgentOrchestrator.persist_analysis_results(
            db=write_db,
            req=payload,
            current_user=current_user,
            clean_transcript=clean_transcript,
            is_suspicious=is_suspicious,
            response_data=response_data,
            analysis=analysis,
        )


@router.post(
    "/copilot/semantic-search",
    response_model=SemanticSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Perform tenant-isolated vector semantic search across CRM entities",
)
async def run_semantic_search(
    payload: SemanticSearchRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    results, source = await semantic_search(
        session=db,
        tenant_id=current_user.tenant_id,
        query=payload.query,
        entity_type=payload.entity_type,
        limit=payload.limit,
    )
    return SemanticSearchResponse(results=results, source=source)


@router.get(
    "/proposals",
    response_model=list[AIProposalResponse],
    status_code=status.HTTP_200_OK,
    summary="List Human-in-the-Loop AI proposals for the current tenant",
)
async def list_ai_proposals(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    stmt = select(AIProposal).where(AIProposal.tenant_id == current_user.tenant_id)
    if status_filter:
        stmt = stmt.where(AIProposal.status == status_filter)
    stmt = stmt.order_by(AIProposal.created_at.desc()).limit(limit)
    return list((await db.scalars(stmt)).all())


@router.post(
    "/proposals/{proposal_id}/approve",
    response_model=AIProposalResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve a pending AI proposal and atomically execute its CRM action",
)
async def approve_ai_proposal(
    proposal_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(require_roles(["admin", "sales_manager"])),
    db: AsyncSession = Depends(get_tenant_db),
):
    proposal = await db.scalar(
        select(AIProposal).where(
            AIProposal.id == proposal_id,
            AIProposal.tenant_id == current_user.tenant_id,
        )
    )
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI proposal not found.")
    if proposal.status != "pending_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Proposal already processed with status '{proposal.status}'.",
        )

    payload_data = proposal.proposed_payload or {}

    if proposal.action_type == "update_deal_stage" and proposal.target_entity_type == "deal":
        deal = await db.scalar(
            select(Deal).where(Deal.id == proposal.target_entity_id, Deal.tenant_id == current_user.tenant_id)
        )
        if not deal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target deal not found.")

        target_stage = None
        if payload_data.get("target_stage_id"):
            target_stage = await db.scalar(
                select(PipelineStage).where(
                    PipelineStage.id == uuid.UUID(str(payload_data["target_stage_id"])),
                    PipelineStage.pipeline_id == deal.pipeline_id,
                    PipelineStage.tenant_id == current_user.tenant_id,
                )
            )
        elif payload_data.get("target_stage_name"):
            target_stage = await db.scalar(
                select(PipelineStage).where(
                    PipelineStage.pipeline_id == deal.pipeline_id,
                    PipelineStage.tenant_id == current_user.tenant_id,
                    PipelineStage.name.ilike(str(payload_data["target_stage_name"])),
                )
            )
        if target_stage is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot resolve target pipeline stage from proposal payload.",
            )

        await apply_deal_stage_transition(
            session=db,
            deal=deal,
            target_stage=target_stage,
            actor_user_id=current_user.id,
            actor_name=current_user.full_name,
            notes=f"Approved AI proposal {proposal.id}: {payload_data.get('summary', '')}",
        )

    elif proposal.action_type == "schedule_followup":
        contact_id_raw = payload_data.get("contact_id")
        deal_id_raw = payload_data.get("deal_id")
        task = Task(
            id=uuid.uuid4(),
            tenant_id=current_user.tenant_id,
            assigned_to=current_user.id,
            created_by=current_user.id,
            contact_id=uuid.UUID(contact_id_raw) if contact_id_raw else None,
            deal_id=uuid.UUID(deal_id_raw) if deal_id_raw else None,
            title=str(payload_data.get("summary") or "AI Follow-up")[:255],
            description=proposal.reasoning_summary,
            priority="high",
            status="pending",
            due_date=datetime.now(UTC) + timedelta(days=2),
        )
        db.add(task)

    else:
        db.add(
            OutboxEvent(
                id=uuid.uuid4(),
                tenant_id=current_user.tenant_id,
                aggregate_type=proposal.target_entity_type,
                aggregate_id=proposal.target_entity_id,
                event_type="AIProposalApproved",
                payload={
                    "proposal_id": str(proposal.id),
                    "action_type": proposal.action_type,
                    "approved_by": str(current_user.id),
                    "proposed_payload": payload_data,
                },
                status="pending",
            )
        )

    proposal.status = "approved"
    proposal.reviewed_by = current_user.id
    proposal.reviewed_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(proposal)
    return proposal


@router.post(
    "/proposals/{proposal_id}/reject",
    response_model=AIProposalResponse,
    status_code=status.HTTP_200_OK,
    summary="Reject a pending AI proposal with explicit audit reasoning",
)
async def reject_ai_proposal(
    proposal_id: uuid.UUID,
    payload: AIProposalRejectRequest,
    current_user: AuthenticatedUser = Depends(require_roles(["admin", "sales_manager"])),
    db: AsyncSession = Depends(get_tenant_db),
):
    proposal = await db.scalar(
        select(AIProposal).where(
            AIProposal.id == proposal_id,
            AIProposal.tenant_id == current_user.tenant_id,
        )
    )
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI proposal not found.")
    if proposal.status != "pending_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Proposal already processed with status '{proposal.status}'.",
        )

    proposal.status = "rejected"
    proposal.reviewed_by = current_user.id
    proposal.reviewed_at = datetime.now(UTC)
    proposal.rejection_reason = payload.rejection_reason.strip()

    await db.flush()
    await db.refresh(proposal)
    return proposal


@router.get(
    "/audit-logs",
    response_model=list[AIAuditLogResponse],
    status_code=status.HTTP_200_OK,
    summary="List AI invocation audit records for compliance monitoring",
)
async def list_ai_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(require_roles(["admin", "sales_manager"])),
    db: AsyncSession = Depends(get_tenant_db),
):
    rows = await db.scalars(
        select(AIAuditLog)
        .where(AIAuditLog.tenant_id == current_user.tenant_id)
        .order_by(AIAuditLog.created_at.desc())
        .limit(limit)
    )
    return list(rows.all())
