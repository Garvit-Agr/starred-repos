# 📚 Curator

**Local-first personal knowledge & bookmark management for macOS.**

Save, organize, search, and rediscover your starred repos, bookmarks, blogs, courses, textbooks, documents, notes, and snippets — all from one place, on your own machine.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **One-click save** | Safari bookmarklet to save any page instantly |
| **AI auto-tagging** | Automatically categorize items using AI (OpenAI, Gemini, Claude, or Ollama) |
| **Semantic search** | Find items by meaning, not just keywords — powered by local vector embeddings |
| **Hybrid search** | Combines full-text (FTS5) + semantic (vectors) with Reciprocal Rank Fusion |
| **Duplicate detection** | 3-layer detection (URL, title similarity, semantic similarity) — never auto-deletes |
| **GitHub stars import** | Import all your starred repositories with full metadata |
| **Safari bookmarks import** | Import directly from Safari's bookmark file |
| **Notes & highlights** | Add personal notes (Markdown) and highlighted excerpts per item |
| **Multi-format import/export** | Netscape HTML, JSON, CSV, Markdown |
| **AI fallback cascade** | OpenAI → Gemini → Claude → Ollama → rule-based (always works offline) |
| **Multi API-key support** | Configure multiple AI providers in priority order |
| **Auto-start** | Runs as a macOS LaunchAgent — starts at login, invisible in background |
| **Lightweight** | ~50 MB RAM idle, single SQLite file, no Docker, no external services |
| **Privacy** | All data stays on your machine. AI is optional and configurable |

---

## 🚀 Quick Start

### Prerequisites

- **macOS** (tested on Apple Silicon, works on Intel too)
- **Python 3.12+** (installed by `uv` if needed)
- **Internet** only needed for: AI features (optional), GitHub import, initial package install

### Install

```bash
# Clone the repo
git clone https://github.com/your-username/curator.git
cd curator

# Run the install script (installs everything + auto-start)
bash scripts/install.sh
```

That's it. Curator is now running at **http://localhost:7745**.

### First Steps

1. Open **http://localhost:7745** in Safari
2. Go to **Settings** → copy the bookmarklet → add it to your Safari toolbar
3. Set your **GitHub username** in Settings for star imports
4. (Optional) Add **AI API keys** for smart tagging and better search

---

## 📖 Usage

### Web UI

Open **http://localhost:7745** in any browser. The interface has:

| Page | Purpose |
|------|---------|
| **Dashboard** | Overview stats, recent items |
| **Browse** | Search, filter, and explore all items |
| **Duplicates** | Review and resolve flagged duplicate items |
| **Import/Export** | Import from GitHub/Safari/files, export your data |
| **Settings** | API keys, GitHub config, bookmarklet, preferences |

### CLI Commands

```bash
# Server management
curator serve              # Start the web server (done automatically by LaunchAgent)
curator stop               # Stop the background service
curator status             # Check if Curator is running
curator open               # Open the web UI in your default browser

# Quick operations
curator add "https://example.com" --title "Example" --type blog --tags "web,tutorial"
curator search "machine learning"

# Import
curator import github --user your-username        # Import GitHub stars
curator import safari                              # Import Safari bookmarks
curator import html bookmarks.html                 # Import Netscape HTML
curator import json data.json                      # Import JSON file

# Export
curator export json -o backup.json                 # Export as JSON
curator export csv -o items.csv                    # Export as CSV
curator export html -o bookmarks.html              # Export as Netscape HTML
```

### Safari Bookmarklet

The bookmarklet lets you save any page with one click:

1. Go to **Settings** in the web UI
2. Copy the bookmarklet code
3. In Safari: **Bookmarks → Add Bookmark** → name it "Save to Curator"
4. Edit the bookmark → replace the URL with the bookmarklet code
5. Click it on any page to save instantly

---

## 🏗 Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    User Interaction                          │
│  Safari Bookmarklet  │  Web UI (localhost:7745)  │  CLI     │
└──────────┬───────────┴──────────┬────────────────┴──┬───────┘
           │                      │                    │
           ▼                      ▼                    ▼
