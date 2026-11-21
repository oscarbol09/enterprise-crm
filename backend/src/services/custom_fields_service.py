"""
Dynamic Custom Fields Service: Tenant-Scoped Metadata Registry, Stage-Gated Lazy Validation,
Anti-Garbage Placeholder Guard & Filtering.
"""

import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.entities import CustomFieldDefinition

_GARBAGE_PLACEHOLDERS = {
    "tbd",
    "n/a",
    "na",
    "none",
    "null",
    "---",
    "...",
    "000",
    "pendiente",
    "por definir",
    "no se",
    "nose",
}


async def validate_entity_custom_fields(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    entity_type: str,
    incoming_metadata: dict[str, Any] | None,
    *,
    is_partial: bool = False,
    existing_metadata: dict[str, Any] | None = None,
    stage_position: int | None = None,
) -> dict[str, Any]:
    """
    Validates an entity's `metadata` JSON payload against the tenant's registered
    `CustomFieldDefinition` schema for `entity_type` ('account', 'contact', 'deal').
    Supports lazy stage-gated validation via `min_stage_position` and blocks garbage placeholders.
    """
    base_meta = dict(existing_metadata or {}) if is_partial else {}
    if incoming_metadata:
        base_meta.update(incoming_metadata)

    definitions = list(
        (
            await session.scalars(
                select(CustomFieldDefinition).where(
                    CustomFieldDefinition.tenant_id == tenant_id,
                    CustomFieldDefinition.entity_type == entity_type,
                )
            )
        ).all()
    )

    if not definitions:
        return base_meta

    missing_fields: list[dict[str, Any]] = []
    first_missing_detail: str | None = None

    for defn in definitions:
        key = defn.field_key
        val = base_meta.get(key)

        if entity_type == "deal" and defn.min_stage_position is not None:
            is_stage_gated_required = (
                stage_position is not None and stage_position >= defn.min_stage_position
            )
            must_be_present = is_stage_gated_required
        else:
            is_stage_gated_required = False
            must_be_present = defn.is_required

        if val is None or val == "":
            if must_be_present:
                gate_reason = (
                    f"at pipeline stage position >= {defn.min_stage_position}"
                    if is_stage_gated_required
                    else f"for {entity_type}"
                )
                if first_missing_detail is None:
                    first_missing_detail = f"Custom field '{key}' ({defn.label}) is required {gate_reason}."
                missing_fields.append(
                    {
                        "field_key": key,
                        "label": defn.label,
                        "field_type": defn.field_type,
                        "allowed_values": list(defn.allowed_values or []),
                    }
                )
            continue

        _validate_single_field_value(defn, val)

    if missing_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=first_missing_detail or "Required custom fields are missing.",
            headers={"X-Stage-Gate-Fields": json.dumps(missing_fields)},
        )

    return base_meta


def _validate_single_field_value(defn: CustomFieldDefinition, val: Any) -> None:
    key = defn.field_key
    ftype = defn.field_type

    if ftype == "text":
        if not isinstance(val, str):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Custom field '{key}' must be a string (text).",
            )
        if (defn.is_required or defn.min_stage_position is not None) and (
            val.strip().lower() in _GARBAGE_PLACEHOLDERS
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"Custom field '{key}' contains a placeholder value ('{val}'). "
                    "Leave it empty until known or provide a valid business value."
                ),
            )

    elif ftype == "number":
        # Note: in Python isinstance(True, int) is True, so explicitly exclude bool
        if isinstance(val, bool) or not isinstance(val, (int, float, Decimal)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Custom field '{key}' must be a numeric value.",
            )

    elif ftype == "boolean":
        if not isinstance(val, bool):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Custom field '{key}' must be a boolean.",
            )

    elif ftype == "date":
        if not isinstance(val, str):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Custom field '{key}' must be an ISO date string (YYYY-MM-DD).",
            )
        try:
            date.fromisoformat(val)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Custom field '{key}' must be a valid ISO date (YYYY-MM-DD).",
            ) from exc

    elif ftype == "select":
        if not isinstance(val, str) or (defn.allowed_values and val not in defn.allowed_values):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Custom field '{key}' value '{val}' is not in allowed values: {defn.allowed_values}.",
            )

    elif ftype == "multi_select":
        if not isinstance(val, list) or any(
            not isinstance(item, str) or (defn.allowed_values and item not in defn.allowed_values)
            for item in val
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Custom field '{key}' must be a list of allowed options: {defn.allowed_values}.",
            )


def matches_custom_field_filter(
    metadata_dict: dict[str, Any] | None,
    cf_key: str | None,
    cf_value: str | None,
) -> bool:
    """Evaluates custom field equality/containment filter consistently across dialects."""
    if not cf_key:
        return True
    if not metadata_dict or cf_key not in metadata_dict:
        return False
    if cf_value is None:
        return True
    actual = metadata_dict[cf_key]
    if isinstance(actual, list):
        return cf_value in [str(x) for x in actual]
    return str(actual) == str(cf_value)
