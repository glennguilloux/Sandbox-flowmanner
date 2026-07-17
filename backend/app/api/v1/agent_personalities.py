"""Agent Personalities API — /api/agent-personalities.

Reads agent personality definitions from markdown files in
backend/app/agent_definitions/agent_personalities/ and serves them
via a REST API. Each personality has YAML-like frontmatter (name,
description, color, domain) followed by markdown body content.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-personalities", tags=["agent-personalities"])

# Resolve the agent_definitions directory relative to this file.
# Scan the entire tree (all 16 domain subdirs), not just agent_personalities/.
_DEFINITIONS_DIR = Path(__file__).resolve().parent.parent.parent / "agent_definitions"


# ---------------------------------------------------------------------------
# Frontmatter parser (no PyYAML dependency)
# ---------------------------------------------------------------------------


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse simple YAML-like frontmatter delimited by ``---``.

    Returns ``(metadata_dict, body_markdown)``.  Only supports flat
    ``key: value`` pairs (no nested structures) which is all we need
    for agent personality definitions.
    """
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    # parts[0] is empty (before first ---), parts[1] is FM block, parts[2] is body.
    _, fm_block, body = parts
    meta: dict[str, str] = {}
    for line in fm_block.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta, body.strip()


def _load_personality(filepath: Path) -> dict[str, str] | None:
    """Load a single agent personality from a markdown file.

    The *id* is the file's path relative to ``_DEFINITIONS_DIR`` (without the
    ``.md`` suffix), e.g. ``engineering/code-review-assistant`` or
    ``game-development/unity/unity-architect``.  The *domain* is the
    top-level domain directory (the first path segment), normalised to
    hyphens to match the frontend ``DOMAIN_LABELS`` keys.
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.warning("Could not read %s", filepath, exc_info=True)
        return None

    meta, body = _parse_frontmatter(text)

    rel_parts = filepath.relative_to(_DEFINITIONS_DIR).with_suffix("").parts
    domain_key = rel_parts[0].replace("_", "-")
    persona_id = "/".join(rel_parts)

    return {
        "id": persona_id,
        "domain": domain_key,
        "name": meta.get("name", rel_parts[-1].replace("-", " ").title()),
        "description": meta.get("description", ""),
        "color": meta.get("color", "gray"),
        "body": body,
    }


# Simple in-process cache (invalidated when module reloads).
_cached_personalities: list[dict[str, str]] | None = None
_cache_mtime: float = 0.0


def _load_all_personalities() -> list[dict[str, str]]:
    """Scan the whole definitions tree (all 16 domain subdirs, recursively)
    and load every personality.

    Results are cached per-process and refreshed when the definitions
    directory mtime changes (i.e. after a deploy or file edit).
    """
    global _cached_personalities, _cache_mtime

    if not _DEFINITIONS_DIR.is_dir():
        logger.warning("Agent definitions dir not found: %s", _DEFINITIONS_DIR)
        return []

    current_mtime = _DEFINITIONS_DIR.stat().st_mtime
    if _cached_personalities is not None and current_mtime == _cache_mtime:
        return _cached_personalities

    personalities: list[dict[str, str]] = []
    for md_file in sorted(_DEFINITIONS_DIR.rglob("*.md")):
        if md_file.parent.name.startswith(("_", ".")):
            continue
        entry = _load_personality(md_file)
        if entry:
            personalities.append(entry)

    _cached_personalities = personalities
    _cache_mtime = current_mtime
    return personalities


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_agent_personalities(domain: str | None = None, q: str | None = None):
    """Return all agent personalities across all domains.

    Optional filters:
      - ``domain``: restrict to a single domain (hyphenated key, e.g. ``engineering``).
      - ``q``: case-insensitive substring match against name/description.
    """
    personalities = _load_all_personalities()

    if domain is not None:
        personalities = [p for p in personalities if p["domain"] == domain]

    if q is not None:
        needle = q.lower()
        personalities = [
            p
            for p in personalities
            if needle in p["name"].lower() or needle in p["description"].lower()
        ]

    return personalities


@router.get("/{path:path}")
async def get_agent_personality(path: str):
    """Return a single agent personality by its id (domain/slug).

    The *path* is expected to be ``<domain>/<slug>`` where *domain*
    may use hyphens (``software-it``) matching the frontend's
    ``DOMAIN_LABELS`` keys.  The backend directory uses underscores
    (``software_it``), so we normalise automatically.
    """
    parts = path.strip("/").split("/", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Expected path format: <domain>/<slug>")

    domain_key, slug = parts  # domain_key uses hyphens from frontend

    # Normalise to directory name (hyphens → underscores).
    domain_dir = domain_key.replace("-", "_")
    domain_path = _DEFINITIONS_DIR / domain_dir

    md_file = domain_path / f"{slug}.md"
    if md_file.is_file():
        entry = _load_personality(md_file)
        if entry:
            return entry

    raise HTTPException(status_code=404, detail=f"Agent personality not found: {path}")
