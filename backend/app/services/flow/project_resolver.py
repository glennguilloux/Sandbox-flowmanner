"""
Flowmanner Project Resolver - Slug Generation

Generates URL-safe slugs from goals for email routing.
Infers project names from goal content.

Slug format: {meaningful-words}-{random-suffix}
Example: "write-blog-post-ai-trends-a1b2c3"
"""

import logging
import re
import secrets

# Try to import unidecode for better slug generation
try:
    from unidecode import unidecode

    HAS_UNIDECODE = True
except ImportError:
    HAS_UNIDECODE = False

logger = logging.getLogger(__name__)


class ProjectResolver:
    """
    Generate slugs and infer project names from goals.

    Slugs are used for email routing:
    - run+slug@flowmanner.com routes to the project with that slug

    Project names are used for display purposes.
    """

    # Words to ignore when generating slugs
    STOP_WORDS = {
        "a",
        "an",
        "the",
        "for",
        "to",
        "and",
        "or",
        "in",
        "on",
        "at",
        "by",
        "with",
        "from",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "can",
        "need",
        "i",
        "me",
        "my",
        "we",
        "our",
        "you",
        "your",
        "he",
        "she",
        "it",
        "its",
        "they",
        "them",
        "their",
        "this",
        "that",
        "these",
        "those",
        "what",
        "which",
        "who",
        "whom",
        "how",
        "when",
        "where",
        "why",
        "not",
        "no",
        "yes",
        "please",
    }

    def generate_slug(self, goal: str, max_words: int = 5) -> str:
        """
        Generate a URL-safe slug from goal.

        Args:
            goal: The user's goal/objective
            max_words: Maximum meaningful words to include

        Returns:
            Slug like "write-blog-post-ai-trends-a1b2c3"
        """
        # Normalize unicode
        goal = unidecode(goal) if HAS_UNIDECODE else goal.encode("ascii", "ignore").decode("ascii")

        # Extract words
        words = re.findall(r"\b[a-zA-Z]+\b", goal.lower())

        # Filter out stop words and short words
        meaningful_words = [w for w in words if w not in self.STOP_WORDS and len(w) > 2][:max_words]

        if not meaningful_words:
            # Fallback if no meaningful words
            meaningful_words = ["project"]

        # Join with hyphens
        slug_base = "-".join(meaningful_words)

        # Sanitize
        slug_base = re.sub(r"[^a-z0-9-]", "", slug_base)
        slug_base = re.sub(r"-+", "-", slug_base).strip("-")

        # Limit length
        if len(slug_base) > 50:
            slug_base = slug_base[:50].rsplit("-", 1)[0]

        # Add random suffix for uniqueness
        suffix = secrets.token_hex(3)  # 6 characters

        slug = f"{slug_base}-{suffix}"

        logger.debug("Generated slug: %s from goal: %s...", slug, goal[:50])

        return slug

    def infer_name(self, goal: str, max_length: int = 100) -> str:
        """
        Infer project name from goal.

        Args:
            goal: The user's goal/objective
            max_length: Maximum name length

        Returns:
            Human-readable project name
        """
        # Take first sentence
        first_sentence = goal.split(".")[0].strip()

        # Remove leading/trailing quotes
        first_sentence = first_sentence.strip("\"'")

        # Capitalize first letter
        if first_sentence:
            first_sentence = first_sentence[0].upper() + first_sentence[1:]

        # Truncate if too long
        if len(first_sentence) > max_length:
            first_sentence = first_sentence[: max_length - 3] + "..."

        # Fallback if empty
        if not first_sentence:
            first_sentence = "New Project"

        logger.debug("Inferred name: %s...", first_sentence[:50])

        return first_sentence

    def extract_keywords(self, goal: str, max_keywords: int = 5) -> list:
        """
        Extract keywords from goal for search/tagging.

        Args:
            goal: The user's goal/objective
            max_keywords: Maximum keywords to return

        Returns:
            List of keywords
        """
        # Normalize
        goal = unidecode(goal) if HAS_UNIDECODE else goal.encode("ascii", "ignore").decode("ascii")

        # Extract words
        words = re.findall(r"\b[a-zA-Z]+\b", goal.lower())

        # Filter and sort by length (prefer longer, more specific words)
        keywords = sorted(
            [w for w in words if w not in self.STOP_WORDS and len(w) > 3],
            key=len,
            reverse=True,
        )[:max_keywords]

        return keywords

    def suggest_slug_variations(self, goal: str) -> list:
        """
        Suggest multiple slug variations for user to choose from.

        Args:
            goal: The user's goal/objective

        Returns:
            List of slug suggestions
        """
        variations = []

        for word_count in [3, 4, 5, 6]:
            slug = self.generate_slug(goal, max_words=word_count)
            # Remove the random suffix for display
            slug_base = "-".join(slug.split("-")[:-1])
            variations.append(slug_base)

        # Remove duplicates while preserving order
        seen = set()
        unique_variations = []
        for v in variations:
            if v not in seen:
                seen.add(v)
                unique_variations.append(v)

        return unique_variations[:4]
