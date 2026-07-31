"""Settings API — view/update config, stats, bookmarklet."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from curator import database as db
from curator.config import load_config, save_config, HOST, PORT
from curator.models import SettingsUpdate, StatsResponse

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def get_settings() -> dict[str, Any]:
    cfg = load_config()
    # Mask API keys for display
    safe_providers = []
    for p in cfg.get("ai", {}).get("providers", []):
        safe = {**p}
        if safe.get("api_key"):
            key = safe["api_key"]
            safe["api_key"] = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
            safe["has_key"] = True
        else:
            safe["has_key"] = False
        safe_providers.append(safe)

    return {
        "ai": {
            "enabled": cfg.get("ai", {}).get("enabled", True),
            "providers": safe_providers,
            "embedding": cfg.get("ai", {}).get("embedding", {}),
        },
        "general": cfg.get("general", {}),
        "github": {
            "username": cfg.get("github", {}).get("username", ""),
            "has_token": bool(cfg.get("github", {}).get("token")),
            "last_sync": cfg.get("github", {}).get("last_sync"),
        },
        "duplicate_detection": cfg.get("duplicate_detection", {}),
    }


@router.put("")
async def update_settings(payload: SettingsUpdate) -> dict[str, str]:
    cfg = load_config()

    if payload.ai_enabled is not None:
        cfg["ai"]["enabled"] = payload.ai_enabled

    if payload.providers is not None:
        cfg["ai"]["providers"] = [p.model_dump() for p in payload.providers]

    if payload.theme is not None:
        cfg["general"]["theme"] = payload.theme

    if payload.auto_tag_on_add is not None:
        cfg["general"]["auto_tag_on_add"] = payload.auto_tag_on_add
    if payload.auto_embed_on_add is not None:
        cfg["general"]["auto_embed_on_add"] = payload.auto_embed_on_add
    if payload.auto_dedupe_on_add is not None:
        cfg["general"]["auto_dedupe_on_add"] = payload.auto_dedupe_on_add

    if payload.embedding_prefer_local is not None:
        cfg["ai"]["embedding"]["prefer_local"] = payload.embedding_prefer_local
    if payload.embedding_local_model is not None:
        cfg["ai"]["embedding"]["local_model"] = payload.embedding_local_model

    if payload.github_username is not None:
        cfg["github"]["username"] = payload.github_username
    if payload.github_token is not None:
        cfg["github"]["token"] = payload.github_token

    if payload.title_threshold is not None:
        cfg["duplicate_detection"]["title_threshold"] = payload.title_threshold
    if payload.semantic_threshold is not None:
        cfg["duplicate_detection"]["semantic_threshold"] = payload.semantic_threshold

    save_config(cfg)
    return {"status": "saved"}


@router.get("/stats")
async def get_stats() -> dict[str, Any]:
    stats = await db.get_stats()
    # Add recent items
    items, _ = await db.list_items(limit=5, offset=0)
    from curator.api.items import _to_response
    stats["recent_items"] = [_to_response(i).model_dump() for i in items]
    return stats


@router.get("/bookmarklet")
async def get_bookmarklet() -> dict[str, str]:
    """Return the Safari bookmarklet JavaScript."""
    js = (
        "javascript:void(fetch('http://{host}:{port}/api/items',"
        "{{method:'POST',headers:{{'Content-Type':'application/json'}},"
        "body:JSON.stringify({{url:location.href,title:document.title,"
        "description:document.querySelector('meta[name=\"description\"]')"
        "?.content||''}})}})"
        ".then(r=>r.ok?alert('✓ Saved to Curator'):alert('✗ Save failed')))"
    ).format(host=HOST, port=PORT)

    return {"bookmarklet": js, "instructions": (
        "Drag this link to your Safari Bookmarks Bar: "
        "1. Show Bookmarks Bar (View → Show Bookmarks Bar). "
        "2. Create a new bookmark with any name like 'Save to Curator'. "
        "3. Edit the bookmark and paste the bookmarklet URL into the address field."
    )}