┌──────────────────────────────────────────────────────────────┐
│                FastAPI Server (auto-starts at login)         │
│                                                              │
│  /api/items      — CRUD + tags + highlights                  │
│  /api/search     — Hybrid FTS5 + vector search               │
│  /api/duplicates — Review & resolve flagged duplicates        │
│  /api/import     — GitHub stars, Safari, file upload          │
│  /api/export     — JSON, CSV, HTML download                  │
│  /api/settings   — Config, stats, bookmarklet                │
│  /static         — Web UI (HTML/CSS/JS)                      │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│        SQLite Database (single file: curator.db)             │
│                                                              │
│  items          — All saved items with metadata              │
│  tags           — Many-to-many item ↔ tag                    │
│  highlights     — Highlighted excerpts + annotations         │
│  duplicates     — Flagged potential duplicates               │
│  items_fts      — FTS5 full-text index (BM25 ranking)        │
│  vec_items      — sqlite-vec embeddings (384-dim float32)    │
└──────────────────────────────────────────────────────────────┘
```

### Auto-Start (LaunchAgent)

Curator runs as a macOS **LaunchAgent** — a native background service that:
- Starts automatically when you log in
- Restarts if it crashes
- Runs at low priority (doesn't compete with your work)
- Stops when you log out

You never need to manually start a server. Just open the browser.

---

## 🔍 How Search Works

Curator uses **hybrid search** — combining keyword and semantic search:

1. **Full-Text Search (FTS5)**: SQLite's built-in full-text search with BM25 ranking. Searches through titles, descriptions, notes, and tags. Always available, works offline.

2. **Semantic Search (sqlite-vec)**: Vector similarity using 384-dimensional embeddings generated by `all-MiniLM-L6-v2` (an 80 MB model that runs locally on your CPU). Finds items by *meaning*, not exact keywords.

3. **Reciprocal Rank Fusion (RRF)**: Merges results from both systems using the formula `score = Σ(1 / (k + rank_i))`. This produces better results than either system alone, without needing manual weight tuning.

**Graceful degradation**: If embeddings aren't available (no model downloaded yet, or AI is off), search falls back to FTS-only — still fast and useful.

---

## 🤖 AI Cascade

AI is **optional**. When configured, Curator tries providers in priority order:

```
Provider 1 (e.g., OpenAI gpt-4o-mini)
    ↓ fail/timeout/quota
Provider 2 (e.g., Gemini gemini-2.5-flash)
    ↓ fail
Provider 3 (e.g., Ollama llama3.2 — local)
    ↓ fail/not installed
