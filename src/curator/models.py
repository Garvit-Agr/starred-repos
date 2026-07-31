"""Pydantic models for Curator."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ItemType(str, enum.Enum):
    REPO = "repo"
    WEBSITE = "website"
    BLOG = "blog"
    COURSE = "course"
    TEXTBOOK = "textbook"
    DOCUMENT = "document"
    NOTE = "note"
    SNIPPET = "snippet"


class ItemSource(str, enum.Enum):
    GITHUB = "github"
    SAFARI = "safari"
    MANUAL = "manual"
    IMPORT = "import"


class TagSource(str, enum.Enum):
    AI = "ai"
    USER = "user"
    RULE = "rule"
    IMPORT = "import"


class Difficulty(str, enum.Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class MatchType(str, enum.Enum):
    EXACT_URL = "exact_url"
    TITLE_SIMILAR = "title_similar"
    SEMANTIC = "semantic"


class DuplicateStatus(str, enum.Enum):
    PENDING = "pending"
    DISMISSED = "dismissed"
    MERGED = "merged"


# ---------------------------------------------------------------------------
# Item models
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ItemCreate(BaseModel):
    url: str | None = None
    title: str
    description: str = ""
    item_type: ItemType = ItemType.WEBSITE
    source: ItemSource = ItemSource.MANUAL
    difficulty: Difficulty | None = None
    language: str | None = None
    author: str | None = None
    starred_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""
    tags: list[str] = Field(default_factory=list)


class ItemUpdate(BaseModel):
    url: str | None = None
    title: str | None = None
    description: str | None = None
    item_type: ItemType | None = None
    difficulty: Difficulty | None = None
    language: str | None = None
    author: str | None = None
    metadata: dict[str, Any] | None = None
    notes: str | None = None
    archived: bool | None = None
    tags: list[str] | None = None


class ItemResponse(BaseModel):
    id: int
    url: str | None
    title: str
    description: str
    item_type: str
    source: str
    difficulty: str | None
    language: str | None
    author: str | None
    created_at: str
    updated_at: str
    starred_at: str | None
    metadata: dict[str, Any]
    notes: str
    archived: bool
    tags: list[dict[str, str]]  # [{tag, source}, ...]
    highlights: list[HighlightResponse] = Field(default_factory=list)
    has_embedding: bool = False


# ---------------------------------------------------------------------------
# Tag models
# ---------------------------------------------------------------------------

class TagCreate(BaseModel):
    tag: str
    source: TagSource = TagSource.USER


# ---------------------------------------------------------------------------
# Highlight models
# ---------------------------------------------------------------------------

class HighlightCreate(BaseModel):
    text: str
    annotation: str = ""
    color: str = "yellow"
    position: int = 0


class HighlightResponse(BaseModel):
    id: int
    item_id: int
    text: str
    annotation: str
    color: str
    position: int
    created_at: str


# ---------------------------------------------------------------------------
# Duplicate models
# ---------------------------------------------------------------------------

class DuplicateResponse(BaseModel):
    id: int
    item_id: int
    similar_to_id: int
    match_type: str
    similarity_score: float
    status: str
    created_at: str
    item: ItemResponse | None = None
    similar_to: ItemResponse | None = None


class DuplicateResolve(BaseModel):
    status: DuplicateStatus  # dismissed or merged
    keep_item_id: int | None = None  # for merge: which item to keep


# ---------------------------------------------------------------------------
# Search models
# ---------------------------------------------------------------------------

class SearchQuery(BaseModel):
    q: str = ""
    item_type: ItemType | None = None
    source: ItemSource | None = None
    difficulty: Difficulty | None = None
    tags: list[str] = Field(default_factory=list)
    language: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    archived: bool = False
    limit: int = 50
    offset: int = 0


class SearchResult(BaseModel):
    items: list[ItemResponse]
    total: int
    query: str


# ---------------------------------------------------------------------------
# Settings / Config models
# ---------------------------------------------------------------------------

class AIProviderConfig(BaseModel):
    name: str  # openai, gemini, claude, ollama
    model: str
    api_key: str = ""
    api_base: str = ""
    priority: int = 1
    timeout: int = 15


class SettingsUpdate(BaseModel):
    ai_enabled: bool | None = None
    providers: list[AIProviderConfig] | None = None
    theme: str | None = None
    auto_tag_on_add: bool | None = None
    auto_embed_on_add: bool | None = None
    auto_dedupe_on_add: bool | None = None
    embedding_prefer_local: bool | None = None
    embedding_local_model: str | None = None
    github_username: str | None = None
    github_token: str | None = None
    title_threshold: float | None = None
    semantic_threshold: float | None = None


# ---------------------------------------------------------------------------
# Import / Export models
# ---------------------------------------------------------------------------

class ImportResult(BaseModel):
    total: int
    created: int
    skipped: int
    duplicates_flagged: int
    errors: list[str] = Field(default_factory=list)


class StatsResponse(BaseModel):
    total_items: int
    by_type: dict[str, int]
    by_source: dict[str, int]
    total_tags: int
    pending_duplicates: int
    has_embeddings: int
    recent_items: list[ItemResponse]
