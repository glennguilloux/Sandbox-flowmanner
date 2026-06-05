"""Parse agent definition .md files from the agent_definitions/ directory.

Each agent file has YAML frontmatter (between --- delimiters) followed by
markdown content that serves as the system prompt.

Frontmatter fields: name, description, color (hex), emoji, vibe
Derived fields: slug (from filename), division (from parent directory)
"""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

AGENT_DEFINITIONS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "agent_definitions"
)


def parse_agent_file(file_path: Path) -> dict | None:
    """Parse a single agent .md file into a structured dict.

    Returns None if the file cannot be parsed.
    """
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Cannot read %s: %s", file_path, exc)
        return None

    text = text.strip()
    if not text.startswith("---"):
        logger.warning("Skipping %s: no YAML frontmatter", file_path.name)
        return None

    parts = text.split("---", 2)
    if len(parts) < 3:
        logger.warning("Skipping %s: malformed frontmatter", file_path.name)
        return None

    yaml_text = parts[1].strip()
    markdown_body = parts[2].strip()

    try:
        meta = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        logger.warning("Skipping %s: YAML parse error: %s", file_path.name, exc)
        return None

    if not isinstance(meta, dict):
        logger.warning("Skipping %s: frontmatter is not a dict", file_path.name)
        return None

    name = meta.get("name")
    if not name:
        logger.warning("Skipping %s: missing 'name' in frontmatter", file_path.name)
        return None

    slug = file_path.stem
    division = file_path.parent.name

    return {
        "name": str(name).strip(),
        "description": str(meta.get("description", "")).strip(),
        "color": str(meta.get("color", "#6B7280")).strip(),
        "emoji": str(meta.get("emoji", "")).strip(),
        "vibe": str(meta.get("vibe", "")).strip(),
        "slug": slug,
        "division": division,
        "system_prompt": markdown_body,
    }


def load_all_agents(definitions_dir: Path | None = None) -> list[dict]:
    """Walk the definitions directory and parse every .md file.

    Returns a list of successfully parsed agent dicts.
    """
    base_dir = definitions_dir or AGENT_DEFINITIONS_DIR

    if not base_dir.is_dir():
        logger.error("Agent definitions directory not found: %s", base_dir)
        return []

    agents: list[dict] = []
    errors = 0

    for md_file in sorted(base_dir.rglob("*.md")):
        parsed = parse_agent_file(md_file)
        if parsed is not None:
            agents.append(parsed)
        else:
            errors += 1

    logger.info(
        "Loaded %d agent definitions from %s (%d parse errors)",
        len(agents),
        base_dir,
        errors,
    )
    return agents
