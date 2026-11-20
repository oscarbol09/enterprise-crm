"""
Accounts & Tasks API Routers: Company Directory and Follow-Up Task Scheduling.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_tenant_db, require_roles
from src.models.entities import Account, Contact, Deal, Task
from src.schemas.crm import (
    AccountCreate,
    AccountResponse,
    AuthenticatedUser,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
)

accounts_router = APIRouter(prefix="/accounts", tags=["Accounts"])
tasks_router = APIRouter(prefix="/tasks", tags=["Tasks"])

_WRITE_ROLES = ["admin", "sales_manager", "sales_rep"]


@accounts_router.get("", response_model=list[AccountResponse], status_code=status.HTTP_200_OK)
async def list_accounts(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    rows = await db.scalars(
        select(Account)
        .where(Account.tenant_id == current_user.tenant_id)
        .order_by(Account.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(rows.all())


@accounts_router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    current_user: AuthenticatedUser = Depends(require_roles(_WRITE_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    if payload.parent_account_id:
        parent = await db.scalar(
            select(Account.id).where(
                Account.id == payload.parent_account_id,
                Account.tenant_id == current_user.tenant_id,
            )
        )
        if not parent:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent account not found.")

    account = Account(
        id=uuid.uuid4(),
        tenant_id=current_user.tenant_id,
        parent_account_id=payload.parent_account_id,
        name=payload.name.strip(),
        industry=payload.industry,
        website=payload.website,
        annual_revenue=payload.annual_revenue,
        employee_count=payload.employee_count,
        owner_id=current_user.id,
        metadata_=payload.metadata,
    )
    db.add(account)
    await db.flush()
    await db.refresh(account)
    return account


@tasks_router.get("", response_model=list[TaskResponse], status_code=status.HTTP_200_OK)
async def list_tasks(
    limit: int = Query(default=100, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    rows = await db.scalars(
        select(Task)
        .where(Task.tenant_id == current_user.tenant_id)
        .order_by(Task.due_date.asc())
        .limit(limit)
    )
    return list(rows.all())


@tasks_router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    current_user: AuthenticatedUser = Depends(require_roles(_WRITE_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    if payload.contact_id:
        c_exists = await db.scalar(
            select(Contact.id).where(
                Contact.id == payload.contact_id, Contact.tenant_id == current_user.tenant_id
            )
        )
        if not c_exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found.")

    if payload.deal_id:
        d_exists = await db.scalar(
            select(Deal.id).where(Deal.id == payload.deal_id, Deal.tenant_id == current_user.tenant_id)
        )
        if not d_exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found.")

    task = Task(
        id=uuid.uuid4(),
        tenant_id=current_user.tenant_id,
        assigned_to=payload.assigned_to or current_user.id,
        created_by=current_user.id,
        contact_id=payload.contact_id,
        deal_id=payload.deal_id,
        title=payload.title.strip(),
        description=payload.description,
        priority=payload.priority,
        status="pending",
        due_date=payload.due_date,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


@tasks_router.patch("/{task_id}", response_model=TaskResponse, status_code=status.HTTP_200_OK)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    current_user: AuthenticatedUser = Depends(require_roles(_WRITE_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    task = await db.scalar(select(Task).where(Task.id == task_id, Task.tenant_id == current_user.tenant_id))
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(task, field, value)
    if payload.status == "completed" and task.completed_at is None:
        task.completed_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(task)
    return task
