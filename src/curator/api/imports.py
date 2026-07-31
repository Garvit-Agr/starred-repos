"""Import API — GitHub stars, file upload (HTML/JSON/CSV)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File

from curator import database as db
from curator.services import importer
from curator.services.github_sync import GitHubSyncService

router = APIRouter(prefix="/import", tags=["import"])


@router.post("/github")
async def import_github(background_tasks: BackgroundTasks) -> dict[str, str]:
    """Import GitHub stars. Runs in background."""
    from curator.server import get_services
    services = get_services()
    if not services:
        raise HTTPException(500, "Services not initialised")

    cfg = services["config"]
    username = cfg.get("github", {}).get("username", "")
    token = cfg.get("github", {}).get("token", "")

    if not username:
        raise HTTPException(400, "GitHub username not configured. Set it in Settings.")

    background_tasks.add_task(_run_github_import, username, token, cfg)
    return {"status": "started", "message": f"Importing stars for {username}..."}


@router.post("/file")
async def import_file(
    file: UploadFile = File(...),
    format: str = "auto",
) -> dict[str, Any]:
    """Import from an uploaded file (HTML, JSON, CSV)."""
    content = (await file.read()).decode("utf-8", errors="replace")
    filename = file.filename or ""

    # Auto-detect format
    if format == "auto":
        if filename.endswith(".html") or filename.endswith(".htm") or "<!DOCTYPE NETSCAPE" in content[:200].upper():
            format = "html"
        elif filename.endswith(".json"):
            format = "json"
        elif filename.endswith(".csv"):
            format = "csv"
        else:
            raise HTTPException(400, "Cannot detect file format. Specify format=html|json|csv.")

    if format == "html":
        raw_items = importer.parse_netscape_html(content)
    elif format == "json":
        raw_items = importer.parse_json_import(content)
    elif format == "csv":
        raw_items = importer.parse_csv_import(content)
    else:
        raise HTTPException(400, f"Unsupported format: {format}")

    stats = await importer.import_items(raw_items)
    return {"status": "done", **stats}


@router.post("/safari")
async def import_safari() -> dict[str, Any]:
    """Import bookmarks from Safari's Bookmarks.plist."""
    try:
        raw_items = importer.parse_safari_bookmarks()
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Failed to parse Safari bookmarks: {exc}")

    stats = await importer.import_items(raw_items)
    return {"status": "done", **stats}


# ---------------------------------------------------------------------------
# Background GitHub import
# ---------------------------------------------------------------------------

async def _run_github_import(username: str, token: str, cfg: dict[str, Any]) -> None:
    """Background task for GitHub import."""
    import logging
    log = logging.getLogger(__name__)

    try:
        sync = GitHubSyncService(username=username, token=token)
        last_sync = cfg.get("github", {}).get("last_sync")
        raw_items = await sync.fetch_stars(since=last_sync)

        stats = await importer.import_items(raw_items)
        log.info("GitHub import done: %s", stats)

        # Enrich imported items (tag + embed + dedupe)
        from curator.server import get_services
        services = get_services()
        if services:
            conn = await db.get_db()
            # Get recently created items (from import)
            rows = await conn.execute_fetchall(
                "SELECT id FROM items WHERE source='github' ORDER BY created_at DESC LIMIT ?",
                (stats["created"],)
            )
            for row in rows:
                from curator.api.items import _enrich_item
                await _enrich_item(row["id"])

        # Update last_sync
        from datetime import datetime, timezone
        from curator.config import save_config
        cfg["github"]["last_sync"] = datetime.now(timezone.utc).isoformat()
        save_config(cfg)

    except Exception as exc:
        log.error("GitHub import failed: %s", exc)
