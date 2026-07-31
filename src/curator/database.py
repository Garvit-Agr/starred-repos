"""SQLite database layer — schema, FTS5, sqlite-vec, and all CRUD operations."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

import aiosqlite
import sqlite_vec

from curator.config import DB_PATH, ensure_dirs

# ---------------------------------------------------------------------------
# Module-level connection (set during init_db / close_db)
# ---------------------------------------------------------------------------
_db: aiosqlite.Connection | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def get_db() -> aiosqlite.Connection:
    """Return the module-level DB connection."""
    if _db is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    return _db


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Open connection, load extensions, create schema."""
    global _db
    ensure_dirs()

    _db = await aiosqlite.connect(str(DB_PATH))
    _db.row_factory = aiosqlite.Row

    # Enable WAL mode for better concurrent read performance
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA foreign_keys=ON")

    # Load sqlite-vec extension
    await _db.enable_load_extension(True)
    await _db.execute("SELECT load_extension(?)", (sqlite_vec.loadable_path(),))
    await _db.enable_load_extension(False)

    await _create_schema()


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db:
        await _db.close()
        _db = None


async def _create_schema() -> None:
    """Create all tables, FTS5 index, and vector table."""
    db = await get_db()

    await db.executescript("""
        CREATE TABLE IF NOT EXISTS items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            url         TEXT,
            title       TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            item_type   TEXT NOT NULL DEFAULT 'website',
            source      TEXT NOT NULL DEFAULT 'manual',
            difficulty  TEXT,
            language    TEXT,
            author      TEXT,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            starred_at  TEXT,
            metadata    TEXT NOT NULL DEFAULT '{}',
            notes       TEXT NOT NULL DEFAULT '',
            archived    INTEGER NOT NULL DEFAULT 0,
            embedding_model TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_items_url ON items(url);
        CREATE INDEX IF NOT EXISTS idx_items_type ON items(item_type);
        CREATE INDEX IF NOT EXISTS idx_items_source ON items(source);
        CREATE INDEX IF NOT EXISTS idx_items_archived ON items(archived);

        CREATE TABLE IF NOT EXISTS tags (
            item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            tag     TEXT NOT NULL,
            source  TEXT NOT NULL DEFAULT 'user',
            PRIMARY KEY (item_id, tag)
        );

        CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag);

        CREATE TABLE IF NOT EXISTS highlights (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id    INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            text       TEXT NOT NULL,
            annotation TEXT NOT NULL DEFAULT '',
            color      TEXT NOT NULL DEFAULT 'yellow',
            position   INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS duplicates (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id         INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            similar_to_id   INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            match_type      TEXT NOT NULL,
            similarity_score REAL NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pending',
            created_at      TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_dup_status ON duplicates(status);
    """)

    # FTS5 virtual table (external content — synced manually)
    await db.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
            title, description, notes, tags_text,
            content='',
            contentless_delete=1
        )
    """)

    # sqlite-vec virtual table for embeddings (384-dim float32)
    await db.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_items USING vec0(
            item_id INTEGER PRIMARY KEY,
            embedding float[384]
        )
    """)

    await db.commit()


# ---------------------------------------------------------------------------
# Items CRUD
# ---------------------------------------------------------------------------