Rule-Based Fallback (always works — keyword extraction + URL patterns)
```

### What AI does

| Task | With AI | Without AI |
|------|---------|-----------|
| **Tagging** | AI analyzes title/URL/description and generates relevant tags | Keywords extracted via TF-IDF + predefined topic mappings |
| **Type detection** | AI classifies items (repo, blog, course, etc.) | URL pattern matching (github.com → repo, medium.com → blog) |
| **Difficulty** | AI estimates beginner/intermediate/advanced | Not assigned |
| **Embeddings** | Generated locally (fastembed) or via API | Not generated — FTS-only search |
| **Duplicate detection** | Semantic similarity (cosine distance on embeddings) | URL exact match + title string similarity |

### Supported Providers

| Provider | Config Key | Notes |
|----------|-----------|-------|
| **OpenAI** | `openai` | Recommended for tagging quality |
| **Google Gemini** | `gemini` | Free tier available, good quality |
| **Anthropic Claude** | `claude` | High quality, higher cost |
| **Ollama** | `ollama` | Fully local, no API key needed. Install from [ollama.com](https://ollama.com) |

Configure in the **Settings** page or in `~/Library/Application Support/Curator/config.json`.

---

## 🔄 Duplicate Detection

When you add a new item, Curator checks for duplicates in 3 layers:

| Layer | Method | Threshold |
|-------|--------|-----------|
| 1. **Exact URL** | String match on URL | 100% match |
| 2. **Title similarity** | SequenceMatcher (Ratcliff/Obershelp) | ≥ 85% similar |
| 3. **Semantic similarity** | Cosine similarity on embeddings | ≥ 90% similar |

**Curator never auto-deletes or auto-merges.** Duplicates are flagged as "pending" and displayed in the **Duplicates** page where you can:
- **Keep Both** — dismiss the flag (remembered, won't flag again)
- **Merge** — choose which item to keep, the other is deleted
  
---

## 📥 Import & Export

### Import Sources

| Source | Method | Details |
|--------|--------|---------|
| **GitHub Stars** | `curator import github --user NAME` or Web UI | Fetches via GitHub API with pagination. Includes stars count, topics, language, license. Supports `--token` for private stars. Incremental sync (only new stars). |
| **Safari** | `curator import safari` or Web UI | Parses `~/Library/Safari/Bookmarks.plist`. Folder names become tags. |
| **Netscape HTML** | `curator import html FILE` or drag-and-drop in Web UI | Universal format exported by Chrome, Firefox, Edge, etc. |
| **JSON** | `curator import json FILE` or file upload | Array of `{url, title, description, tags, ...}` |
| **CSV** | File upload | Headers: `url, title, description, item_type, tags, notes, ...` |

### Export Formats

| Format | Output |
|--------|--------|
| **JSON** | Full data dump with all fields, tags, and metadata |
| **CSV** | Flat table for spreadsheets |
| **Netscape HTML** | Re-importable to any browser or bookmark manager |

All imports run **duplicate detection** — no silent overwrites.

---

## 📝 Notes & Highlights

### Notes
Every item has a **Notes** field that supports free-form text. Notes are stored as-is and are searchable via full-text search.

### Highlights  
You can add **highlighted excerpts** to any item — a quoted passage plus your annotation. Useful for remembering why you saved something or tracking key insights.

Both are accessible in the **Item Detail** view.

---

## ⚙️ Configuration

### Config File

Located at `~/Library/Application Support/Curator/config.json`:

```json
{
  "ai": {
    "enabled": true,
    "providers": [
      {
        "name": "openai",
        "model": "gpt-4o-mini",
        "api_key": "sk-...",
        "priority": 1,
        "timeout": 15
      },
      {
        "name": "gemini",
        "model": "gemini-2.5-flash",
        "api_key": "AIza...",
        "priority": 2,
        "timeout": 15
      },
      {
        "name": "ollama",
        "model": "llama3.2",
        "api_base": "http://localhost:11434",
        "priority": 3,
        "timeout": 30
      }
    ],
    "embedding": {
      "prefer_local": true,
      "local_model": "sentence-transformers/all-MiniLM-L6-v2"
    }
  },
  "general": {
    "theme": "dark",
    "auto_tag_on_add": true,
    "auto_embed_on_add": true,
    "auto_dedupe_on_add": true
  },
  "github": {
    "username": "your-username",
    "token": "ghp_...",
    "last_sync": null
  },
  "duplicate_detection": {
    "title_threshold": 0.85,
    "semantic_threshold": 0.90
  }
}
```

All settings are also editable via the web UI **Settings** page.

### Data Storage

| Path | Contents |
|------|----------|
| `~/Library/Application Support/Curator/curator.db` | SQLite database (all items, tags, highlights, duplicates, FTS index, vector embeddings) |
| `~/Library/Application Support/Curator/config.json` | Configuration |
| `~/Library/Application Support/Curator/logs/` | Server logs |
| `~/Library/Application Support/Curator/curator.pid` | PID of running server |

---

## 📦 Data Model

### Item Types

| Type | Description | Example |
|------|-------------|---------|
| `repo` | Git repository | GitHub/GitLab repos |
| `website` | General website | Reference pages, tools |
| `blog` | Blog post or article | Medium, dev.to, personal blogs |
| `course` | Online course | Coursera, Udemy, egghead |
| `textbook` | Book or manual | O'Reilly, textbooks |
| `document` | Paper or document | arXiv, whitepapers |
| `note` | Personal note (no URL) | Ideas, reminders |
| `snippet` | Code snippet | Useful code fragments |

### Item Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Auto-incrementing ID |
| `url` | string? | URL (null for notes/snippets) |
| `title` | string | Item title |
| `description` | string | Auto-extracted or user-provided |
| `item_type` | enum | One of the types above |
| `source` | enum | `github`, `safari`, `manual`, `import` |
| `difficulty` | enum? | `beginner`, `intermediate`, `advanced` |
| `language` | string? | Programming or content language |
| `author` | string? | Author or organization |
| `created_at` | ISO 8601 | When added to Curator |
| `updated_at` | ISO 8601 | Last modified |
| `starred_at` | ISO 8601? | Original star/save date |
| `metadata` | JSON | Type-specific extra data |
| `notes` | text | User's personal notes |
| `tags` | array | List of `{tag, source}` |
| `highlights` | array | List of `{text, annotation, color}` |
| `archived` | bool | Soft-delete (hidden from default views) |
| `has_embedding` | bool | Whether vector embedding exists |

### Tag Sources

| Source | Meaning |
|--------|---------|
| `user` | Manually added by you |
| `ai` | Generated by AI auto-tagger |
| `rule` | Generated by rule-based fallback |
| `import` | Came from an import source |

---

## 🛠 Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Language | Python 3.12+ | Rich AI/ML ecosystem, async support |
| Package Manager | `uv` | Fast, reliable, no pip quirks |
| Web Framework | FastAPI | Async, fast, auto-docs at `/docs` |
| Database | SQLite (WAL mode) | Zero-config, single file, portable |
| Full-Text Search | SQLite FTS5 | Built-in, BM25 ranking, zero overhead |
| Vector Search | sqlite-vec | Embeds in same DB file, SIMD-accelerated |
| Local Embeddings | fastembed (ONNX) | 80 MB model, CPU-only, <100ms per item |
| AI Integration | httpx (direct API calls) | No heavy litellm dependency |
| Frontend | Vanilla HTML/CSS/JS | No build step, no node_modules |
| CLI | click | Simple, well-documented |
| Auto-Start | macOS LaunchAgent | Native, zero Docker |

### Resource Footprint

| Resource | Amount |
|----------|--------|
| RAM (idle) | ~50 MB |
| RAM (embedding) | ~200 MB peak |
| Disk (app + deps) | ~150 MB |
| Disk (embedding model) | ~80 MB (downloaded on first use) |
| Disk (DB at 2,000 items) | ~10 MB |
| CPU (idle) | < 0.1% |

---

## 🗂 Project Structure

```
curator/
├── pyproject.toml              # Project config & dependencies
├── README.md                   # This file
├── src/curator/
│   ├── __init__.py             # Package init
│   ├── __main__.py             # CLI entry point (click commands)
│   ├── config.py               # Settings, paths, config management
│   ├── models.py               # Pydantic data models
│   ├── database.py             # SQLite schema, FTS5, sqlite-vec, CRUD
│   ├── server.py               # FastAPI app, lifespan, static serving
│   ├── api/
│   │   ├── items.py            # CRUD + tags + highlights + enrichment
│   │   ├── search.py           # Hybrid search endpoint
│   │   ├── duplicates.py       # Duplicate review & resolution
│   │   ├── imports.py          # GitHub/Safari/file imports
│   │   ├── exports.py          # JSON/CSV/HTML exports
│   │   └── settings.py         # Config, stats, bookmarklet
│   ├── services/
│   │   ├── ai_cascade.py       # Multi-provider AI with fallback
│   │   ├── embedder.py         # Local + API embedding generation
│   │   ├── tagger.py           # AI + rule-based auto-tagging
│   │   ├── searcher.py         # Hybrid FTS + vector search engine
│   │   ├── deduplicator.py     # 3-layer duplicate detection
│   │   ├── github_sync.py      # GitHub stars API client
│   │   └── importer.py         # Multi-format import/export
│   └── static/
│       ├── index.html          # SPA shell
│       ├── css/style.css       # Premium dark theme
│       └── js/app.js           # Frontend application
└── scripts/
    ├── install.sh              # One-time install + LaunchAgent setup
    ├── uninstall.sh            # Clean removal
    └── com.curator.app.plist   # LaunchAgent template
