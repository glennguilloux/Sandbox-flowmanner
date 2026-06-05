"""Blog & Case Studies API — reads markdown files with YAML frontmatter.

Provides:
- GET /blog/posts         — list posts (optional ?category=blog|case-study)
- GET /blog/posts/{slug}  — single post with full content
"""

import logging
from functools import lru_cache
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/blog", tags=["blog"])

CONTENT_ROOT = Path(__file__).resolve().parent.parent.parent / "content"
BLOG_DIR = CONTENT_ROOT / "blog"
CASE_STUDIES_DIR = CONTENT_ROOT / "case-studies"


def _parse_frontmatter(filepath: Path) -> dict:
    """Parse a markdown file with YAML frontmatter delimited by ---.

    Uses split("---", 2) so that horizontal rules (---) in the markdown
    body do not interfere with frontmatter extraction.
    """
    text = filepath.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {"content": text}

    parts = text.split("---", 2)
    if len(parts) < 2:
        return {"content": text}

    yaml_text = parts[1].strip()
    body = parts[2].strip() if len(parts) > 2 else ""

    try:
        meta = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as e:
        logger.warning(f"Invalid frontmatter in {filepath}: {e}")
        meta = {}

    # safe_load may return a non-dict (list, str, etc.) — guard against that
    if not isinstance(meta, dict):
        logger.warning(f"Frontmatter in {filepath} parsed to non-dict: {type(meta)}")
        meta = {}

    meta["content"] = body
    return meta


def _normalize_post(post: dict, directory: Path, fpath: Path) -> dict:
    """Apply defaults and normalize a parsed post dict."""
    post.setdefault("slug", fpath.stem)
    post.setdefault("category", "blog" if "blog" in str(directory) else "case-study")
    post.setdefault("id", fpath.stem)
    # Generate tag slugs
    raw_tags = post.get("tags", [])
    if raw_tags:
        post["tags"] = [
            {"id": str(i + 1), "name": t, "slug": t.lower().replace(" ", "-")}
            for i, t in enumerate(raw_tags)
        ]
    return post


def _find_post_file(slug: str) -> Path | None:
    """Find a markdown file by slug in blog or case-studies directories."""
    for directory in (BLOG_DIR, CASE_STUDIES_DIR):
        candidate = directory / f"{slug}.md"
        if candidate.is_file():
            return candidate
    return None


@lru_cache(maxsize=1)
def _scan_posts_cached(category: str | None = None) -> list[dict]:
    """Scan content directories and return parsed posts (cached)."""
    posts: list[dict] = []

    dirs_to_scan = []
    if category is None or category == "blog":
        dirs_to_scan.append(BLOG_DIR)
    if category is None or category == "case-study":
        dirs_to_scan.append(CASE_STUDIES_DIR)

    for directory in dirs_to_scan:
        if not directory.is_dir():
            continue
        for fpath in sorted(directory.glob("*.md")):
            try:
                post = _parse_frontmatter(fpath)
                post = _normalize_post(post, directory, fpath)
                posts.append(post)
            except Exception as e:
                logger.warning(f"Failed to parse {fpath}: {e}")

    # Sort by published_at descending
    posts.sort(key=lambda p: p.get("published_at", ""), reverse=True)
    return posts


def _invalidate_cache():
    """Invalidate the scan cache. Call after content changes."""
    _scan_posts_cached.cache_clear()


@router.get("/posts")
async def list_posts(
    category: str | None = Query(None, description="Filter by category: 'blog' or 'case-study'"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List blog posts and/or case studies."""
    posts = _scan_posts_cached(category)
    total = len(posts)

    # Paginate
    page = posts[offset : offset + limit]

    # Strip content from listing (content is in detail endpoint)
    result = []
    for p in page:
        item = {k: v for k, v in p.items() if k != "content"}
        result.append(item)

    return {"posts": result, "total": total, "limit": limit, "offset": offset}


@router.get("/posts/{slug}")
async def get_post(slug: str):
    """Get a single post by slug (includes full content)."""
    fpath = _find_post_file(slug)
    if fpath is None:
        raise HTTPException(status_code=404, detail=f"Post '{slug}' not found")

    directory = fpath.parent
    post = _parse_frontmatter(fpath)
    post = _normalize_post(post, directory, fpath)
    return post
