"""Export API — JSON, CSV, HTML, Markdown."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, Response

from curator.services import importer

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/json")
async def export_json() -> Response:
    content = await importer.export_json()
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=curator-export.json"},
    )


@router.get("/csv")
async def export_csv() -> Response:
    content = await importer.export_csv()
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=curator-export.csv"},
    )


@router.get("/html")
async def export_html() -> Response:
    content = await importer.export_netscape_html()
    return Response(
        content=content,
        media_type="text/html",
        headers={"Content-Disposition": "attachment; filename=curator-bookmarks.html"},
    )
