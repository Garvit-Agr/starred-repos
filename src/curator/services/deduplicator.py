"""Duplicate detection — URL, title similarity, semantic similarity."""

from __future__ import annotations

import difflib
import logging
from typing import Any

from curator import database as db
from curator.services.embedder import EmbedderService, make_embed_text

log = logging.getLogger(__name__)


class DeduplicatorService:
    """Three-layer duplicate detection. Never auto-deletes — only flags."""

    def __init__(
        self,
        embedder: EmbedderService | None = None,
        title_threshold: float = 0.85,
        semantic_threshold: float = 0.90,
    ) -> None:
        self.embedder = embedder
        self.title_threshold = title_threshold
        self.semantic_threshold = semantic_threshold

    async def check_duplicates(self, item_id: int) -> list[dict[str, Any]]:
        """Run all duplicate checks for a newly added item.

        Returns list of flagged duplicates: [{similar_to_id, match_type, score}]
        """
        item = await db.get_item(item_id)
        if not item:
            return []

        flagged: list[dict[str, Any]] = []

        # Step 1: Exact URL match
        if item.get("url"):
            url_matches = await self._check_url(item_id, item["url"])
            flagged.extend(url_matches)

        # Step 2: Title similarity
        title_matches = await self._check_title(item_id, item["title"])
        flagged.extend(title_matches)

        # Step 3: Semantic similarity (if embeddings available)
        semantic_matches = await self._check_semantic(item_id, item)
        flagged.extend(semantic_matches)

        # Deduplicate flags (same similar_to_id shouldn't appear twice)
        seen: set[int] = set()
        unique_flags: list[dict[str, Any]] = []
        for f in flagged:
            if f["similar_to_id"] not in seen:
                seen.add(f["similar_to_id"])
                unique_flags.append(f)

        # Persist flags
        for f in unique_flags:
            await db.flag_duplicate(
                item_id=item_id,
                similar_to_id=f["similar_to_id"],
                match_type=f["match_type"],
                score=f["score"],
            )

        return unique_flags

    async def _check_url(self, item_id: int, url: str) -> list[dict[str, Any]]:
        """Check for exact URL matches."""
        conn = await db.get_db()
        rows = await conn.execute_fetchall(
            "SELECT id FROM items WHERE url = ? AND id != ?", (url, item_id)
        )
        return [
            {"similar_to_id": r["id"], "match_type": "exact_url", "score": 1.0}
            for r in rows
        ]

    async def _check_title(self, item_id: int, title: str) -> list[dict[str, Any]]:
        """Check for title similarity using SequenceMatcher."""
        conn = await db.get_db()
        rows = await conn.execute_fetchall(
            "SELECT id, title FROM items WHERE id != ?", (item_id,)
        )
        matches: list[dict[str, Any]] = []
        title_lower = title.lower().strip()

        for r in rows:
            other_title = r["title"].lower().strip()
            ratio = difflib.SequenceMatcher(None, title_lower, other_title).ratio()
            if ratio >= self.title_threshold:
                matches.append({
                    "similar_to_id": r["id"],
                    "match_type": "title_similar",
                    "score": round(ratio, 4),
                })

        return matches

    async def _check_semantic(self, item_id: int, item: dict[str, Any]) -> list[dict[str, Any]]:
        """Check for semantic similarity via vector cosine distance."""
        if not self.embedder:
            return []

        # Generate embedding for the new item
        text = make_embed_text(
            item["title"],
            item.get("description", ""),
            [t["tag"] for t in item.get("tags", [])],
        )
        query_emb = await self.embedder.embed_text(text)
        if query_emb is None:
            return []

        # Search for nearest vectors
        vec_results = await db.vector_search(query_emb, limit=10)
        matches: list[dict[str, Any]] = []

        for vr in vec_results:
            if vr["item_id"] == item_id:
                continue
            # sqlite-vec returns cosine distance (0 = identical, 2 = opposite)
            # Convert to similarity: 1 - (distance / 2)
            similarity = 1.0 - (vr["distance"] / 2.0)
            if similarity >= self.semantic_threshold:
                matches.append({
                    "similar_to_id": vr["item_id"],
                    "match_type": "semantic",
                    "score": round(similarity, 4),
                })

        return matches
