"""Multi-format import/export — Safari, HTML, JSON, CSV, Markdown."""

from __future__ import annotations

import csv
import io
import json
import logging
import plistlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from html.parser import HTMLParser

from curator import database as db

log = logging.getLogger(__name__)


# =====================================================================
# IMPORT
# =====================================================================

async def import_items(raw_items: list[dict[str, Any]]) -> dict[str, int]:
    """Import a list of normalised item dicts. Returns stats."""
    created = 0
    skipped = 0

    for item in raw_items:
        url = item.get("url")
        # Skip exact URL duplicates
        if url and await db.url_exists(url):
            skipped += 1
            continue

        await db.create_item(
            url=url,
            title=item.get("title", url or "Untitled"),
            description=item.get("description", ""),
            item_type=item.get("item_type", "website"),
            source=item.get("source", "import"),
            difficulty=item.get("difficulty"),
            language=item.get("language"),
            author=item.get("author"),
            starred_at=item.get("starred_at"),
            metadata=item.get("metadata", {}),
            notes=item.get("notes", ""),
            tags=item.get("tags", []),
        )
        created += 1

    return {"total": len(raw_items), "created": created, "skipped": skipped}


# ---------------------------------------------------------------------------
# Safari bookmarks
# ---------------------------------------------------------------------------

def parse_safari_bookmarks(
    path: str | None = None,
) -> list[dict[str, Any]]:
    """Parse Safari's Bookmarks.plist (binary plist format)."""
    if path is None:
        path = str(Path.home() / "Library" / "Safari" / "Bookmarks.plist")

    plist_path = Path(path)
    if not plist_path.exists():
        raise FileNotFoundError(f"Safari bookmarks not found at {plist_path}")

    with open(plist_path, "rb") as f:
        plist = plistlib.load(f)

    items: list[dict[str, Any]] = []
    _walk_safari_plist(plist, items, tags=[])
    return items


def _walk_safari_plist(
    node: dict[str, Any],
    items: list[dict[str, Any]],
    tags: list[str],
) -> None:
    """Recursively walk the Safari plist tree."""
    web_type = node.get("WebBookmarkType", "")

    if web_type == "WebBookmarkTypeLeaf":
        url = node.get("URLString", "")
        title = node.get("URIDictionary", {}).get("title", url)
        if url and url.startswith(("http://", "https://")):
            items.append({
                "url": url,
                "title": title,
                "description": "",
                "item_type": "website",
                "source": "import",
                "tags": [t for t in tags if t],
            })

    elif web_type == "WebBookmarkTypeList":
        folder_title = node.get("Title", "")
        # Skip special folders
        if folder_title in ("com.apple.ReadingList",):
            return
        child_tags = tags + ([folder_title.lower()] if folder_title and folder_title != "BookmarksBar" else [])
        for child in node.get("Children", []):
            _walk_safari_plist(child, items, child_tags)


# ---------------------------------------------------------------------------
# Netscape HTML bookmarks
# ---------------------------------------------------------------------------

class _NetscapeParser(HTMLParser):
    """Parse Netscape bookmark HTML format (universal browser export)."""

    def __init__(self) -> None:
        super().__init__()
        self.items: list[dict[str, Any]] = []
        self.folder_stack: list[str] = []
        self._current_url: str | None = None
        self._current_title: str = ""
        self._in_a: bool = False
        self._in_h3: bool = False
        self._h3_text: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            attr_dict = dict(attrs)
            self._current_url = attr_dict.get("href", "")
            self._current_title = ""
            self._in_a = True
        elif tag.lower() == "h3":
            self._in_h3 = True
            self._h3_text = ""
        elif tag.lower() == "dl":
            pass  # folder nesting handled by h3

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._in_a:
            self._in_a = False
            if self._current_url and self._current_url.startswith(("http://", "https://")):
                self.items.append({
                    "url": self._current_url,
                    "title": self._current_title or self._current_url,
                    "description": "",
                    "item_type": "website",
                    "source": "import",
                    "tags": [f.lower() for f in self.folder_stack if f],
                })
            self._current_url = None
        elif tag.lower() == "h3" and self._in_h3:
            self._in_h3 = False
            self.folder_stack.append(self._h3_text.strip())
        elif tag.lower() == "dl" and self.folder_stack:
            self.folder_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._in_a:
            self._current_title += data
        elif self._in_h3:
            self._h3_text += data


def parse_netscape_html(html_content: str) -> list[dict[str, Any]]:
    """Parse Netscape bookmark HTML format."""
    parser = _NetscapeParser()
    parser.feed(html_content)
    return parser.items


# ---------------------------------------------------------------------------
# JSON import
# ---------------------------------------------------------------------------

