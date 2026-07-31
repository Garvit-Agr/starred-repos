"""Auto-tagging service — AI-based with rule-based fallback."""

from __future__ import annotations

import json
import logging
from typing import Any

from curator.services.ai_cascade import AICascade, rule_based_tags, rule_based_type

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a tagging assistant for a personal knowledge management system.
Given an item's title, URL, and description, return a JSON object with:
- "tags": array of 3-8 lowercase descriptive tags (e.g. "python", "web-development", "tutorial")
- "item_type": one of "repo", "website", "blog", "course", "textbook", "document", "note", "snippet"
- "difficulty": one of "beginner", "intermediate", "advanced", or null if not applicable

Rules:
- Tags should be specific and useful for filtering.
- Use hyphens for multi-word tags (e.g. "machine-learning", not "machine learning").
- Prefer established terms over obscure ones.
- Return ONLY valid JSON, no markdown fences, no extra text."""

USER_PROMPT_TEMPLATE = """Title: {title}
URL: {url}
Description: {description}"""


class TaggerService:
    """Auto-tag items using AI with rule-based fallback."""

    def __init__(self, ai_cascade: AICascade | None = None) -> None:
        self.ai_cascade = ai_cascade

    async def auto_tag(
        self,
        title: str,
        url: str = "",
        description: str = "",
    ) -> dict[str, Any]:
        """Return {"tags": [...], "item_type": str, "difficulty": str|None}.

        Tries AI first, falls back to rule-based.
        """
        # Try AI
        if self.ai_cascade:
            result = await self._ai_tag(title, url, description)
            if result:
                return result

        # Rule-based fallback
        return self._rule_tag(title, url, description)

    async def _ai_tag(
        self, title: str, url: str, description: str
    ) -> dict[str, Any] | None:
        """Use AI to generate tags."""
        prompt = USER_PROMPT_TEMPLATE.format(
            title=title, url=url or "(none)", description=description or "(none)"
        )

        response = await self.ai_cascade.complete(prompt, system=SYSTEM_PROMPT)
        if not response:
            return None

        try:
            # Clean response — strip markdown code fences if present
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
                cleaned = cleaned.rsplit("```", 1)[0]
            parsed = json.loads(cleaned.strip())

            tags = parsed.get("tags", [])
            item_type = parsed.get("item_type", "website")
            difficulty = parsed.get("difficulty")

            # Validate
            valid_types = {"repo", "website", "blog", "course", "textbook", "document", "note", "snippet"}
            valid_diff = {"beginner", "intermediate", "advanced", None}

            if item_type not in valid_types:
                item_type = "website"
            if difficulty not in valid_diff:
                difficulty = None

            return {
                "tags": [t.strip().lower().replace(" ", "-") for t in tags if t][:10],
                "item_type": item_type,
                "difficulty": difficulty,
            }
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            log.warning("Failed to parse AI tagging response: %s", exc)
            return None

    def _rule_tag(
        self, title: str, url: str, description: str
    ) -> dict[str, Any]:
        """Rule-based tagging fallback."""
        tags = rule_based_tags(title, description, url)
        item_type = rule_based_type(url) if url else "note"

        return {
            "tags": tags,
            "item_type": item_type,
            "difficulty": None,
        }
