"""Cross-chapter glossary management for concept consistency."""
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from src.config import GLOSSARY_MAX_TOKENS, book_data_dir

logger = logging.getLogger(__name__)

# Rough token estimate: 1 token ~= 4 chars for English + Chinese mixed content
_CHARS_PER_TOKEN = 4


def load_glossary(book_slug: str) -> dict[str, dict[str, Any]]:
    """
    Load global_glossary.json.

    Returns:
        {"concept_name": {"definition": "...", "first_seen_chapter": N}, ...}
        Returns empty dict if file does not exist.
    """
    path = book_data_dir(book_slug) / "global_glossary.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    logger.info("Loaded glossary for %s: %d concepts", book_slug, len(data))
    return data


def save_glossary(glossary: dict[str, dict[str, Any]], book_slug: str) -> None:
    """Atomically write global_glossary.json via temp + rename."""
    data_dir = book_data_dir(book_slug)
    output_path = data_dir / "global_glossary.json"

    fd, tmp_path = tempfile.mkstemp(suffix=".json", dir=str(data_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(glossary, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, output_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    logger.info("Glossary saved for %s: %d concepts", book_slug, len(glossary))


def merge_concepts(
    glossary: dict[str, dict[str, Any]],
    concepts: list[dict[str, Any]],
    chapter_idx: int,
) -> dict[str, dict[str, Any]]:
    """
    Merge new concepts from ConceptAgent output into the glossary.

    Only adds concepts where is_new is True. Existing concepts are never overwritten.

    Args:
        glossary: Existing glossary dict (modified in place and returned)
        concepts: List of concept dicts from ConceptOutput.concepts (each has
                  name, definition, is_new fields)
        chapter_idx: Current chapter number

    Returns:
        The updated glossary dict (same object as input)
    """
    added = 0
    for concept in concepts:
        if concept.get("is_new", True) and concept["name"] not in glossary:
            glossary[concept["name"]] = {
                "definition": concept["definition"],
                "first_seen_chapter": chapter_idx,
            }
            added += 1
    logger.info(
        "Merged %d new concepts from Ch.%d (total: %d)",
        added, chapter_idx, len(glossary),
    )
    return glossary


def estimate_tokens(text: str) -> int:
    """Rough token count estimation."""
    return len(text) // _CHARS_PER_TOKEN


def trim_to_budget(glossary: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """
    Trim glossary to fit within GLOSSARY_MAX_TOKENS.

    Strategy: keep concepts from the most recent chapters first.
    Within the same chapter, keep all concepts (no partial chapter).

    Returns:
        New dict with concepts trimmed to budget. Does not modify input.
    """
    if not glossary:
        return glossary

    # Build chapter -> concepts mapping
    chapters: dict[int, list[tuple[str, dict]]] = {}
    for name, info in glossary.items():
        ch = info["first_seen_chapter"]
        chapters.setdefault(ch, []).append((name, info))

    # Process chapters from highest to lowest
    result: dict[str, dict[str, Any]] = {}
    for ch_num in sorted(chapters.keys(), reverse=True):
        # Add this chapter's concepts
        for name, info in chapters[ch_num]:
            result[name] = info
        # Check budget
        text = to_prompt_text(result)
        if estimate_tokens(text) > GLOSSARY_MAX_TOKENS:
            # This chapter pushed us over — remove it and stop
            for name, _ in chapters[ch_num]:
                result.pop(name, None)
            break

    logger.info(
        "Trimmed glossary from %d to %d concepts (~%d tokens)",
        len(glossary), len(result), estimate_tokens(to_prompt_text(result)),
    )
    return result


def to_prompt_text(glossary: dict[str, dict[str, Any]]) -> str:
    """
    Format glossary as text for token estimation.

    Format matches ConceptAgent's expected input:
    "- {name}：{definition}（首见 Ch.{N}）"
    """
    if not glossary:
        return ""
    lines = []
    for name, info in glossary.items():
        lines.append(
            f"- {name}\uff1a{info['definition']}\uff08\u9996\u89c1 Ch.{info['first_seen_chapter']}\uff09"
        )
    return "\n".join(lines)
