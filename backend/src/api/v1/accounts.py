"""
Accounts & Tasks API Routers: Company Directory, Multi-Entity Affiliations,
Hierarchical Activity Roll-Up Timeline, and Follow-Up Task Scheduling.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_tenant_db, require_roles
from src.models.entities import (
    Account,
    CompanyAffiliation,
    Contact,
    Deal,
    Interaction,
    Task,
)
from src.schemas.crm import (
    AccountCreate,
    AccountMergeRequest,
    AccountResponse,
    AccountUpdate,
    AuthenticatedUser,
    CompanyAffiliationCreate,
    CompanyAffiliationResponse,
    CursorPaginatedTimelineResponse,
    InteractionResponse,
    TaskCreate,
    TaskPruneZombiesRequest,
    TaskPruneZombiesResponse,
    TaskResponse,
    TaskUpdate,
)
from src.services.audit_service import (
    apply_sql_keyset_cursor,
    paginate_interactions_with_cursor,
    record_entity_audit,
    slice_keyset_page,
)
from src.services.custom_fields_service import (
    matches_custom_field_filter,
    validate_entity_custom_fields,
)
from src.services.rbac_service import get_visible_owner_ids, verify_record_access

accounts_router = APIRouter(prefix="/accounts", tags=["Accounts"])
tasks_router = APIRouter(prefix="/tasks", tags=["Tasks"])

_WRITE_ROLES = ["admin", "sales_manager", "sales_rep"]


@accounts_router.get("", response_model=list[AccountResponse], status_code=status.HTTP_200_OK)
async def list_accounts(
    response: Response,
    q: str | None = Query(default=None, max_length=120),
    cf_key: str | None = Query(default=None, max_length=100),
    cf_value: str | None = Query(default=None, max_length=255),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    stmt = select(Account).where(
        Account.tenant_id == current_user.tenant_id,
        Account.deleted_at.is_(None),
    )

    visible_owners = await get_visible_owner_ids(db, current_user)
    if visible_owners is not None:
        stmt = stmt.where(Account.owner_id.in_(visible_owners))

    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Account.name.ilike(pattern),
                Account.industry.ilike(pattern),
                Account.website.ilike(pattern),
            )
        )

    stmt = apply_sql_keyset_cursor(stmt, Account, cursor)
    stmt = stmt.order_by(Account.created_at.desc(), Account.id.desc())
    if not cf_key:
        stmt = stmt.limit(limit + 1)

    rows = list((await db.scalars(stmt)).all())
    if cf_key:
        rows = [r for r in rows if matches_custom_field_filter(r.metadata_, cf_key, cf_value)]

    page, next_cursor = slice_keyset_page(rows, limit)
    if next_cursor:
        response.headers["X-Next-Cursor"] = next_cursor
    return page


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
                Account.deleted_at.is_(None),
            )
        )
        if not parent:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent account not found.")

    validated_metadata = await validate_entity_custom_fields(
        db,
        current_user.tenant_id,
        "account",
        payload.metadata,
    )

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
        metadata_=validated_metadata,
    )
    db.add(account)
    await record_entity_audit(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="account",
        entity_id=account.id,
        action="CREATE",
        actor_user_id=current_user.id,
        changes={"name": account.name, "website": account.website},
    )
    await db.flush()
    await db.refresh(account)
    return account


@accounts_router.get(
    "/{account_id}",
    response_model=AccountResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch a single account by ID (transparently follows merged_into_id pointers)",
)
async def get_account(
    account_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    account = await db.scalar(
        select(Account).where(
            Account.id == account_id,
            Account.tenant_id == current_user.tenant_id,
        )
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    hops = 0
    while account and account.merged_into_id is not None and hops < 5:
        account = await db.scalar(
            select(Account).where(
                Account.id == account.merged_into_id,
                Account.tenant_id == current_user.tenant_id,
            )
        )
        hops += 1

    if not account or account.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    await verify_record_access(db, current_user, account.owner_id, require_write=False)
    return account


@accounts_router.post(
    "/{target_account_id}/merge",
    response_model=AccountResponse,
    status_code=status.HTTP_200_OK,
    summary="Non-destructively merge a duplicate account into target account, re-linking contacts, deals & interactions",
)
async def merge_accounts(
    target_account_id: uuid.UUID,
    payload: AccountMergeRequest,
    current_user: AuthenticatedUser = Depends(require_roles(["admin", "sales_manager"])),
    db: AsyncSession = Depends(get_tenant_db),
):
    if target_account_id == payload.source_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot merge an account into itself.",
        )

    target = await db.scalar(
        select(Account).where(
            Account.id == target_account_id,
            Account.tenant_id == current_user.tenant_id,
            Account.deleted_at.is_(None),
        )
    )
    source = await db.scalar(
        select(Account).where(
            Account.id == payload.source_account_id,
            Account.tenant_id == current_user.tenant_id,
            Account.deleted_at.is_(None),
        )
    )
    if not target or not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target or source account not found in this tenant.",
        )

    # Re-link Contacts, Deals, and Interactions
    await db.execute(
        update(Contact)
        .where(Contact.tenant_id == current_user.tenant_id, Contact.account_id == source.id)
        .values(account_id=target.id)
    )
    await db.execute(
        update(Deal)
        .where(Deal.tenant_id == current_user.tenant_id, Deal.account_id == source.id)
        .values(account_id=target.id)
    )
    await db.execute(
        update(Interaction)
        .where(Interaction.tenant_id == current_user.tenant_id, Interaction.account_id == source.id)
        .values(account_id=target.id)
    )

    # Backfill empty fields on target from source
    if not target.industry and source.industry:
        target.industry = source.industry
    if not target.website and source.website:
        target.website = source.website
    if target.annual_revenue is None and source.annual_revenue is not None:
        target.annual_revenue = source.annual_revenue
    if target.employee_count is None and source.employee_count is not None:
        target.employee_count = source.employee_count

    merged_meta = dict(source.metadata_ or {})
    merged_meta.update(target.metadata_ or {})
    target.metadata_ = merged_meta

    now = datetime.now(UTC)
    source.merged_into_id = target.id
    source.deleted_at = now

    await record_entity_audit(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="account",
        entity_id=target.id,
        action="MERGE",
        actor_user_id=current_user.id,
        changes={
            "source_account_id": str(source.id),
            "source_name": source.name,
            "target_account_id": str(target.id),
        },
    )
    await db.flush()
    await db.refresh(target)
    return target


@accounts_router.patch("/{account_id}", response_model=AccountResponse, status_code=status.HTTP_200_OK)
async def update_account(
    account_id: uuid.UUID,
    payload: AccountUpdate,
    current_user: AuthenticatedUser = Depends(require_roles(_WRITE_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    account = await db.scalar(
        select(Account).where(
            Account.id == account_id,
            Account.tenant_id == current_user.tenant_id,
            Account.deleted_at.is_(None),
        )
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    await verify_record_access(db, current_user, account.owner_id, require_write=True)

    updates = payload.model_dump(exclude_unset=True)
    if "metadata" in updates:
        raw_meta = updates.pop("metadata")
        account.metadata_ = await validate_entity_custom_fields(
            db,
            current_user.tenant_id,
            "account",
            raw_meta,
            is_partial=True,
            existing_metadata=account.metadata_,
        )

    for field, value in updates.items():
        setattr(account, field, value)

    await db.flush()
    await db.refresh(account)
    return account


@accounts_router.post(
    "/{account_id}/affiliations",
    response_model=CompanyAffiliationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Affiliate a contact with a company with an explicit role and department",
)
async def create_company_affiliation(
    account_id: uuid.UUID,
    payload: CompanyAffiliationCreate,
    current_user: AuthenticatedUser = Depends(require_roles(_WRITE_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    account = await db.scalar(
        select(Account).where(
            Account.id == account_id,
            Account.tenant_id == current_user.tenant_id,
            Account.deleted_at.is_(None),
        )
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    contact = await db.scalar(
        select(Contact).where(
            Contact.id == payload.contact_id,
            Contact.tenant_id == current_user.tenant_id,
            Contact.deleted_at.is_(None),
        )
    )
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found.")

    affiliation = CompanyAffiliation(
        id=uuid.uuid4(),
        tenant_id=current_user.tenant_id,
        account_id=account.id,
        contact_id=contact.id,
        role_title=payload.role_title,
        department=payload.department,
        is_primary=payload.is_primary,
        is_active=payload.is_active,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
    )
    db.add(affiliation)

    if payload.is_primary or contact.account_id is None:
        contact.account_id = account.id

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This contact is already affiliated with this company.",
        ) from exc

    await db.refresh(affiliation)
    return affiliation


@accounts_router.get(
    "/{account_id}/affiliations",
    response_model=list[CompanyAffiliationResponse],
    status_code=status.HTTP_200_OK,
    summary="List all contacts affiliated with an account",
)
async def list_account_affiliations(
    account_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    rows = await db.scalars(
        select(CompanyAffiliation)
        .where(
            CompanyAffiliation.tenant_id == current_user.tenant_id,
            CompanyAffiliation.account_id == account_id,
        )
        .order_by(CompanyAffiliation.is_primary.desc(), CompanyAffiliation.created_at.asc())
    )
    return list(rows.all())


@accounts_router.get(
    "/{account_id}/timeline",
    response_model=CursorPaginatedTimelineResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch hierarchical roll-up timeline across the company, its affiliated contacts, and deals",
)
async def get_account_rollup_timeline(
    account_id: uuid.UUID,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    account = await db.scalar(
        select(Account).where(
            Account.id == account_id,
            Account.tenant_id == current_user.tenant_id,
            Account.deleted_at.is_(None),
        )
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    await verify_record_access(db, current_user, account.owner_id, require_write=False)

    # Collect direct account interactions + any interactions linked to contacts/deals of this account
    contact_ids = list(
        (
            await db.scalars(
                select(Contact.id).where(
                    Contact.tenant_id == current_user.tenant_id,
                    Contact.account_id == account_id,
                )
            )
        ).all()
    )
    deal_ids = list(
        (
            await db.scalars(
                select(Deal.id).where(
                    Deal.tenant_id == current_user.tenant_id,
                    Deal.account_id == account_id,
                )
            )
        ).all()
    )

    predicates = [Interaction.account_id == account_id]
    if contact_ids:
        predicates.append(Interaction.contact_id.in_(contact_ids))
    if deal_ids:
        predicates.append(Interaction.deal_id.in_(deal_ids))

    all_interactions = list(
        (
            await db.scalars(
                select(Interaction)
                .where(
                    Interaction.tenant_id == current_user.tenant_id,
                    or_(*predicates),
                )
                .order_by(Interaction.occurred_at.desc(), Interaction.id.desc())
            )
        ).all()
    )

    page_items, next_cursor = paginate_interactions_with_cursor(all_interactions, cursor, limit)
    return CursorPaginatedTimelineResponse(
        items=[InteractionResponse.model_validate(item) for item in page_items],
        next_cursor=next_cursor,
    )


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
                Contact.id == payload.contact_id,
                Contact.tenant_id == current_user.tenant_id,
                Contact.deleted_at.is_(None),
            )
        )
        if not c_exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found.")

    if payload.deal_id:
        d_exists = await db.scalar(
            select(Deal.id).where(
                Deal.id == payload.deal_id,
                Deal.tenant_id == current_user.tenant_id,
                Deal.deleted_at.is_(None),
            )
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


@tasks_router.post(
    "/prune-zombies",
    response_model=TaskPruneZombiesResponse,
    status_code=status.HTTP_200_OK,
    summary="Auto-cancel stale overdue tasks and tasks linked to already closed deals",
)
async def prune_zombie_tasks(
    payload: TaskPruneZombiesRequest,
    current_user: AuthenticatedUser = Depends(require_roles(_WRITE_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=payload.max_overdue_days)

    open_tasks = list(
        (
            await db.scalars(
                select(Task).where(
                    Task.tenant_id == current_user.tenant_id,
                    Task.status.in_(["pending", "in_progress"]),
                )
            )
        ).all()
    )

    closed_deal_ids = set(
        (
            await db.scalars(
                select(Deal.id).where(
                    Deal.tenant_id == current_user.tenant_id,
                    or_(Deal.is_won.is_(True), Deal.is_lost.is_(True), Deal.deleted_at.is_not(None)),
                )
            )
        ).all()
    )

    pruned_ids: list[uuid.UUID] = []
    for t in open_tasks:
        due_aware = t.due_date.replace(tzinfo=UTC) if t.due_date.tzinfo is None else t.due_date
        is_stale_overdue = due_aware < cutoff
        is_closed_deal_orphan = t.deal_id is not None and t.deal_id in closed_deal_ids

        if is_stale_overdue or is_closed_deal_orphan:
            t.status = "cancelled"
            t.updated_at = now
            pruned_ids.append(t.id)

    await db.flush()
    return TaskPruneZombiesResponse(
        pruned_count=len(pruned_ids),
        pruned_task_ids=pruned_ids,
    )


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

