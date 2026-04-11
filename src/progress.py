"""Progress tracking for batch chapter processing."""
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import book_data_dir

logger = logging.getLogger(__name__)


def load_progress(book_slug: str) -> dict[str, Any]:
    """
    Load progress.json for the given book.

    Returns:
        Dict with chapter numbers as keys ("1", "2", ...) mapped to status strings
        ("done", "pending", "failed"), plus a "metadata" key.
        Returns empty dict if file does not exist.
    """
    path = book_data_dir(book_slug) / "progress.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    done_count = sum(1 for k, v in data.items() if k.isdigit() and v == "done")
    logger.info("Loaded progress for %s: %d chapters done", book_slug, done_count)
    return data


def save_progress(progress: dict[str, Any], book_slug: str) -> None:
    """
    Atomically write progress.json via temp + rename.

    Updates the "metadata.last_updated" timestamp before writing.
    """
    progress["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    data_dir = book_data_dir(book_slug)
    output_path = data_dir / "progress.json"

    fd, tmp_path = tempfile.mkstemp(suffix=".json", dir=str(data_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, output_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    logger.info("Progress saved for %s", book_slug)


def init_progress(book_slug: str, total_chapters: int) -> dict[str, Any]:
    """
    Create initial progress dict, preserving any existing "done" entries.

    Returns:
        Progress dict with all chapters marked "pending" except those
        already "done" in the existing progress file.
    """
    existing = load_progress(book_slug)
    progress: dict[str, Any] = {}
    for i in range(1, total_chapters + 1):
        key = str(i)
        status = existing.get(key, "pending")
        if status == "done":
            progress[key] = "done"
        else:
            progress[key] = "pending"
    progress["metadata"] = existing.get("metadata", {
        "book_slug": book_slug,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    })
    return progress


def init_progress_fresh(book_slug: str, total_chapters: int) -> dict[str, Any]:
    """Create fresh progress dict, ignoring existing completions."""
    progress: dict[str, Any] = {}
    for i in range(1, total_chapters + 1):
        progress[str(i)] = "pending"
    progress["metadata"] = {
        "book_slug": book_slug,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    return progress


def mark_done(progress: dict[str, Any], chapter_idx: int) -> None:
    """Mark a chapter as done in the progress dict."""
    progress[str(chapter_idx)] = "done"
