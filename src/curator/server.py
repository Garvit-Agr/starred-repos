"""FastAPI server — app factory, lifespan, static serving."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from curator import database as db
from curator.config import STATIC_DIR, load_config, get_ai_providers
from curator.api import items, search, duplicates, imports, exports, settings

log = logging.getLogger(__name__)

# Module-level services dict — initialised during lifespan
_services: dict[str, Any] | None = None


def get_services() -> dict[str, Any] | None:
    """Access the global services dict."""
    return _services


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, load services. Shutdown: close DB."""
    global _services

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Init database
    await db.init_db()
    log.info("Database initialised at %s", db.DB_PATH)

    # Load config and init services
    cfg = load_config()
    _services = _init_services(cfg)
    log.info("Services initialised (AI enabled: %s)", cfg.get("ai", {}).get("enabled", True))

    yield

    # Shutdown
    await db.close_db()
    _services = None
    log.info("Curator shut down")


def _init_services(cfg: dict[str, Any]) -> dict[str, Any]:
    """Initialise all service objects from config."""
    from curator.services.ai_cascade import AICascade
    from curator.services.embedder import EmbedderService
    from curator.services.tagger import TaggerService
    from curator.services.searcher import SearchService
    from curator.services.deduplicator import DeduplicatorService

    services: dict[str, Any] = {"config": cfg}

    # AI Cascade
    ai_enabled = cfg.get("ai", {}).get("enabled", True)
    providers = get_ai_providers(cfg) if ai_enabled else []
    cascade = AICascade(providers) if providers else None
    services["ai_cascade"] = cascade

    # Embedder
    embed_cfg = cfg.get("ai", {}).get("embedding", {})
    embedder = EmbedderService(
        ai_cascade=cascade,
        prefer_local=embed_cfg.get("prefer_local", True),
        local_model=embed_cfg.get("local_model", "sentence-transformers/all-MiniLM-L6-v2"),
    )
    services["embedder"] = embedder

    # Tagger
    services["tagger"] = TaggerService(ai_cascade=cascade)

    # Searcher
    services["searcher"] = SearchService(embedder=embedder)

    # Deduplicator
    dup_cfg = cfg.get("duplicate_detection", {})
    services["deduplicator"] = DeduplicatorService(
        embedder=embedder,
        title_threshold=dup_cfg.get("title_threshold", 0.85),
        semantic_threshold=dup_cfg.get("semantic_threshold", 0.90),
    )

    return services


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Curator",
        description="Local-first personal knowledge & bookmark manager",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS for local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(items.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    app.include_router(duplicates.router, prefix="/api")
    app.include_router(imports.router, prefix="/api")
    app.include_router(exports.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")

    # Serve static frontend files
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.get("/")
        async def root():
            return FileResponse(str(STATIC_DIR / "index.html"))

        # Catch-all for SPA routing — serve index.html for any unmatched path
        @app.get("/{path:path}")
        async def spa_fallback(path: str):
            # Check if it's a static file first
            static_file = STATIC_DIR / path
            if static_file.exists() and static_file.is_file():
                return FileResponse(str(static_file))
            return FileResponse(str(STATIC_DIR / "index.html"))

    return app
