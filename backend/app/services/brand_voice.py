"""Brand Voice Enforcer — LLM-based style evaluation and rewriting.

Evaluates text against a named style guide and optionally rewrites it
to conform.  Uses ModelRouter for LLM calls with a rule-based fallback
when no LLM is configured.

Style guides are stored in Redis as JSON (keyed by ``style_guide:{id}``).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Result types ──────────────────────────────────────────────────────


@dataclass
class StyleIssue:
    type: str
    excerpt: str
    suggestion: str


@dataclass
class EvaluationResult:
    score: int  # 0-100
    issues: list[StyleIssue] = field(default_factory=list)
    passed: bool = False


@dataclass
class RewriteResult:
    rewritten_text: str
    changes_made: int = 0


# ── Redis helpers ─────────────────────────────────────────────────────

_REDIS_KEY_PREFIX = "style_guide:"
_REDIS_TTL = 86400 * 30  # 30 days


async def _get_redis():
    """Return an async Redis client, or None if unavailable."""
    try:
        from redis.asyncio import Redis

        from app.config import settings

        client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        await client.ping()
        return client
    except Exception:
        return None


async def get_style_guide(style_guide_id: str) -> dict | None:
    """Fetch a style guide from Redis."""
    redis = await _get_redis()
    if redis is None:
        return None
    try:
        raw = await redis.get(f"{_REDIS_KEY_PREFIX}{style_guide_id}")
        if raw:
            return json.loads(raw)
    except Exception:
        logger.debug("Failed to fetch style guide %s", style_guide_id, exc_info=True)
    finally:
        await redis.aclose()
    return None


async def save_style_guide(style_guide_id: str, guide: dict) -> None:
    """Store a style guide in Redis."""
    redis = await _get_redis()
    if redis is None:
        return
    try:
        await redis.setex(
            f"{_REDIS_KEY_PREFIX}{style_guide_id}",
            _REDIS_TTL,
            json.dumps(guide),
        )
    except Exception:
        logger.debug("Failed to save style guide %s", style_guide_id, exc_info=True)
    finally:
        await redis.aclose()


# ── Rule-based fallback ──────────────────────────────────────────────

_PASSIVE_RE = re.compile(
    r"\b(?:is|are|was|were|be|been|being)\s+\w+(?:ed|en)\b",
    re.IGNORECASE,
)
_BANNED_DEFAULT = {"synergy", "leverage", "paradigm", "disrupt", "pivot", "bandwidth"}


def _estimate_reading_level(text: str) -> float:
    """Flesch-Kincaid grade level estimate."""
    sentences = max(len(re.split(r"[.!?]+", text)), 1)
    words = text.split()
    syllables = sum(_count_syllables(w) for w in words)
    n = max(len(words), 1)
    return 0.39 * (n / sentences) + 11.8 * (syllables / n) - 15.59


def _count_syllables(word: str) -> int:
    word = word.lower().strip(".,;:!?")
    if len(word) <= 3:
        return 1
    count = len(re.findall(r"[aeiouy]+", word))
    if word.endswith("e"):
        count -= 1
    return max(count, 1)


def _rule_evaluate(text: str, style_guide: dict | None) -> EvaluationResult:
    """Evaluate text using deterministic rules (no LLM needed)."""
    issues: list[StyleIssue] = []
    score = 100

    # Passive voice
    passive_matches = _PASSIVE_RE.findall(text)
    if len(passive_matches) > 2:
        score -= min(len(passive_matches) * 5, 25)
        issues.append(
            StyleIssue(
                type="passive_voice",
                excerpt=f"{len(passive_matches)} passive constructions detected",
                suggestion="Rewrite in active voice for clarity and impact",
            )
        )

    # Reading level
    level = _estimate_reading_level(text)
    max_level = (style_guide or {}).get("max_reading_level", 12)
    if level > max_level:
        score -= min(int((level - max_level) * 5), 20)
        issues.append(
            StyleIssue(
                type="reading_level",
                excerpt=f"Reading level ~{level:.1f} (target ≤{max_level})",
                suggestion="Use shorter sentences and simpler words",
            )
        )

    # Banned words
    banned = set((style_guide or {}).get("banned_words", _BANNED_DEFAULT))
    lower_text = text.lower()
    found_banned = [w for w in banned if w in lower_text]
    if found_banned:
        score -= min(len(found_banned) * 10, 30)
        issues.append(
            StyleIssue(
                type="banned_words",
                excerpt=f"Banned words found: {', '.join(found_banned)}",
                suggestion="Replace with plain-language alternatives",
            )
        )

    # Sentence length
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    long_sentences = [s for s in sentences if len(s.split()) > 35]
    if long_sentences:
        score -= min(len(long_sentences) * 5, 15)
        issues.append(
            StyleIssue(
                type="long_sentences",
                excerpt=f"{len(long_sentences)} sentence(s) exceed 35 words",
                suggestion="Break long sentences into shorter ones",
            )
        )

    score = max(score, 0)
    threshold = (style_guide or {}).get("pass_threshold", 80)
    return EvaluationResult(score=score, issues=issues, passed=score >= threshold)


# ── LLM-based evaluation ─────────────────────────────────────────────

_EVAL_SYSTEM_PROMPT = """You are a brand style auditor. Evaluate the given text against the style guide.
Return ONLY valid JSON with this structure:
{
  "score": <0-100>,
  "passed": <true|false>,
  "issues": [
    {"type": "<issue_type>", "excerpt": "<text excerpt>", "suggestion": "<improvement>"}
  ]
}"""

_REWRITE_SYSTEM_PROMPT = """You are a brand voice editor. Rewrite the given text to match the style guide.
Preserve the original meaning. Return ONLY valid JSON:
{
  "rewritten_text": "<the rewritten text>",
  "changes_made": <number of changes>
}"""


async def _llm_evaluate(text: str, style_guide: dict) -> EvaluationResult | None:
    """Use LLM to evaluate text against a style guide.  Returns None on failure."""
    try:
        from app.services.model_router import get_model_router

        router = get_model_router()
        guide_text = json.dumps(style_guide, indent=2)
        prompt = f"Style guide:\n{guide_text}\n\nText to evaluate:\n{text[:3000]}"

        response = await router.route_request(
            messages=[
                {"role": "system", "content": _EVAL_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            model_preference="deepseek-v4-flash",
            max_tokens=1000,
            temperature=0.1,
        )
        content = response.get("response", "")
        parsed = json.loads(content)
        issues = [
            StyleIssue(
                type=i["type"],
                excerpt=i.get("excerpt", ""),
                suggestion=i.get("suggestion", ""),
            )
            for i in parsed.get("issues", [])
        ]
        return EvaluationResult(
            score=int(parsed.get("score", 0)),
            issues=issues,
            passed=bool(parsed.get("passed", False)),
        )
    except Exception:
        logger.debug("LLM evaluation failed, falling back to rules", exc_info=True)
        return None


async def _llm_rewrite(text: str, style_guide: dict) -> RewriteResult | None:
    """Use LLM to rewrite text.  Returns None on failure."""
    try:
        from app.services.model_router import get_model_router

        router = get_model_router()
        guide_text = json.dumps(style_guide, indent=2)
        prompt = f"Style guide:\n{guide_text}\n\nText to rewrite:\n{text[:3000]}"

        response = await router.route_request(
            messages=[
                {"role": "system", "content": _REWRITE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            model_preference="deepseek-v4-flash",
            max_tokens=4000,
            temperature=0.3,
        )
        content = response.get("response", "")
        parsed = json.loads(content)
        return RewriteResult(
            rewritten_text=parsed.get("rewritten_text", text),
            changes_made=int(parsed.get("changes_made", 0)),
        )
    except Exception:
        logger.debug("LLM rewrite failed", exc_info=True)
        return None


# ── Public API ────────────────────────────────────────────────────────


async def evaluate_text(
    text: str,
    style_guide_id: str,
) -> EvaluationResult:
    """Evaluate *text* against the named style guide.

    Tries LLM evaluation first; falls back to rule-based checks.
    """
    style_guide = await get_style_guide(style_guide_id)

    # Try LLM
    llm_result = await _llm_evaluate(text, style_guide or {})
    if llm_result is not None:
        return llm_result

    # Fallback to rules
    return _rule_evaluate(text, style_guide)


async def rewrite_text(
    text: str,
    style_guide_id: str,
) -> RewriteResult:
    """Rewrite *text* to match the named style guide.

    Tries LLM rewrite first; falls back to returning the original text
    with 0 changes.
    """
    style_guide = await get_style_guide(style_guide_id)

    llm_result = await _llm_rewrite(text, style_guide or {})
    if llm_result is not None:
        return llm_result

    # Fallback: no rewrite capability without LLM
    return RewriteResult(rewritten_text=text, changes_made=0)
