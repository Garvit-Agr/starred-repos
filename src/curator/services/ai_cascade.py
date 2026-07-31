"""AI Cascade — multi-provider AI with priority-based fallback.

Supports: OpenAI, Gemini (Google), Claude (Anthropic), Ollama (local).
Falls back to rule-based when all providers fail.
Uses httpx directly — no heavy litellm dependency.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

_PROVIDER_ENDPOINTS: dict[str, dict[str, str]] = {
    "openai": {
        "url": "https://api.openai.com/v1/chat/completions",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
    "claude": {
        "url": "https://api.anthropic.com/v1/messages",
        "auth_header": "x-api-key",
        "auth_prefix": "",
    },
    "ollama": {
        "url": "http://localhost:11434/v1/chat/completions",
        "auth_header": "",
        "auth_prefix": "",
    },
}


async def _call_openai_compatible(
    url: str,
    model: str,
    messages: list[dict[str, str]],
    api_key: str = "",
    timeout: int = 15,
) -> str | None:
    """Call an OpenAI-compatible chat endpoint."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {"model": model, "messages": messages, "temperature": 0.3}

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def _call_claude(
    model: str,
    messages: list[dict[str, str]],
    api_key: str,
    timeout: int = 15,
) -> str | None:
    """Call the Anthropic Messages API."""
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    # Convert OpenAI-style messages to Anthropic format
    system_msg = ""
    user_msgs = []
    for m in messages:
        if m["role"] == "system":
            system_msg = m["content"]
        else:
            user_msgs.append(m)

    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": 1024,
        "messages": user_msgs,
    }
    if system_msg:
        payload["system"] = system_msg

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages", json=payload, headers=headers
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]


# ---------------------------------------------------------------------------
# AI Cascade
# ---------------------------------------------------------------------------

class AICascade:
    """Multi-provider AI with priority fallback."""

    def __init__(self, providers: list[dict[str, Any]]) -> None:
        # Sort by priority (lowest = highest priority)
        self.providers = sorted(providers, key=lambda p: p.get("priority", 99))

    async def complete(
        self,
        prompt: str,
        system: str = "You are a helpful assistant.",
    ) -> str | None:
        """Try each provider in priority order. Returns response text or None."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        for provider in self.providers:
            name = provider.get("name", "")
            model = provider.get("model", "")
            api_key = provider.get("api_key", "")
            api_base = provider.get("api_base", "")
            timeout = provider.get("timeout", 15)

            try:
                if name == "claude":
                    result = await _call_claude(model, messages, api_key, timeout)
                elif name == "ollama":
                    base = api_base or "http://localhost:11434"
                    url = f"{base}/v1/chat/completions"
                    result = await _call_openai_compatible(url, model, messages, "", timeout)
                elif name == "gemini":
                    url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
                    result = await _call_openai_compatible(url, model, messages, api_key, timeout)
                elif name == "openai":
                    url = api_base or "https://api.openai.com/v1/chat/completions"
                    result = await _call_openai_compatible(url, model, messages, api_key, timeout)
                else:
                    # Generic OpenAI-compatible endpoint
                    url = api_base or _PROVIDER_ENDPOINTS.get(name, {}).get("url", "")
                    if not url:
                        continue
                    result = await _call_openai_compatible(url, model, messages, api_key, timeout)

                if result:
                    log.info("AI response from %s/%s", name, model)
                    return result
            except Exception as exc:
                log.warning("AI provider %s failed: %s", name, exc)
                continue

        log.info("All AI providers failed — returning None")
        return None


# ---------------------------------------------------------------------------
# Rule-based fallback (always works, zero dependencies)
# ---------------------------------------------------------------------------

# Topic → keyword mapping for rule-based tagging
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "machine-learning": ["ml", "machine learning", "deep learning", "neural", "tensorflow", "pytorch", "model", "training"],
    "web-development": ["web", "html", "css", "javascript", "react", "vue", "angular", "frontend", "backend", "api", "rest"],
    "python": ["python", "django", "flask", "fastapi", "pip", "conda"],
    "rust": ["rust", "cargo", "crate", "rustc"],
    "go": ["golang", "go ", "goroutine"],
    "devops": ["docker", "kubernetes", "k8s", "ci/cd", "pipeline", "deploy", "terraform", "ansible"],
    "database": ["sql", "database", "postgres", "mysql", "sqlite", "mongodb", "redis", "nosql"],
    "security": ["security", "encryption", "auth", "oauth", "jwt", "vulnerability", "cve"],
    "data-science": ["data science", "pandas", "numpy", "jupyter", "visualization", "statistics", "analytics"],
    "algorithms": ["algorithm", "data structure", "sorting", "graph", "tree", "leetcode", "competitive"],
    "systems": ["systems", "kernel", "os ", "operating system", "linux", "network", "distributed"],
    "mobile": ["ios", "android", "swift", "kotlin", "react native", "flutter", "mobile"],
    "cloud": ["aws", "azure", "gcp", "cloud", "serverless", "lambda"],
    "ai": ["ai", "artificial intelligence", "llm", "gpt", "language model", "nlp", "chatbot", "embedding"],
    "tutorial": ["tutorial", "guide", "how to", "introduction", "beginner", "learn", "course"],
    "tool": ["tool", "utility", "cli", "command line", "terminal", "editor", "ide"],
}

# URL pattern → item type mapping
URL_TYPE_PATTERNS: list[tuple[str, str]] = [
    (r"github\.com/[\w-]+/[\w-]+$", "repo"),
    (r"gitlab\.com/[\w-]+/[\w-]+$", "repo"),
    (r"medium\.com|dev\.to|hashnode|substack", "blog"),
    (r"coursera|udemy|edx|pluralsight|egghead|frontendmasters", "course"),
    (r"arxiv\.org|scholar\.google|papers", "document"),
    (r"youtube\.com|youtu\.be", "website"),
]


def rule_based_tags(title: str, description: str = "", url: str = "") -> list[str]:
    """Extract tags using keyword matching. Always works offline."""
    text = f"{title} {description} {url}".lower()
    matched_tags: list[str] = []

    for topic, keywords in TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                matched_tags.append(topic)
                break

    return matched_tags[:10]  # Cap at 10 tags


def rule_based_type(url: str) -> str:
    """Guess item type from URL patterns."""
    for pattern, item_type in URL_TYPE_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return item_type
    return "website"


def rule_based_summary(description: str, max_length: int = 200) -> str:
    """Generate a basic summary — just truncates."""
    if len(description) <= max_length:
        return description
    return description[:max_length].rsplit(" ", 1)[0] + "…"