def parse_json_import(json_content: str) -> list[dict[str, Any]]:
    """Parse a JSON array of items."""
    data = json.loads(json_content)
    if isinstance(data, dict):
        # Maybe it's a Curator export with a wrapper
        data = data.get("items", [data])
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array of items")

    items: list[dict[str, Any]] = []
    for entry in data:
        items.append({
            "url": entry.get("url"),
            "title": entry.get("title", entry.get("url", "Untitled")),
            "description": entry.get("description", ""),
            "item_type": entry.get("item_type", entry.get("type", "website")),
            "source": "import",
            "difficulty": entry.get("difficulty"),
            "language": entry.get("language"),
            "author": entry.get("author"),
            "starred_at": entry.get("starred_at"),
            "metadata": entry.get("metadata", {}),
            "notes": entry.get("notes", ""),
            "tags": entry.get("tags", []),
        })
    return items


# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------

def parse_csv_import(csv_content: str) -> list[dict[str, Any]]:
    """Parse CSV with headers: url, title, description, item_type, tags, ..."""
    reader = csv.DictReader(io.StringIO(csv_content))
    items: list[dict[str, Any]] = []

    for row in reader:
        tags_str = row.get("tags", "")
        tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
        items.append({
            "url": row.get("url"),
            "title": row.get("title", row.get("url", "Untitled")),
            "description": row.get("description", ""),
            "item_type": row.get("item_type", "website"),
            "source": "import",
            "difficulty": row.get("difficulty"),
            "language": row.get("language"),
            "author": row.get("author"),
            "notes": row.get("notes", ""),
            "tags": tags,
        })
    return items


# =====================================================================
# EXPORT
# =====================================================================

async def export_json() -> str:
    """Export all items as JSON."""
    items, _ = await db.list_items(limit=100000, offset=0)
    return json.dumps({"items": items, "exported_at": _now()}, indent=2, default=str)


async def export_csv() -> str:
    """Export all items as CSV."""
    items, _ = await db.list_items(limit=100000, offset=0)
    output = io.StringIO()
    fieldnames = [
        "id", "url", "title", "description", "item_type", "source",
        "difficulty", "language", "author", "created_at", "tags", "notes",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for item in items:
        row = {k: item.get(k, "") for k in fieldnames}
        row["tags"] = ", ".join(t["tag"] for t in item.get("tags", []))
        writer.writerow(row)
    return output.getvalue()


async def export_netscape_html() -> str:
    """Export as Netscape bookmarks HTML."""
    items, _ = await db.list_items(limit=100000, offset=0)
    lines = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        "<TITLE>Curator Bookmarks</TITLE>",
        "<H1>Curator Bookmarks</H1>",
        "<DL><p>",
    ]

    # Group by item_type
    by_type: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        t = item.get("item_type", "website")
        by_type.setdefault(t, []).append(item)

    for type_name, type_items in sorted(by_type.items()):
        lines.append(f"    <DT><H3>{type_name.title()}</H3>")
        lines.append("    <DL><p>")
        for item in type_items:
            url = item.get("url", "")
            title = item.get("title", "Untitled")
            if url:
                lines.append(f'        <DT><A HREF="{url}">{title}</A>')
            else:
                lines.append(f"        <DT>{title}")
        lines.append("    </DL><p>")

    lines.append("</DL><p>")
    return "\n".join(lines)


async def export_markdown(output_dir: str) -> int:
    """Export items as individual Markdown files with YAML frontmatter.

    Returns the number of files written.
    """
    items, _ = await db.list_items(limit=100000, offset=0)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    count = 0
    for item in items:
        # Sanitize title for filename
        safe_title = re.sub(r'[^\w\s-]', '', item.get("title", "untitled"))
        safe_title = re.sub(r'\s+', '-', safe_title).strip("-")[:80]
        filename = f"{item['id']:04d}-{safe_title}.md"

        tags = [t["tag"] for t in item.get("tags", [])]
        frontmatter = {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "type": item.get("item_type", ""),
            "source": item.get("source", ""),
            "tags": tags,
            "difficulty": item.get("difficulty", ""),
            "language": item.get("language", ""),
            "author": item.get("author", ""),
            "created_at": item.get("created_at", ""),
        }

        md_lines = ["---"]
        for k, v in frontmatter.items():
            if isinstance(v, list):
                md_lines.append(f"{k}: [{', '.join(v)}]")
            else:
                md_lines.append(f"{k}: {v}")
        md_lines.append("---")
        md_lines.append("")
        md_lines.append(f"# {item.get('title', 'Untitled')}")
        md_lines.append("")
        if item.get("description"):
            md_lines.append(item["description"])
            md_lines.append("")
        if item.get("notes"):
            md_lines.append("## Notes")
            md_lines.append("")
            md_lines.append(item["notes"])
            md_lines.append("")

        (out_path / filename).write_text("\n".join(md_lines))
        count += 1

    return count


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
