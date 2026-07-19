"""Regression guard for OpenAPI tag reconciliation (task t_1db19911).

Ensures that logically-single domains are NOT split across two OpenAPI tags,
which would cause the SDK generator (openapi-typescript-codegen) to emit
duplicate services (e.g. FileService + FilesService).

This test inspects the LIVE FastAPI app's generated schema in-memory only.
It never writes or regenerates the committed openapi.json.
"""
import os

# Guard import-time client construction (mirrors check_fe_be_contract.py).
os.environ.setdefault("OPENAI_API_KEY", "sk-test-guard")
os.environ.setdefault("OTLP_ENDPOINT", "")
os.environ.setdefault("SANDBOXD_AUTH_TOKEN", "")

import pytest
from fastapi.testclient import TestClient

from app.main_fastapi import app


def _collect_tagged_paths(schema: dict) -> dict[str, set[str]]:
    """Map each tag -> set of path strings carrying that tag."""
    by_tag: dict[str, set[str]] = {}
    for path, methods in schema.get("paths", {}).items():
        for op in methods.values():
            if not isinstance(op, dict):
                continue
            for tag in op.get("tags", []):
                by_tag.setdefault(tag, set()).add(path)
    return by_tag


@pytest.fixture(scope="module")
def schema():
    # app.openapi() is cached + resilient; safe to call without a DB.
    return app.openapi()


def test_file_domain_has_single_canonical_tag(schema):
    """The file domain must appear under exactly ONE tag ('file'), not
    split across 'file' and 'files'."""
    by_tag = _collect_tagged_paths(schema)

    file_tag_paths = by_tag.get("file", set())
    files_tag_paths = by_tag.get("files", set())

    assert file_tag_paths, "expected at least one path tagged 'file'"
    assert not files_tag_paths, (
        f"file domain is split across tags: 'files' tag still carries "
        f"{len(files_tag_paths)} path(s): {sorted(files_tag_paths)}. "
        "Both /file and /files routers must share the single 'file' tag "
        "(see backend/app/api/v1/file.py)."
    )


def test_no_orphaned_tenant_tags(schema):
    """Sanity guard: the backend must not expose a 'tenant' / 'tenants' tag
    split. If tenant routes ever return, they must use one canonical tag.

    NOTE: as of t_1db19911 the backend has NO tenant router at all; the
    frontend TenantService.ts / TenantsService.ts are orphaned SDK artifacts
    from a stale spec. This assertion documents that there is no backend-side
    tag duplication to reconcile for tenant.
    """
    by_tag = _collect_tagged_paths(schema)
    assert "tenant" not in by_tag, f"unexpected 'tenant' tag: {sorted(by_tag['tenant'])}"
    assert "tenants" not in by_tag, f"unexpected 'tenants' tag: {sorted(by_tag['tenants'])}"