async def create_item(
    url: str | None,
    title: str,
    description: str = "",
    item_type: str = "website",
    source: str = "manual",
    difficulty: str | None = None,
    language: str | None = None,
    author: str | None = None,
    starred_at: str | None = None,
    metadata: dict[str, Any] | None = None,
    notes: str = "",
    tags: list[str] | None = None,
) -> int:
    """Insert a new item. Returns the new item ID."""
    db = await get_db()
    now = _now()
    cursor = await db.execute(
        """INSERT INTO items
           (url, title, description, item_type, source, difficulty,
            language, author, created_at, updated_at, starred_at, metadata, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            url, title, description, item_type, source, difficulty,
            language, author, now, now, starred_at,
            json.dumps(metadata or {}), notes,
        ),
    )
    item_id = cursor.lastrowid

    # Insert tags
    if tags:
        tag_source = "import" if source == "import" else "user"
        await db.executemany(
            "INSERT OR IGNORE INTO tags (item_id, tag, source) VALUES (?, ?, ?)",
            [(item_id, t.strip().lower(), tag_source) for t in tags if t.strip()],
        )

    # Update FTS
    await _fts_insert(item_id, title, description, notes, tags or [])

    await db.commit()
    return item_id


async def get_item(item_id: int) -> dict[str, Any] | None:
    """Fetch a single item with tags and highlights."""
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT * FROM items WHERE id = ?", (item_id,)
    )
    if not row:
        return None
    item = dict(row[0])
    item["metadata"] = json.loads(item["metadata"])
    item["archived"] = bool(item["archived"])

    # Tags
    tag_rows = await db.execute_fetchall(
        "SELECT tag, source FROM tags WHERE item_id = ?", (item_id,)
    )
    item["tags"] = [{"tag": r["tag"], "source": r["source"]} for r in tag_rows]

    # Highlights
    hl_rows = await db.execute_fetchall(
        "SELECT * FROM highlights WHERE item_id = ? ORDER BY position", (item_id,)
    )
    item["highlights"] = [dict(r) for r in hl_rows]

    # Has embedding?
    vec_row = await db.execute_fetchall(
        "SELECT 1 FROM vec_items WHERE item_id = ?", (item_id,)
    )
    item["has_embedding"] = len(vec_row) > 0

    return item


async def update_item(item_id: int, **fields: Any) -> bool:
    """Update item fields. Returns True if the item existed."""
    db = await get_db()
    # Separate tags from regular fields
    tags = fields.pop("tags", None)

    if fields:
        fields["updated_at"] = _now()
        if "metadata" in fields and isinstance(fields["metadata"], dict):
            fields["metadata"] = json.dumps(fields["metadata"])

        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [item_id]
        cursor = await db.execute(
            f"UPDATE items SET {set_clause} WHERE id = ?", values
        )
        if cursor.rowcount == 0:
            return False

    # Update tags if provided
    if tags is not None:
        await db.execute("DELETE FROM tags WHERE item_id = ? AND source = 'user'", (item_id,))
        await db.executemany(
            "INSERT OR IGNORE INTO tags (item_id, tag, source) VALUES (?, ?, 'user')",
            [(item_id, t.strip().lower()) for t in tags if t.strip()],
        )

    # Refresh FTS
    item = await get_item(item_id)
    if item:
        await _fts_delete(item_id)
        tag_list = [t["tag"] for t in item["tags"]]
        await _fts_insert(
            item_id, item["title"], item["description"], item["notes"], tag_list
        )

    await db.commit()
    return True


async def delete_item(item_id: int) -> bool:
    """Delete an item and all related data. Returns True if existed."""
    db = await get_db()
    await _fts_delete(item_id)
    try:
        await db.execute("DELETE FROM vec_items WHERE item_id = ?", (item_id,))
    except Exception:
        pass  # vec row may not exist
    cursor = await db.execute("DELETE FROM items WHERE id = ?", (item_id,))
    await db.commit()
    return cursor.rowcount > 0


async def list_items(
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
    """List items with filters. Returns (items, total_count)."""
    db = await get_db()
    where_clauses = ["i.archived = ?"]
    params: list[Any] = [int(archived)]

    if item_type:
        where_clauses.append("i.item_type = ?")
        params.append(item_type)
    if source:
        where_clauses.append("i.source = ?")
        params.append(source)
    if difficulty:
        where_clauses.append("i.difficulty = ?")
        params.append(difficulty)
    if language:
        where_clauses.append("i.language = ?")
        params.append(language)
    if date_from:
        where_clauses.append("i.created_at >= ?")
        params.append(date_from)
    if date_to:
        where_clauses.append("i.created_at <= ?")
        params.append(date_to)
    if tags:
        placeholders = ",".join("?" * len(tags))
        where_clauses.append(
            f"i.id IN (SELECT item_id FROM tags WHERE tag IN ({placeholders}))"
        )
        params.extend(t.lower() for t in tags)

    where_sql = " AND ".join(where_clauses)

    # Total count
    count_row = await db.execute_fetchall(
        f"SELECT COUNT(*) as cnt FROM items i WHERE {where_sql}", params
    )
    total = count_row[0]["cnt"]

    # Fetch page
    params_page = params + [limit, offset]
    rows = await db.execute_fetchall(
        f"""SELECT i.* FROM items i
            WHERE {where_sql}
            ORDER BY i.created_at DESC
            LIMIT ? OFFSET ?""",
        params_page,
    )

    items = []
    for row in rows:
        item = dict(row)
        item["metadata"] = json.loads(item["metadata"])
        item["archived"] = bool(item["archived"])
        # Fetch tags for each item
        tag_rows = await db.execute_fetchall(
            "SELECT tag, source FROM tags WHERE item_id = ?", (item["id"],)
        )
        item["tags"] = [{"tag": r["tag"], "source": r["source"]} for r in tag_rows]
        item["highlights"] = []
        vec_row = await db.execute_fetchall(
            "SELECT 1 FROM vec_items WHERE item_id = ?", (item["id"],)
        )
        item["has_embedding"] = len(vec_row) > 0
        items.append(item)

    return items, total


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

async def add_tags(item_id: int, tags: list[str], source: str = "user") -> None:
    """Add tags to an item."""
    db = await get_db()
    await db.executemany(
        "INSERT OR IGNORE INTO tags (item_id, tag, source) VALUES (?, ?, ?)",
        [(item_id, t.strip().lower(), source) for t in tags if t.strip()],
    )
    await db.commit()


async def remove_tag(item_id: int, tag: str) -> None:
    """Remove a specific tag from an item."""
    db = await get_db()
    await db.execute(
        "DELETE FROM tags WHERE item_id = ? AND tag = ?", (item_id, tag.lower())
    )
    await db.commit()


async def get_all_tags() -> list[dict[str, Any]]:
    """Get all unique tags with counts."""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT tag, COUNT(*) as count FROM tags GROUP BY tag ORDER BY count DESC"
    )
    return [{"tag": r["tag"], "count": r["count"]} for r in rows]


# ---------------------------------------------------------------------------
# Highlights
# ---------------------------------------------------------------------------

async def create_highlight(
    item_id: int, text: str, annotation: str = "", color: str = "yellow", position: int = 0
) -> int:
    """Create a highlight. Returns highlight ID."""
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO highlights (item_id, text, annotation, color, position, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (item_id, text, annotation, color, position, _now()),
    )
    await db.commit()
    return cursor.lastrowid


async def delete_highlight(highlight_id: int) -> bool:
    """Delete a highlight."""
    db = await get_db()
    cursor = await db.execute("DELETE FROM highlights WHERE id = ?", (highlight_id,))
    await db.commit()
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------

async def flag_duplicate(
    item_id: int, similar_to_id: int, match_type: str, score: float
) -> int:
    """Flag a potential duplicate. Returns duplicate record ID."""
    db = await get_db()
    # Check if this pair already exists (in either direction)
    existing = await db.execute_fetchall(
        """SELECT id FROM duplicates
           WHERE (item_id = ? AND similar_to_id = ?)
              OR (item_id = ? AND similar_to_id = ?)""",
        (item_id, similar_to_id, similar_to_id, item_id),
    )
    if existing:
        return existing[0]["id"]

    cursor = await db.execute(
        """INSERT INTO duplicates (item_id, similar_to_id, match_type, similarity_score, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (item_id, similar_to_id, match_type, score, _now()),
    )
    await db.commit()
    return cursor.lastrowid


async def list_duplicates(status: str = "pending") -> list[dict[str, Any]]:
    """List duplicate flags with item data."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT d.* FROM duplicates d WHERE d.status = ? ORDER BY d.created_at DESC""",
        (status,),
    )
    results = []
    for row in rows:
        dup = dict(row)
        dup["item"] = await get_item(dup["item_id"])
        dup["similar_to"] = await get_item(dup["similar_to_id"])
        results.append(dup)
    return results


