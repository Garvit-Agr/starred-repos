"""GitHub stars importer — fetches starred repos via the GitHub API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
PER_PAGE = 100


class GitHubSyncService:
    """Import GitHub starred repositories."""

    def __init__(self, username: str = "", token: str = "") -> None:
        self.username = username
        self.token = token

    async def fetch_stars(
        self,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all starred repos for the configured user.

        Args:
            since: ISO 8601 timestamp — only return stars newer than this.

        Returns list of normalised item dicts ready for insertion.
        """
        if not self.username:
            raise ValueError("GitHub username not configured")

        headers: dict[str, str] = {
            "Accept": "application/vnd.github.v3.star+json",  # includes starred_at
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        items: list[dict[str, Any]] = []
        page = 1

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            while True:
                url = f"{GITHUB_API}/users/{self.username}/starred"
                params: dict[str, Any] = {"per_page": PER_PAGE, "page": page}

                resp = await client.get(url, params=params)
                if resp.status_code == 403:
                    log.warning("GitHub API rate limit reached. Got %d stars so far.", len(items))
                    break
                resp.raise_for_status()

                data = resp.json()
                if not data:
                    break

                for entry in data:
                    # With star+json accept header, each entry has {starred_at, repo}
                    repo = entry.get("repo", entry)
                    starred_at = entry.get("starred_at")

                    # Skip if before `since`
                    if since and starred_at and starred_at < since:
                        continue

                    item = _normalize_repo(repo, starred_at)
                    items.append(item)

                # Check if there are more pages
                link_header = resp.headers.get("Link", "")
                if 'rel="next"' not in link_header:
                    break
                page += 1

        log.info("Fetched %d starred repos for %s", len(items), self.username)
        return items


def _normalize_repo(repo: dict[str, Any], starred_at: str | None = None) -> dict[str, Any]:
    """Convert a GitHub API repo object into a Curator item dict."""
    topics = repo.get("topics", [])

    return {
        "url": repo.get("html_url", ""),
        "title": repo.get("full_name", repo.get("name", "Unknown")),
        "description": repo.get("description") or "",
        "item_type": "repo",
        "source": "github",
        "language": repo.get("language"),
        "author": repo.get("owner", {}).get("login", ""),
        "starred_at": starred_at,
        "metadata": {
            "github_stars": repo.get("stargazers_count", 0),
            "github_forks": repo.get("forks_count", 0),
            "github_topics": topics,
            "github_language": repo.get("language"),
            "github_owner": repo.get("owner", {}).get("login", ""),
            "github_last_push": repo.get("pushed_at"),
            "license": (repo.get("license") or {}).get("spdx_id", ""),
            "github_archived": repo.get("archived", False),
        },
        "tags": topics if topics else [],
    }
