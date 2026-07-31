"""Hybrid search engine — FTS5 + sqlite-vec with Reciprocal Rank Fusion."""

from __future__ import annotations

import logging
from typing import Any

from curator import database as db
from curator.services.embedder import EmbedderService, make_embed_text

log = logging.getLogger(__name__)


class SearchService:
    """Hybrid search: FTS5 keyword + vector semantic, merged via RRF."""

    def __init__(self, embedder: EmbedderService | None = None) -> None:
        self.embedder = embedder

    async def search(
        self,
        query: str,
        item_type: str | None = None,
        source: str | None = None,
        difficulty: str | None = None,
        language: str | None = None,
        tags: list[str] | None = None,
        archived: bool = False,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Run hybrid search and return (items, total).

        1. FTS5 keyword search
        2. Vector similarity search (if embeddings available)
        3. Reciprocal Rank Fusion to merge rankings
        4. Apply filters, paginate
        """
        if not query.strip():
            # No query — just list with filters
            return await db.list_items(
                item_type=item_type, source=source, difficulty=difficulty,
                language=language, tags=tags, archived=archived,
                date_from=date_from, date_to=date_to,
                limit=limit, offset=offset,
            )

        # --- FTS5 search ---
        fts_results = await _safe_fts_search(query, limit=200)
        fts_ranking: dict[int, int] = {}  # item_id → rank position
        for rank, r in enumerate(fts_results):
            fts_ranking[r["item_id"]] = rank

        # --- Vector search ---
        vec_ranking: dict[int, int] = {}
        if self.embedder:
            query_embedding = await self.embedder.embed_text(query)
            if query_embedding:
                vec_results = await db.vector_search(query_embedding, limit=200)
                for rank, r in enumerate(vec_results):
                    vec_ranking[r["item_id"]] = rank

        # --- Reciprocal Rank Fusion ---
        all_ids = set(fts_ranking.keys()) | set(vec_ranking.keys())
        if not all_ids:
            return [], 0

        k = 60  # RRF constant
        rrf_scores: dict[int, float] = {}

        for item_id in all_ids:
            score = 0.0
            if item_id in fts_ranking:
                score += 1.0 / (k + fts_ranking[item_id])
            if item_id in vec_ranking:
                score += 1.0 / (k + vec_ranking[item_id])
            rrf_scores[item_id] = score

        # Sort by RRF score descending
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

        # --- Fetch full items and apply filters ---
        filtered_items: list[dict[str, Any]] = []

        for item_id in sorted_ids:
            item = await db.get_item(item_id)
            if not item:
                continue

            # Apply filters
            if item.get("archived", False) != archived:
                continue
            if item_type and item.get("item_type") != item_type:
                continue
            if source and item.get("source") != source:
                continue
            if difficulty and item.get("difficulty") != difficulty:
                continue
            if language and item.get("language") != language:
                continue
            if date_from and item.get("created_at", "") < date_from:
                continue
            if date_to and item.get("created_at", "") > date_to:
                continue
            if tags:
                item_tags = {t["tag"] for t in item.get("tags", [])}
                if not set(t.lower() for t in tags).intersection(item_tags):
                    continue

            filtered_items.append(item)

        total = len(filtered_items)

        # Paginate
        page = filtered_items[offset : offset + limit]

        return page, total


async def _safe_fts_search(query: str, limit: int = 200) -> list[dict[str, Any]]:
    """Run FTS5 search, gracefully handling query syntax errors."""
    try:
        return await db.fts_search(query, limit=limit)
    except Exception:
        # If FTS query syntax fails, try quoting the entire query
        try:
            return await db.fts_search(f'"{query}"', limit=limit)
        except Exception as exc:
            log.warning("FTS search failed for query '%s': %s", query, exc)
            return []