async def resolve_duplicate(dup_id: int, status: str, keep_item_id: int | None = None) -> bool:
    """Resolve a duplicate flag. If merge, delete the other item."""
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT * FROM duplicates WHERE id = ?", (dup_id,)
    )
    if not row:
        return False

    dup = dict(row[0])

    if status == "merged" and keep_item_id:
        delete_id = (
            dup["similar_to_id"] if keep_item_id == dup["item_id"] else dup["item_id"]
        )
        await delete_item(delete_id)

    await db.execute(
        "UPDATE duplicates SET status = ? WHERE id = ?", (status, dup_id)
    )
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Embeddings (sqlite-vec)
# ---------------------------------------------------------------------------

async def store_embedding(item_id: int, embedding: list[float], model_name: str) -> None:
    """Store a vector embedding for an item."""
    db = await get_db()
    vec_bytes = sqlite_vec.serialize_float32(embedding)
    try:
        await db.execute("DELETE FROM vec_items WHERE item_id = ?", (item_id,))
    except Exception:
        pass
    await db.execute(
        "INSERT INTO vec_items (item_id, embedding) VALUES (?, ?)",
        (item_id, vec_bytes),
    )
    await db.execute(
        "UPDATE items SET embedding_model = ? WHERE id = ?", (model_name, item_id)
    )
    await db.commit()


