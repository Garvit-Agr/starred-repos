"""Configuration management for Curator."""

from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _default_data_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Curator"
    if system == "Linux":
        return Path.home() / ".local" / "share" / "curator"
    # Windows fallback
    return Path.home() / ".curator"


DATA_DIR = Path(
    __import__("os").environ.get("CURATOR_DATA_DIR", str(_default_data_dir()))
)
DB_PATH = DATA_DIR / "curator.db"
CONFIG_PATH = DATA_DIR / "config.json"
LOG_DIR = DATA_DIR / "logs"

STATIC_DIR = Path(__file__).parent / "static"

HOST = "127.0.0.1"
PORT = 7745
PID_FILE = DATA_DIR / "curator.pid"

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict[str, Any] = {
    "ai": {
        "enabled": True,
        "providers": [],  # list of {name, model, api_key, api_base, priority, timeout}
        "embedding": {
            "prefer_local": True,
            "local_model": "sentence-transformers/all-MiniLM-L6-v2",
        },
    },
    "general": {
        "theme": "dark",
        "items_per_page": 50,
        "auto_tag_on_add": True,
        "auto_embed_on_add": True,
        "auto_dedupe_on_add": True,
    },
    "github": {
        "username": "",
        "token": "",
        "last_sync": None,
    },
    "duplicate_detection": {
        "url_exact": True,
        "title_threshold": 0.85,
        "semantic_threshold": 0.90,
    },
}

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def ensure_dirs() -> None:
    """Create all required directories."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    """Load config from disk, merging with defaults."""
    ensure_dirs()
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            user_cfg = json.load(f)
        return _deep_merge(DEFAULT_CONFIG, user_cfg)
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict[str, Any]) -> None:
    """Persist config to disk."""
    ensure_dirs()
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2, default=str)


def get_ai_providers(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Return AI providers sorted by priority."""
    providers = cfg.get("ai", {}).get("providers", [])
    return sorted(providers, key=lambda p: p.get("priority", 99))


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result
