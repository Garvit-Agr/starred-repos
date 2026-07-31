"""Items API — CRUD + tags + highlights."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from curator import database as db
from curator.models import (
    HighlightCreate,
    HighlightResponse,
    ItemCreate,
    ItemResponse,
    ItemUpdate,
    TagCreate,
)

router = APIRouter(prefix="/items", tags=["items"])


def _to_response(item: dict[str, Any]) -> ItemResponse:
    highlights = [
        HighlightResponse(**h) for h in item.get("highlights", [])
    ]
    return ItemResponse(
        id=item["id"],
        url=item.get("url"),
        title=item["title"],
        description=item.get("description", ""),
        item_type=item.get("item_type", "website"),
        source=item.get("source", "manual"),
        difficulty=item.get("difficulty"),
        language=item.get("language"),
        author=item.get("author"),
        created_at=item.get("created_at", ""),
        updated_at=item.get("updated_at", ""),
        starred_at=item.get("starred_at"),
        metadata=item.get("metadata", {}),
        notes=item.get("notes", ""),
        archived=item.get("archived", False),
        tags=item.get("tags", []),
        highlights=highlights,
        has_embedding=item.get("has_embedding", False),
    )


# ---------------------------------------------------------------------------
# Items CRUD
# ---------------------------------------------------------------------------

@router.get("")
async def list_items(
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
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    items, total = await db.list_items(
        item_type=item_type, source=source, difficulty=difficulty,
        language=language, tags=tag_list, archived=archived,
        date_from=date_from, date_to=date_to,
        limit=limit, offset=offset,
    )
    return {
        "items": [_to_response(i).model_dump() for i in items],
        "total": total,
    }


@router.post("", status_code=201)
async def create_item(
    payload: ItemCreate,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    item_id = await db.create_item(
        url=payload.url,
        title=payload.title,
        description=payload.description,
        item_type=payload.item_type.value,
        source=payload.source.value,
        difficulty=payload.difficulty.value if payload.difficulty else None,
        language=payload.language,
        author=payload.author,
        starred_at=payload.starred_at,
        metadata=payload.metadata,
        notes=payload.notes,
        tags=payload.tags,
    )
    # Enqueue background enrichment
    background_tasks.add_task(_enrich_item, item_id)

    item = await db.get_item(item_id)
    return _to_response(item).model_dump()


@router.get("/{item_id}")
async def get_item(item_id: int) -> dict[str, Any]:
    item = await db.get_item(item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    return _to_response(item).model_dump()


@router.put("/{item_id}")
async def update_item(item_id: int, payload: ItemUpdate) -> dict[str, Any]:
    fields = payload.model_dump(exclude_none=True)
    # Convert enums to values
    for k in ("item_type", "difficulty"):
        if k in fields and hasattr(fields[k], "value"):
            fields[k] = fields[k].value
    if "archived" in fields:
        fields["archived"] = int(fields["archived"])

    ok = await db.update_item(item_id, **fields)
    if not ok:
        raise HTTPException(404, "Item not found")
    item = await db.get_item(item_id)
    return _to_response(item).model_dump()


@router.delete("/{item_id}", status_code=204)
async def delete_item(item_id: int) -> None:
    ok = await db.delete_item(item_id)
    if not ok:
        raise HTTPException(404, "Item not found")


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

@router.post("/{item_id}/tags")
async def add_tag(item_id: int, payload: TagCreate) -> dict[str, str]:
    item = await db.get_item(item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    await db.add_tags(item_id, [payload.tag], payload.source.value)
    return {"status": "ok", "tag": payload.tag}


@router.delete("/{item_id}/tags/{tag}")
async def remove_tag(item_id: int, tag: str) -> dict[str, str]:
    await db.remove_tag(item_id, tag)
    return {"status": "ok"}


@router.get("/meta/tags")
async def all_tags() -> list[dict[str, Any]]:
    return await db.get_all_tags()


# ---------------------------------------------------------------------------
# Highlights
# ---------------------------------------------------------------------------

@router.post("/{item_id}/highlights", status_code=201)
async def create_highlight(item_id: int, payload: HighlightCreate) -> dict[str, Any]:
    item = await db.get_item(item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    hl_id = await db.create_highlight(
        item_id, payload.text, payload.annotation, payload.color, payload.position
    )
    return {"id": hl_id, "status": "created"}


@router.delete("/{item_id}/highlights/{highlight_id}", status_code=204)
async def delete_highlight(item_id: int, highlight_id: int) -> None:
    ok = await db.delete_highlight(highlight_id)
    if not ok:
        raise HTTPException(404, "Highlight not found")


# ---------------------------------------------------------------------------
# Background enrichment
# ---------------------------------------------------------------------------

async def _enrich_item(item_id: int) -> None:
    """Background task: auto-tag, embed, check duplicates."""
    from curator.server import get_services

    services = get_services()
    if not services:
        return

    item = await db.get_item(item_id)
    if not item:
        return

    cfg = services["config"]
    general = cfg.get("general", {})

    # Auto-tag
    if general.get("auto_tag_on_add", True) and services.get("tagger"):
        try:
            result = await services["tagger"].auto_tag(
                item["title"], item.get("url", ""), item.get("description", "")
            )
            if result.get("tags"):
                await db.add_tags(item_id, result["tags"], "ai")
            # Update item_type if AI suggests differently and user didn't specify
            if result.get("item_type") and item.get("item_type") == "website":
                await db.update_item(item_id, item_type=result["item_type"])
            if result.get("difficulty"):
                await db.update_item(item_id, difficulty=result["difficulty"])
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Auto-tag failed for item %d: %s", item_id, exc)

    # Embed
    if general.get("auto_embed_on_add", True) and services.get("embedder"):
        try:
            from curator.services.embedder import make_embed_text
            item = await db.get_item(item_id)  # Refresh to get AI tags
            text = make_embed_text(
                item["title"],
                item.get("description", ""),
                [t["tag"] for t in item.get("tags", [])],
            )
            embedding = await services["embedder"].embed_text(text)
            if embedding:
                await db.store_embedding(item_id, embedding, services["embedder"].model_name)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Embedding failed for item %d: %s", item_id, exc)

    # Duplicate check
    if general.get("auto_dedupe_on_add", True) and services.get("deduplicator"):
        try:
            await services["deduplicator"].check_duplicates(item_id)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Dedupe check failed for item %d: %s", item_id, exc)