async def vector_search(query_embedding: list[float], limit: int = 20) -> list[dict[str, Any]]:
    """Find nearest neighbours by cosine similarity."""
    db = await get_db()
    vec_bytes = sqlite_vec.serialize_float32(query_embedding)
    rows = await db.execute_fetchall(
        """SELECT item_id, distance
           FROM vec_items
           WHERE embedding MATCH ?
           ORDER BY distance
           LIMIT ?""",
        (vec_bytes, limit),
    )
    return [{"item_id": r["item_id"], "distance": r["distance"]} for r in rows]


async def get_all_embeddings() -> list[tuple[int, list[float]]]:
    """Get all item_id→embedding pairs (for duplicate detection)."""
    db = await get_db()
    rows = await db.execute_fetchall("SELECT item_id, embedding FROM vec_items")
    results = []
    for r in rows:
        # sqlite-vec returns raw bytes; we just pass them along
        results.append((r["item_id"], r["embedding"]))
    return results


# ---------------------------------------------------------------------------
# FTS5 helpers
# ---------------------------------------------------------------------------

async def _fts_insert(item_id: int, title: str, description: str, notes: str, tags: list[str]) -> None:
    db = await get_db()
    tags_text = " ".join(tags)
    await db.execute(
        "INSERT INTO items_fts (rowid, title, description, notes, tags_text) VALUES (?, ?, ?, ?, ?)",
        (item_id, title, description, notes, tags_text),
    )


async def _fts_delete(item_id: int) -> None:
    db = await get_db()
    try:
        await db.execute(
            "DELETE FROM items_fts WHERE rowid = ?", (item_id,)
        )
    except Exception:
        pass


async def fts_search(query: str, limit: int = 50) -> list[dict[str, Any]]:
    """Full-text search using FTS5 with BM25 ranking."""
    db = await get_db()
    # Escape FTS5 special characters
    safe_query = query.replace('"', '""')
    rows = await db.execute_fetchall(
        """SELECT rowid, rank
           FROM items_fts
           WHERE items_fts MATCH ?
           ORDER BY rank
           LIMIT ?""",
        (safe_query, limit),
    )
    return [{"item_id": r["rowid"], "rank": r["rank"]} for r in rows]


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

async def get_stats() -> dict[str, Any]:
    """Get aggregate statistics."""
    db = await get_db()

    total = (await db.execute_fetchall("SELECT COUNT(*) as c FROM items WHERE archived=0"))[0]["c"]

    type_rows = await db.execute_fetchall(
        "SELECT item_type, COUNT(*) as c FROM items WHERE archived=0 GROUP BY item_type"
    )
    by_type = {r["item_type"]: r["c"] for r in type_rows}

    source_rows = await db.execute_fetchall(
        "SELECT source, COUNT(*) as c FROM items WHERE archived=0 GROUP BY source"
    )
    by_source = {r["source"]: r["c"] for r in source_rows}

    tag_count = (await db.execute_fetchall("SELECT COUNT(DISTINCT tag) as c FROM tags"))[0]["c"]

    pending_dups = (await db.execute_fetchall(
        "SELECT COUNT(*) as c FROM duplicates WHERE status='pending'"
    ))[0]["c"]

    embed_count = (await db.execute_fetchall("SELECT COUNT(*) as c FROM vec_items"))[0]["c"]

    return {
        "total_items": total,
        "by_type": by_type,
        "by_source": by_source,
        "total_tags": tag_count,
        "pending_duplicates": pending_dups,
        "has_embeddings": embed_count,
    }


async def url_exists(url: str) -> int | None:
    """Check if a URL already exists. Returns item ID or None."""
    db = await get_db()
    rows = await db.execute_fetchall("SELECT id FROM items WHERE url = ?", (url,))
    return rows[0]["id"] if rows else None
