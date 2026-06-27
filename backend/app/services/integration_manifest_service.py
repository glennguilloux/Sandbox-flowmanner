"""Integration Manifest Service — loads, validates, and caches integration manifests.

Manifests are JSON files in ``backend/integrations/manifests/`` that define the
metadata, capabilities, and health-check config for each first-party integration.
This service replaces the hardcoded ``AVAILABLE_INTEGRATIONS`` list in
``integrations.py`` behind the ``integration_manifests_v1`` feature flag.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Resolve the manifests directory relative to this file's location so it works
# both inside Docker (``/app/…``) and on the host (``/opt/flowmanner/backend/…``).
_DEFAULT_MANIFESTS_DIR = Path(__file__).resolve().parents[2] / "integrations" / "manifests"


class IntegrationManifestService:
    """Loads and validates integration manifests from JSON files.

    The service reads every ``*.json`` file in the manifests directory, validates
    it against the integration manifest schema, and caches the results in memory.
    Call ``load_all()`` to populate the cache; subsequent ``get()`` calls are
    cache hits with zero I/O.
    """

    def __init__(
        self,
        manifests_dir: str | Path | None = None,
        schema_path: str | Path | None = None,
    ) -> None:
        self._manifests_dir = Path(manifests_dir) if manifests_dir else _DEFAULT_MANIFESTS_DIR
        self._schema_path = (
            Path(schema_path)
            if schema_path
            else self._manifests_dir.parents[1] / "schemas" / "integration-manifest.json"
        )
        self._cache: dict[str, dict[str, Any]] = {}
        self._schema: dict[str, Any] | None = None
        self._loaded = False

    # ── Public API ──────────────────────────────────────────────────────

    def load_all(self) -> list[dict[str, Any]]:
        """Load all manifests, validate against schema, cache results.

        Returns a list of manifest dicts sorted by name.  If a manifest file
        fails validation it is skipped with a warning log; the remaining
        manifests are still returned.
        """
        if self._loaded:
            return sorted(self._cache.values(), key=lambda m: m["name"].lower())

        schema = self._get_schema()
        self._cache.clear()

        if not self._manifests_dir.is_dir():
            logger.warning("Manifests directory not found: %s", self._manifests_dir)
            self._loaded = True
            return []

        for path in sorted(self._manifests_dir.glob("*.json")):
            try:
                manifest = self._load_one(path, schema)
                self._cache[manifest["slug"]] = manifest
            except Exception as exc:
                logger.warning("Skipping invalid manifest %s: %s", path.name, exc)

        self._loaded = True
        logger.info("Loaded %d integration manifests from %s", len(self._cache), self._manifests_dir)
        return sorted(self._cache.values(), key=lambda m: m["name"].lower())

    def get(self, slug: str) -> dict[str, Any] | None:
        """Get a single integration manifest by slug.

        Returns ``None`` if the slug is not found.  Automatically loads all
        manifests on first call.
        """
        if not self._loaded:
            self.load_all()
        return self._cache.get(slug)

    def get_health_check(self, slug: str) -> dict[str, Any] | None:
        """Get the health-check config for an integration.

        Returns ``None`` if the integration has no health check or doesn't exist.
        """
        manifest = self.get(slug)
        if manifest is None:
            return None
        return manifest.get("health_check")

    def get_all_health_checks(self) -> dict[str, dict[str, Any]]:
        """Return a dict mapping slug → health_check for all integrations."""
        if not self._loaded:
            self.load_all()
        return {slug: m["health_check"] for slug, m in self._cache.items() if "health_check" in m}

    def reload(self) -> list[dict[str, Any]]:
        """Force a reload of all manifests (clears cache first)."""
        self._loaded = False
        self._cache.clear()
        return self.load_all()

    @property
    def slug_list(self) -> list[str]:
        """Return sorted list of all loaded manifest slugs."""
        if not self._loaded:
            self.load_all()
        return sorted(self._cache.keys())

    # ── Internal helpers ────────────────────────────────────────────────

    def _get_schema(self) -> dict[str, Any] | None:
        """Load and cache the JSON schema file (if it exists)."""
        if self._schema is not None:
            return self._schema

        if self._schema_path.is_file():
            try:
                self._schema = json.loads(self._schema_path.read_text())
                logger.debug("Loaded manifest schema from %s", self._schema_path)
            except Exception as exc:
                logger.warning("Failed to load manifest schema: %s — validation disabled", exc)
                self._schema = None
        else:
            logger.debug("No schema file at %s — validation disabled", self._schema_path)
            self._schema = None

        return self._schema

    @staticmethod
    def _load_one(path: Path, schema: dict[str, Any] | None) -> dict[str, Any]:
        """Load and validate a single manifest file.

        If ``jsonschema`` is available and a schema was loaded, the manifest is
        validated.  Otherwise we rely on the required-field checks below.
        """
        raw = json.loads(path.read_text())

        # ── Validate with jsonschema if available ────────────────────────
        if schema is not None:
            try:
                import jsonschema

                jsonschema.validate(raw, schema)
            except ImportError:
                logger.debug("jsonschema not installed — falling back to basic validation")
                _basic_validate(raw)
            except jsonschema.ValidationError as exc:
                raise ValueError(f"Schema validation failed: {exc.message}") from exc
        else:
            _basic_validate(raw)

        # Ensure defaults for optional fields
        raw.setdefault("icon_url", "")
        raw.setdefault("trust_level", "verified")
        raw.setdefault("version", "1.0.0")
        raw.setdefault("docs_url", "")
        raw.setdefault("playground", {"enabled": False, "demo_actions": []})

        return raw


def _basic_validate(manifest: dict[str, Any]) -> None:
    """Minimal validation when jsonschema is not installed."""
    required = ["slug", "name", "description", "category", "auth_type", "capabilities", "health_check"]
    missing = [f for f in required if f not in manifest]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")

    valid_categories = {"communication", "development", "productivity", "storage", "automation"}
    if manifest["category"] not in valid_categories:
        raise ValueError(f"Invalid category: {manifest['category']}")

    valid_auth = {"oauth2", "api_key", "bot_token"}
    if manifest["auth_type"] not in valid_auth:
        raise ValueError(f"Invalid auth_type: {manifest['auth_type']}")

    if not isinstance(manifest["capabilities"], list):
        raise ValueError("capabilities must be a list")

    hc = manifest["health_check"]
    if not isinstance(hc, dict) or "endpoint" not in hc or "method" not in hc:
        raise ValueError("health_check must have 'endpoint' and 'method'")


# ── Module-level singleton ─────────────────────────────────────────────────

manifest_service = IntegrationManifestService()
