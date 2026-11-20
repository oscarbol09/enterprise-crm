"""
Model Context Protocol (MCP) Execution Engine for Enterprise CRM.
Backed by real tenant-scoped SQLAlchemy queries and Human-in-the-Loop proposal creation.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.entities import AIProposal, Contact, Deal, Interaction, PipelineStage, Task


class MCPToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    requires_approval: bool = False


CRM_MCP_TOOLS: list[MCPToolDefinition] = [
    MCPToolDefinition(
        name="crm_search_contacts",
        description="Search contacts within the caller's tenant using name, email, or job title.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term or email"},
                "limit": {"type": "integer", "default": 10, "maximum": 50},
            },
            "required": ["query"],
        },
        requires_approval=False,
    ),
    MCPToolDefinition(
        name="crm_get_interaction_timeline",
        description="Fetch chronological interactions (emails, calls, meetings, notes) for a contact or deal.",
        parameters={
            "type": "object",
            "properties": {
                "contact_id": {"type": "string", "description": "UUID of the contact"},
                "limit": {"type": "integer", "default": 20, "maximum": 100},
            },
            "required": ["contact_id"],
        },
        requires_approval=False,
    ),
    MCPToolDefinition(
        name="crm_update_deal_stage",
        description="Propose moving a sales deal to a different pipeline stage. Requires human confirmation.",
        parameters={
            "type": "object",
            "properties": {
                "deal_id": {"type": "string", "description": "UUID of the target deal"},
                "target_stage_name": {"type": "string", "description": "Target stage name"},
                "justification": {"type": "string", "description": "Reasoning based on interaction analysis"},
            },
            "required": ["deal_id", "target_stage_name", "justification"],
        },
        requires_approval=True,
    ),
    MCPToolDefinition(
        name="crm_create_task",
        description="Schedule a follow-up task or reminder for a sales rep.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Concise task description"},
                "due_date_iso": {"type": "string", "description": "Due date in ISO 8601 format"},
                "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
                "contact_id": {"type": "string", "description": "Associated contact UUID"},
            },
            "required": ["title", "due_date_iso"],
        },
        requires_approval=False,
    ),
]


class MCPAgentExecutionEngine:
    """
    Executes registered CRM MCP tools inside the caller's tenant isolation boundary.
    """

    @classmethod
    async def dispatch_tool(
        cls,
        tool_name: str,
        arguments: dict[str, Any],
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> dict[str, Any]:
        tool = next((t for t in CRM_MCP_TOOLS if t.name == tool_name), None)
        if not tool:
            return {"status": "error", "message": f"Tool '{tool_name}' is not registered."}

        if tool_name == "crm_search_contacts":
            return await cls._exec_search_contacts(arguments, tenant_id, db)

        if tool_name == "crm_get_interaction_timeline":
            return await cls._exec_get_timeline(arguments, tenant_id, db)

        if tool_name == "crm_update_deal_stage":
            return await cls._exec_propose_deal_stage(arguments, tenant_id, db)

        if tool_name == "crm_create_task":
            return await cls._exec_create_task(arguments, tenant_id, user_id, db)

        return {"status": "error", "message": f"No handler bound for tool '{tool_name}'."}

    @staticmethod
    async def _exec_search_contacts(
        arguments: dict[str, Any], tenant_id: uuid.UUID, db: AsyncSession
    ) -> dict[str, Any]:
        raw_query = str(arguments.get("query", "")).strip()
        if not raw_query:
            return {"status": "error", "message": "Argument 'query' is required."}

        limit = min(max(int(arguments.get("limit", 10)), 1), 50)
        pattern = f"%{raw_query}%"
        stmt = (
            select(Contact)
            .where(
                Contact.tenant_id == tenant_id,
                or_(
                    Contact.first_name.ilike(pattern),
                    Contact.last_name.ilike(pattern),
                    Contact.email.ilike(pattern),
                    Contact.job_title.ilike(pattern),
                ),
            )
            .order_by(Contact.lead_score.desc())
            .limit(limit)
        )
        contacts = list((await db.scalars(stmt)).all())
        return {
            "status": "success",
            "results": [
                {
                    "contact_id": str(c.id),
                    "name": f"{c.first_name} {c.last_name}",
                    "email": c.email,
                    "title": c.job_title,
                    "lifecycle_stage": c.lifecycle_stage,
                    "lead_score": float(c.lead_score),
                }
                for c in contacts
            ],
        }

    @staticmethod
    async def _exec_get_timeline(
        arguments: dict[str, Any], tenant_id: uuid.UUID, db: AsyncSession
    ) -> dict[str, Any]:
        try:
            contact_uuid = uuid.UUID(str(arguments.get("contact_id", "")))
        except ValueError:
            return {"status": "error", "message": "Argument 'contact_id' must be a valid UUID."}

        limit = min(max(int(arguments.get("limit", 20)), 1), 100)
        stmt = (
            select(Interaction)
            .where(Interaction.tenant_id == tenant_id, Interaction.contact_id == contact_uuid)
            .order_by(Interaction.occurred_at.desc())
            .limit(limit)
        )
        items = list((await db.scalars(stmt)).all())
        return {
            "status": "success",
            "results": [
                {
                    "id": str(item.id),
                    "type": item.type,
                    "direction": item.direction,
                    "subject": item.subject,
                    "content_body": item.content_body,
                    "occurred_at": item.occurred_at.isoformat(),
                }
                for item in items
            ],
        }

    @staticmethod
    async def _exec_propose_deal_stage(
        arguments: dict[str, Any], tenant_id: uuid.UUID, db: AsyncSession
    ) -> dict[str, Any]:
        try:
            deal_uuid = uuid.UUID(str(arguments.get("deal_id", "")))
        except ValueError:
            return {"status": "error", "message": "Argument 'deal_id' must be a valid UUID."}

        target_stage_name = str(arguments.get("target_stage_name", "")).strip()
        justification = str(arguments.get("justification", "")).strip()
        if not target_stage_name or not justification:
            return {
                "status": "error",
                "message": "Arguments 'target_stage_name' and 'justification' are required.",
            }

        deal = await db.scalar(select(Deal).where(Deal.id == deal_uuid, Deal.tenant_id == tenant_id))
        if not deal:
            return {"status": "error", "message": f"Deal {deal_uuid} not found in tenant."}

        target_stage = await db.scalar(
            select(PipelineStage).where(
                PipelineStage.tenant_id == tenant_id,
                PipelineStage.pipeline_id == deal.pipeline_id,
                PipelineStage.name.ilike(target_stage_name),
            )
        )
        if not target_stage:
            return {
                "status": "error",
                "message": f"Stage '{target_stage_name}' not found in deal pipeline.",
            }

        proposal = AIProposal(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            agent_name="CRM_MCP_Agent",
            action_type="update_deal_stage",
            target_entity_type="deal",
            target_entity_id=deal.id,
            proposed_payload={
                "target_stage_id": str(target_stage.id),
                "target_stage_name": target_stage.name,
                "summary": f"Move '{deal.title}' to '{target_stage.name}'",
            },
            reasoning_summary=justification,
            status="pending_review",
        )
        db.add(proposal)
        await db.flush()

        return {
            "status": "pending_human_approval",
            "message": (
                f"Action 'crm_update_deal_stage' queued as proposal {proposal.id} "
                f"for manager approval before mutating deal {deal.id}."
            ),
            "proposal_id": str(proposal.id),
            "proposed_arguments": arguments,
        }

    @staticmethod
    async def _exec_create_task(
        arguments: dict[str, Any], tenant_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
    ) -> dict[str, Any]:
        title = str(arguments.get("title", "")).strip()
        if not title:
            return {"status": "error", "message": "Argument 'title' is required."}

        due_iso = arguments.get("due_date_iso")
        try:
            due_date = (
                datetime.fromisoformat(str(due_iso).replace("Z", "+00:00"))
                if due_iso
                else datetime.now(UTC) + timedelta(days=1)
            )
        except ValueError:
            return {"status": "error", "message": "Argument 'due_date_iso' must be ISO 8601."}

        priority = str(arguments.get("priority", "medium")).lower()
        if priority not in {"low", "medium", "high", "urgent"}:
            priority = "medium"

        contact_uuid: uuid.UUID | None = None
        if arguments.get("contact_id"):
            try:
                contact_uuid = uuid.UUID(str(arguments["contact_id"]))
            except ValueError:
                return {"status": "error", "message": "Argument 'contact_id' must be a valid UUID."}
            exists = await db.scalar(
                select(Contact.id).where(Contact.id == contact_uuid, Contact.tenant_id == tenant_id)
            )
            if not exists:
                return {"status": "error", "message": f"Contact {contact_uuid} not found in tenant."}

        task = Task(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            assigned_to=user_id,
            created_by=user_id,
            contact_id=contact_uuid,
            title=title[:255],
            priority=priority,
            status="pending",
            due_date=due_date,
        )
        db.add(task)
        await db.flush()
        return {
            "status": "success",
            "task_id": str(task.id),
            "title": task.title,
            "due_date": task.due_date.isoformat(),
        }
