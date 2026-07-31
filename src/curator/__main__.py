"""Curator CLI — entry point for all commands."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import webbrowser

import click

from curator.config import (
    DATA_DIR, DB_PATH, HOST, LOG_DIR, PID_FILE, PORT, ensure_dirs, load_config, save_config,
)


@click.group()
def cli() -> None:
    """Curator — local-first personal knowledge & bookmark manager."""
    pass


@cli.command()
def init() -> None:
    """Initialise Curator (create data directory and database)."""
    ensure_dirs()
    # Load config to create default config.json
    cfg = load_config()
    save_config(cfg)
    click.echo(f"✓ Data directory: {DATA_DIR}")
    click.echo(f"✓ Config: {DATA_DIR / 'config.json'}")
    click.echo(f"✓ Run 'curator serve' to start, or run the install script for auto-start.")


@cli.command()
@click.option("--host", default=HOST, help="Bind host")
@click.option("--port", default=PORT, type=int, help="Bind port")
def serve(host: str, port: int) -> None:
    """Start the Curator web server."""
    ensure_dirs()
    # Write PID file
    PID_FILE.write_text(str(os.getpid()))

    click.echo(f"🚀 Curator starting at http://{host}:{port}")
    click.echo(f"   Data: {DATA_DIR}")
    click.echo(f"   Press Ctrl+C to stop\n")

    import uvicorn
    from curator.server import create_app

    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")

    # Clean up PID file on exit
    if PID_FILE.exists():
        PID_FILE.unlink()


@cli.command()
def stop() -> None:
    """Stop the background Curator server."""
    if not PID_FILE.exists():
        click.echo("Curator is not running (no PID file found).")
        return

    pid = int(PID_FILE.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        click.echo(f"✓ Curator (PID {pid}) stopped.")
        PID_FILE.unlink(missing_ok=True)
    except ProcessLookupError:
        click.echo(f"Process {pid} not found. Cleaning up stale PID file.")
        PID_FILE.unlink(missing_ok=True)
    except PermissionError:
        click.echo(f"Permission denied stopping PID {pid}. Try: kill {pid}")


@cli.command()
def status() -> None:
    """Check if Curator is running."""
    if not PID_FILE.exists():
        click.echo("● Curator is not running.")
        return

    pid = int(PID_FILE.read_text().strip())
    try:
        os.kill(pid, 0)  # Check if process exists
        click.echo(f"● Curator is running (PID {pid})")
        click.echo(f"  URL: http://{HOST}:{PORT}")
        click.echo(f"  Data: {DATA_DIR}")
    except ProcessLookupError:
        click.echo("● Curator is not running (stale PID file).")
        PID_FILE.unlink(missing_ok=True)


@cli.command(name="open")
def open_ui() -> None:
    """Open the Curator web UI in your browser."""
    url = f"http://{HOST}:{PORT}"
    click.echo(f"Opening {url} ...")
    webbrowser.open(url)


@cli.command()
@click.argument("url")
@click.option("--title", "-t", default=None, help="Item title")
@click.option("--type", "item_type", default="website", help="Item type")
@click.option("--tags", default="", help="Comma-separated tags")
@click.option("--notes", "-n", default="", help="Notes")
def add(url: str, title: str | None, item_type: str, tags: str, notes: str) -> None:
    """Quick-add an item from the command line."""
    import asyncio
    from curator import database as db

    async def _add():
        await db.init_db()
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        item_id = await db.create_item(
            url=url,
            title=title or url,
            item_type=item_type,
            tags=tag_list,
            notes=notes,
        )
        click.echo(f"✓ Added item #{item_id}: {title or url}")
        await db.close_db()

    asyncio.run(_add())


@cli.command(name="search")
@click.argument("query")
@click.option("--limit", "-l", default=10, help="Max results")
def search_cmd(query: str, limit: int) -> None:
    """Search items from the command line."""
    import asyncio
    from curator import database as db

    async def _search():
        await db.init_db()
        results = await db.fts_search(query, limit=limit)
        if not results:
            click.echo("No results found.")
            await db.close_db()
            return

        for r in results:
            item = await db.get_item(r["item_id"])
            if item:
                tags = ", ".join(t["tag"] for t in item.get("tags", []))
                click.echo(f"  [{item['id']}] {item['title']}")
                if item.get("url"):
                    click.echo(f"       {item['url']}")
                if tags:
                    click.echo(f"       Tags: {tags}")
                click.echo()

        await db.close_db()

    asyncio.run(_search())


@cli.group(name="import")
def import_group() -> None:
    """Import items from various sources."""
    pass


@import_group.command(name="github")
@click.option("--user", "-u", default=None, help="GitHub username")
@click.option("--token", "-t", default=None, help="GitHub personal access token")
def import_github(user: str | None, token: str | None) -> None:
    """Import starred repositories from GitHub."""
    import asyncio
    from curator import database as db
    from curator.services.github_sync import GitHubSyncService
    from curator.services.importer import import_items

    cfg = load_config()
    username = user or cfg.get("github", {}).get("username", "")
    gh_token = token or cfg.get("github", {}).get("token", "")

    if not username:
        click.echo("Error: GitHub username required. Use --user or set in config.")
        sys.exit(1)

    async def _import():
        await db.init_db()
        click.echo(f"Fetching stars for {username}...")
        sync = GitHubSyncService(username=username, token=gh_token)
        last_sync = cfg.get("github", {}).get("last_sync")
        raw_items = await sync.fetch_stars(since=last_sync)
        click.echo(f"Found {len(raw_items)} starred repos.")

        stats = await import_items(raw_items)
        click.echo(f"✓ Created: {stats['created']}, Skipped (duplicates): {stats['skipped']}")

        # Update last_sync
        from datetime import datetime, timezone
        cfg["github"]["last_sync"] = datetime.now(timezone.utc).isoformat()
        if user:
            cfg["github"]["username"] = user
        save_config(cfg)
        await db.close_db()

    asyncio.run(_import())


@import_group.command(name="safari")
def import_safari() -> None:
    """Import bookmarks from Safari."""
    import asyncio
    from curator import database as db
    from curator.services.importer import import_items, parse_safari_bookmarks

    async def _import():
        await db.init_db()
        click.echo("Parsing Safari bookmarks...")
        try:
            raw_items = parse_safari_bookmarks()
        except FileNotFoundError as e:
            click.echo(f"Error: {e}")
            await db.close_db()
            sys.exit(1)

        click.echo(f"Found {len(raw_items)} bookmarks.")
        stats = await import_items(raw_items)
        click.echo(f"✓ Created: {stats['created']}, Skipped: {stats['skipped']}")
        await db.close_db()

    asyncio.run(_import())


@import_group.command(name="html")
@click.argument("filepath")
def import_html(filepath: str) -> None:
    """Import from a Netscape bookmark HTML file."""
    import asyncio
    from pathlib import Path
    from curator import database as db
    from curator.services.importer import import_items, parse_netscape_html

    if not Path(filepath).exists():
        click.echo(f"Error: File not found: {filepath}")
        sys.exit(1)

    async def _import():
        await db.init_db()
        content = Path(filepath).read_text(errors="replace")
        raw_items = parse_netscape_html(content)
        click.echo(f"Found {len(raw_items)} bookmarks.")
        stats = await import_items(raw_items)
        click.echo(f"✓ Created: {stats['created']}, Skipped: {stats['skipped']}")
        await db.close_db()

    asyncio.run(_import())


@import_group.command(name="json")
@click.argument("filepath")
def import_json(filepath: str) -> None:
    """Import from a JSON file."""
    import asyncio
    from pathlib import Path
    from curator import database as db
    from curator.services.importer import import_items, parse_json_import

    if not Path(filepath).exists():
        click.echo(f"Error: File not found: {filepath}")
        sys.exit(1)

    async def _import():
        await db.init_db()
        content = Path(filepath).read_text(errors="replace")
        raw_items = parse_json_import(content)
        click.echo(f"Found {len(raw_items)} items.")
        stats = await import_items(raw_items)
        click.echo(f"✓ Created: {stats['created']}, Skipped: {stats['skipped']}")
        await db.close_db()

    asyncio.run(_import())


@cli.group(name="export")
def export_group() -> None:
    """Export items to various formats."""
    pass


@export_group.command(name="json")
@click.option("--output", "-o", default="curator-export.json", help="Output file")
def export_json(output: str) -> None:
    """Export all items as JSON."""
    import asyncio
    from pathlib import Path
    from curator import database as db
    from curator.services.importer import export_json as _export

    async def _run():
        await db.init_db()
        content = await _export()
        Path(output).write_text(content)
        click.echo(f"✓ Exported to {output}")
        await db.close_db()

    asyncio.run(_run())


@export_group.command(name="csv")
@click.option("--output", "-o", default="curator-export.csv", help="Output file")
def export_csv(output: str) -> None:
    """Export all items as CSV."""
    import asyncio
    from pathlib import Path
    from curator import database as db
    from curator.services.importer import export_csv as _export

    async def _run():
        await db.init_db()
        content = await _export()
        Path(output).write_text(content)
        click.echo(f"✓ Exported to {output}")
        await db.close_db()

    asyncio.run(_run())


@export_group.command(name="html")
@click.option("--output", "-o", default="curator-bookmarks.html", help="Output file")
def export_html(output: str) -> None:
    """Export as Netscape bookmark HTML."""
    import asyncio
    from pathlib import Path
    from curator import database as db
    from curator.services.importer import export_netscape_html

    async def _run():
        await db.init_db()
        content = await export_netscape_html()
        Path(output).write_text(content)
        click.echo(f"✓ Exported to {output}")
        await db.close_db()

    asyncio.run(_run())


if __name__ == "__main__":
    cli()
