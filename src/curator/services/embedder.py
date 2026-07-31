"""Embedding service — local (fastembed) or API-based vector generation."""

from __future__ import annotations

import logging
from typing import Any

from curator.services.ai_cascade import AICascade

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Local embedding via fastembed (lazy-loaded)
# ---------------------------------------------------------------------------

_local_model: Any = None
_local_model_name: str = ""


def _get_local_model(model_name: str) -> Any:
    """Lazy-load the fastembed model."""
    global _local_model, _local_model_name
    if _local_model is not None and _local_model_name == model_name:
        return _local_model
    try:
        from fastembed import TextEmbedding
        log.info("Loading local embedding model: %s", model_name)
        _local_model = TextEmbedding(model_name)
        _local_model_name = model_name
        return _local_model
    except Exception as exc:
        log.warning("Failed to load local embedding model: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Embedder service
# ---------------------------------------------------------------------------

class EmbedderService:
    """Generate embeddings using local model or API fallback."""

    def __init__(
        self,
        ai_cascade: AICascade | None = None,
        prefer_local: bool = True,
        local_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    ) -> None:
        self.ai_cascade = ai_cascade
        self.prefer_local = prefer_local
        self.local_model_name = local_model
        self._dimension = 384  # MiniLM-L6-v2 output dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self.local_model_name if self.prefer_local else "api"

    async def embed_text(self, text: str) -> list[float] | None:
        """Generate an embedding for the given text.

        Priority:
        1. Local model (fastembed) if prefer_local=True
        2. AI cascade API (OpenAI embeddings endpoint)
        3. None (caller should fall back to FTS-only)
        """
        if self.prefer_local:
            result = self._embed_local(text)
            if result is not None:
                return result

        # API fallback
        result = await self._embed_api(text)
        if result is not None:
            return result

        # If local wasn't tried first, try it as last resort
        if not self.prefer_local:
            result = self._embed_local(text)
            if result is not None:
                return result

        return None

    async def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        """Embed multiple texts. Returns list aligned with input."""
        if self.prefer_local:
            model = _get_local_model(self.local_model_name)
            if model is not None:
                try:
                    embeddings = list(model.embed(texts))
                    return [emb.tolist() for emb in embeddings]
                except Exception as exc:
                    log.warning("Batch local embedding failed: %s", exc)

        # Fall back to individual API calls
        results = []
        for text in texts:
            emb = await self.embed_text(text)
            results.append(emb)
        return results

    def _embed_local(self, text: str) -> list[float] | None:
        """Generate embedding using local fastembed model."""
        model = _get_local_model(self.local_model_name)
        if model is None:
            return None
        try:
            embeddings = list(model.embed([text]))
            return embeddings[0].tolist()
        except Exception as exc:
            log.warning("Local embedding failed: %s", exc)
            return None

    async def _embed_api(self, text: str) -> list[float] | None:
        """Generate embedding via OpenAI-compatible API."""
        if not self.ai_cascade or not self.ai_cascade.providers:
            return None

        import httpx

        for provider in self.ai_cascade.providers:
            if provider.get("name") not in ("openai", "gemini"):
                continue  # Only OpenAI and Gemini have embedding endpoints
            try:
                api_key = provider.get("api_key", "")
                timeout = provider.get("timeout", 15)

                if provider["name"] == "openai":
                    url = "https://api.openai.com/v1/embeddings"
                    payload = {
                        "model": "text-embedding-3-small",
                        "input": text,
                    }
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    }
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        resp = await client.post(url, json=payload, headers=headers)
                        resp.raise_for_status()
                        data = resp.json()
                        embedding = data["data"][0]["embedding"]
                        # Resize to 384 dims if needed (truncate or pad)
                        if len(embedding) > self._dimension:
                            embedding = embedding[: self._dimension]
                        elif len(embedding) < self._dimension:
                            embedding.extend([0.0] * (self._dimension - len(embedding)))
                        return embedding

                elif provider["name"] == "gemini":
                    url = "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent"
                    payload = {
                        "content": {"parts": [{"text": text}]},
                    }
                    headers = {
                        "Content-Type": "application/json",
                        "x-goog-api-key": api_key,
                    }
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        resp = await client.post(url, json=payload, headers=headers)
                        resp.raise_for_status()
                        data = resp.json()
                        embedding = data["embedding"]["values"]
                        if len(embedding) > self._dimension:
                            embedding = embedding[: self._dimension]
                        elif len(embedding) < self._dimension:
                            embedding.extend([0.0] * (self._dimension - len(embedding)))
                        return embedding

            except Exception as exc:
                log.warning("API embedding via %s failed: %s", provider["name"], exc)
                continue

        return None


def make_embed_text(title: str, description: str = "", tags: list[str] | None = None) -> str:
    """Compose the text that gets embedded for an item."""
    parts = [title]
    if description:
        parts.append(description)
    if tags:
        parts.append("Tags: " + ", ".join(tags))
    return " | ".join(parts)
