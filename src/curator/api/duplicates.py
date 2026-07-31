"""Duplicates API — review and resolve."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from curator import database as db
from curator.models import DuplicateResolve

router = APIRouter(prefix="/duplicates", tags=["duplicates"])


@router.get("")
async def list_duplicates(status: str = "pending") -> dict[str, Any]:
    dupes = await db.list_duplicates(status=status)
    return {"duplicates": dupes, "total": len(dupes)}


@router.put("/{dup_id}")
async def resolve_duplicate(dup_id: int, payload: DuplicateResolve) -> dict[str, str]:
    ok = await db.resolve_duplicate(
        dup_id, payload.status.value, payload.keep_item_id
    )
    if not ok:
        raise HTTPException(404, "Duplicate record not found")
    return {"status": "resolved"}
