"""Search API endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def search(
    q: str = "",
    item_type: str | None = None,
    source: str | None = None,
    difficulty: str | None = None,
    language: str | None = None,
    tags: str | None = Query(None, description="Comma-separated tags"),
    archived: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    from curator.server import get_services

    services = get_services()
    searcher = services.get("searcher") if services else None

    if searcher is None:
        # Fallback: just list with filters
        from curator import database as db
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        items, total = await db.list_items(
            item_type=item_type, source=source, difficulty=difficulty,
            language=language, tags=tag_list, archived=archived,
            date_from=date_from, date_to=date_to,
            limit=limit, offset=offset,
        )
        from curator.api.items import _to_response
        return {
            "items": [_to_response(i).model_dump() for i in items],
            "total": total,
            "query": q,
        }

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    items, total = await searcher.search(
        query=q,
        item_type=item_type,
        source=source,
        difficulty=difficulty,
        language=language,
        tags=tag_list,
        archived=archived,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    from curator.api.items import _to_response
    return {
        "items": [_to_response(i).model_dump() for i in items],
        "total": total,
        "query": q,
    }
