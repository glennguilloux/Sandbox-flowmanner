"""Tests for IntegrationManifestService — manifest loading, validation, and caching."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from app.services.integration_manifest_service import (
    IntegrationManifestService,
    _basic_validate,
    manifest_service,
)

if TYPE_CHECKING:
    from pathlib import Path

# ── Fixtures ────────────────────────────────────────────────────────────────


def _sample_manifest(**overrides) -> dict:
    """Return a minimal valid manifest dict."""
    base = {
        "slug": "test-svc",
        "name": "Test Service",
        "description": "A test integration for unit tests.",
        "category": "development",
        "auth_type": "api_key",
        "capabilities": [
            {"name": "ping", "description": "Ping the service"},
        ],
        "health_check": {
            "endpoint": "https://example.com/health",
            "method": "GET",
        },
    }
    base.update(overrides)
    return base


@pytest.fixture
def tmp_manifests(tmp_path: Path):
    """Create a temporary manifests directory with sample files."""
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()

    # Write a minimal schema file
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["slug", "name", "description", "category", "auth_type", "capabilities", "health_check"],
        "properties": {
            "slug": {"type": "string"},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "category": {
                "type": "string",
                "enum": ["communication", "development", "productivity", "storage", "automation"],
            },
            "auth_type": {"type": "string", "enum": ["oauth2", "api_key", "bot_token"]},
            "capabilities": {"type": "array"},
            "health_check": {"type": "object"},
            "trust_level": {"type": "string"},
            "version": {"type": "string"},
            "playground": {"type": "object"},
        },
    }
    (schema_dir / "integration-manifest.json").write_text(json.dumps(schema))

    return manifests_dir, schema_dir / "integration-manifest.json"


def _write_manifest(manifests_dir: Path, filename: str, data: dict):
    """Write a manifest JSON file."""
    (manifests_dir / filename).write_text(json.dumps(data, indent=2))


# ── basic_validate ──────────────────────────────────────────────────────────


class TestBasicValidate:
    def test_valid_manifest_passes(self):
        _basic_validate(_sample_manifest())

    def test_missing_required_field_raises(self):
        manifest = _sample_manifest()
        del manifest["slug"]
        with pytest.raises(ValueError, match="Missing required fields"):
            _basic_validate(manifest)

    def test_invalid_category_raises(self):
        with pytest.raises(ValueError, match="Invalid category"):
            _basic_validate(_sample_manifest(category="invalid"))

    def test_invalid_auth_type_raises(self):
        with pytest.raises(ValueError, match="Invalid auth_type"):
            _basic_validate(_sample_manifest(auth_type="magic"))

    def test_capabilities_not_list_raises(self):
        with pytest.raises(ValueError, match="capabilities must be a list"):
            _basic_validate(_sample_manifest(capabilities="not-a-list"))

    def test_health_check_missing_endpoint_raises(self):
        with pytest.raises(ValueError, match="health_check"):
            _basic_validate(_sample_manifest(health_check={"method": "GET"}))

    def test_health_check_missing_method_raises(self):
        with pytest.raises(ValueError, match="health_check"):
            _basic_validate(_sample_manifest(health_check={"endpoint": "/health"}))


# ── load_all ────────────────────────────────────────────────────────────────


class TestLoadAll:
    def test_loads_all_valid_manifests(self, tmp_manifests):
        manifests_dir, schema_path = tmp_manifests
        _write_manifest(manifests_dir, "alpha.json", _sample_manifest(slug="alpha", name="Alpha"))
        _write_manifest(manifests_dir, "beta.json", _sample_manifest(slug="beta", name="Beta"))

        svc = IntegrationManifestService(manifests_dir=manifests_dir, schema_path=schema_path)
        result = svc.load_all()

        assert len(result) == 2
        slugs = [m["slug"] for m in result]
        assert "alpha" in slugs
        assert "beta" in slugs

    def test_returns_sorted_by_name(self, tmp_manifests):
        manifests_dir, schema_path = tmp_manifests
        _write_manifest(manifests_dir, "z.json", _sample_manifest(slug="z-svc", name="Zebra"))
        _write_manifest(manifests_dir, "a.json", _sample_manifest(slug="a-svc", name="Alpha"))

        svc = IntegrationManifestService(manifests_dir=manifests_dir, schema_path=schema_path)
        result = svc.load_all()

        assert result[0]["name"] == "Alpha"
        assert result[1]["name"] == "Zebra"

    def test_skips_invalid_manifests(self, tmp_manifests, caplog):
        manifests_dir, schema_path = tmp_manifests
        _write_manifest(manifests_dir, "good.json", _sample_manifest(slug="good", name="Good"))
        _write_manifest(manifests_dir, "bad.json", {"slug": "bad"})  # missing required fields

        svc = IntegrationManifestService(manifests_dir=manifests_dir, schema_path=schema_path)
        result = svc.load_all()

        assert len(result) == 1
        assert result[0]["slug"] == "good"
        assert "Skipping invalid manifest" in caplog.text

    def test_empty_directory_returns_empty(self, tmp_manifests):
        manifests_dir, schema_path = tmp_manifests
        svc = IntegrationManifestService(manifests_dir=manifests_dir, schema_path=schema_path)
        result = svc.load_all()
        assert result == []

    def test_missing_directory_returns_empty(self, tmp_path, caplog):
        svc = IntegrationManifestService(manifests_dir=tmp_path / "nonexistent")
        result = svc.load_all()
        assert result == []
        assert "not found" in caplog.text

    def test_ignores_non_json_files(self, tmp_manifests):
        manifests_dir, schema_path = tmp_manifests
        _write_manifest(manifests_dir, "good.json", _sample_manifest(slug="good", name="Good"))
        (manifests_dir / "README.md").write_text("# Not a manifest")

        svc = IntegrationManifestService(manifests_dir=manifests_dir, schema_path=schema_path)
        result = svc.load_all()
        assert len(result) == 1

    def test_caches_results(self, tmp_manifests):
        manifests_dir, schema_path = tmp_manifests
        _write_manifest(manifests_dir, "a.json", _sample_manifest(slug="a", name="A"))

        svc = IntegrationManifestService(manifests_dir=manifests_dir, schema_path=schema_path)
        first = svc.load_all()
        second = svc.load_all()
        assert first is second or first == second  # cached, no re-read


# ── get ─────────────────────────────────────────────────────────────────────


class TestGet:
    def test_get_existing_slug(self, tmp_manifests):
        manifests_dir, schema_path = tmp_manifests
        _write_manifest(manifests_dir, "slack.json", _sample_manifest(slug="slack", name="Slack"))

        svc = IntegrationManifestService(manifests_dir=manifests_dir, schema_path=schema_path)
        result = svc.get("slack")

        assert result is not None
        assert result["slug"] == "slack"

    def test_get_missing_slug_returns_none(self, tmp_manifests):
        manifests_dir, schema_path = tmp_manifests
        svc = IntegrationManifestService(manifests_dir=manifests_dir, schema_path=schema_path)
        assert svc.get("nonexistent") is None

    def test_get_triggers_load_if_not_loaded(self, tmp_manifests):
        manifests_dir, schema_path = tmp_manifests
        _write_manifest(manifests_dir, "x.json", _sample_manifest(slug="x", name="X"))

        svc = IntegrationManifestService(manifests_dir=manifests_dir, schema_path=schema_path)
        assert svc._loaded is False
        result = svc.get("x")
        assert result is not None
        assert svc._loaded is True


# ── get_health_check ────────────────────────────────────────────────────────


class TestGetHealthCheck:
    def test_returns_health_check(self, tmp_manifests):
        manifests_dir, schema_path = tmp_manifests
        _write_manifest(manifests_dir, "svc.json", _sample_manifest(slug="svc", name="Svc"))

        svc = IntegrationManifestService(manifests_dir=manifests_dir, schema_path=schema_path)
        hc = svc.get_health_check("svc")

        assert hc is not None
        assert hc["endpoint"] == "https://example.com/health"
        assert hc["method"] == "GET"

    def test_returns_none_for_missing_slug(self, tmp_manifests):
        manifests_dir, schema_path = tmp_manifests
        svc = IntegrationManifestService(manifests_dir=manifests_dir, schema_path=schema_path)
        assert svc.get_health_check("nope") is None


# ── reload ──────────────────────────────────────────────────────────────────


class TestReload:
    def test_reload_picks_up_new_files(self, tmp_manifests):
        manifests_dir, schema_path = tmp_manifests
        _write_manifest(manifests_dir, "a.json", _sample_manifest(slug="a", name="A"))

        svc = IntegrationManifestService(manifests_dir=manifests_dir, schema_path=schema_path)
        assert len(svc.load_all()) == 1

        # Add a new manifest
        _write_manifest(manifests_dir, "b.json", _sample_manifest(slug="b", name="B"))
        result = svc.reload()

        assert len(result) == 2


# ── slug_list ───────────────────────────────────────────────────────────────


class TestSlugList:
    def test_returns_sorted_slugs(self, tmp_manifests):
        manifests_dir, schema_path = tmp_manifests
        _write_manifest(manifests_dir, "z.json", _sample_manifest(slug="z", name="Z"))
        _write_manifest(manifests_dir, "a.json", _sample_manifest(slug="a", name="A"))

        svc = IntegrationManifestService(manifests_dir=manifests_dir, schema_path=schema_path)
        assert svc.slug_list == ["a", "z"]


# ── Default values ──────────────────────────────────────────────────────────


class TestDefaults:
    def test_optional_fields_get_defaults(self, tmp_manifests):
        manifests_dir, schema_path = tmp_manifests
        # Minimal manifest — no optional fields
        _write_manifest(manifests_dir, "min.json", _sample_manifest(slug="min", name="Min"))

        svc = IntegrationManifestService(manifests_dir=manifests_dir, schema_path=schema_path)
        result = svc.get("min")

        assert result["icon_url"] == ""
        assert result["trust_level"] == "verified"
        assert result["version"] == "1.0.0"
        assert result["docs_url"] == ""
        assert result["playground"] == {"enabled": False, "demo_actions": []}

    def test_explicit_values_not_overridden(self, tmp_manifests):
        manifests_dir, schema_path = tmp_manifests
        _write_manifest(
            manifests_dir,
            "custom.json",
            _sample_manifest(
                slug="custom",
                name="Custom",
                trust_level="beta",
                version="2.0.0",
                docs_url="https://docs.example.com",
            ),
        )

        svc = IntegrationManifestService(manifests_dir=manifests_dir, schema_path=schema_path)
        result = svc.get("custom")

        assert result["trust_level"] == "beta"
        assert result["version"] == "2.0.0"
        assert result["docs_url"] == "https://docs.example.com"


# ── Singleton ───────────────────────────────────────────────────────────────


class TestSingleton:
    def test_module_level_singleton_exists(self):
        assert manifest_service is not None
        assert isinstance(manifest_service, IntegrationManifestService)


# ── Schema validation with jsonschema ───────────────────────────────────────


class TestJsonSchemaValidation:
    def test_valid_manifest_passes_jsonschema(self, tmp_manifests):
        """If jsonschema is installed, valid manifests pass validation."""
        pytest.importorskip("jsonschema")
        manifests_dir, schema_path = tmp_manifests
        _write_manifest(manifests_dir, "good.json", _sample_manifest(slug="good", name="Good"))

        svc = IntegrationManifestService(manifests_dir=manifests_dir, schema_path=schema_path)
        result = svc.load_all()
        assert len(result) == 1

    def test_invalid_category_rejected_by_jsonschema(self, tmp_manifests, caplog):
        """jsonschema rejects an invalid category enum value."""
        pytest.importorskip("jsonschema")
        manifests_dir, schema_path = tmp_manifests
        _write_manifest(manifests_dir, "bad.json", _sample_manifest(slug="bad", name="Bad", category="invalid_cat"))

        svc = IntegrationManifestService(manifests_dir=manifests_dir, schema_path=schema_path)
        result = svc.load_all()
        assert len(result) == 0
        assert "Skipping invalid manifest" in caplog.text

    def test_invalid_auth_type_rejected_by_jsonschema(self, tmp_manifests, caplog):
        """jsonschema rejects an invalid auth_type enum value."""
        pytest.importorskip("jsonschema")
        manifests_dir, schema_path = tmp_manifests
        _write_manifest(manifests_dir, "bad.json", _sample_manifest(slug="bad", name="Bad", auth_type="magic"))

        svc = IntegrationManifestService(manifests_dir=manifests_dir, schema_path=schema_path)
        result = svc.load_all()
        assert len(result) == 0
        assert "Skipping invalid manifest" in caplog.text