```

---

## 🔧 Troubleshooting

### Curator won't start

```bash
# Check if it's running
curator status

# Check logs
cat ~/Library/Application\ Support/Curator/logs/curator.err.log

# Restart manually
curator serve
```

### Port 7745 is in use

```bash
# Find what's using the port
lsof -i :7745

# Kill it
kill <PID>
```

### LaunchAgent not working

```bash
# Check if loaded
launchctl list | grep curator

# Reload
launchctl unload ~/Library/LaunchAgents/com.curator.app.plist
launchctl load ~/Library/LaunchAgents/com.curator.app.plist
```

### Database is locked

This shouldn't happen (WAL mode supports concurrent reads), but if it does:

```bash
# Stop Curator
curator stop

# Check for stale processes
ps aux | grep curator

# Restart
curator serve
```

### Embeddings not generating

1. Check if `fastembed` is installed: `uv run python -c "import fastembed; print('ok')"`
2. The model downloads on first use (~80 MB). Check internet and disk space.
3. Check logs for errors: `cat ~/Library/Application\ Support/Curator/logs/curator.err.log`

---

## 🗑 Uninstalling

### Quick Uninstall

```bash
bash scripts/uninstall.sh
```

This will:
1. Stop the background service
2. Remove the LaunchAgent (no more auto-start)
3. Ask whether to delete your data
4. Leave the source code for you to delete manually

### Manual Uninstall

```bash
# 1. Stop and unload the LaunchAgent
launchctl unload ~/Library/LaunchAgents/com.curator.app.plist
rm ~/Library/LaunchAgents/com.curator.app.plist

# 2. (Optional) Delete your data
rm -rf ~/Library/Application\ Support/Curator

# 3. Delete the project
rm -rf /path/to/curator
```

---

## 📜 License

This project is licensed under the Apache License, Version 2.0. See the [LICENSE.md](LICENSE.md) file for details.
