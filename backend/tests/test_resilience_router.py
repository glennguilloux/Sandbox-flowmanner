"""HTTP-contract tests for the resilience router (v2 /mission-templates/...).

Mirrors test_critique_router.py: TestClient against the real FastAPI app with
get_current_user overridden, and ResilienceService PATCHED in the route module
so no live DB is required. Only the HTTP envelope + delegation contract is
asserted here; the subgraph-shaping logic is covered by test_resilience.py.
"""

from __future__ import annotations

import os
import uuid

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://flowmanner:REDACTED_DB_PASSWORD@127.0.0.1:5432/flowmanner",
)

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.v2 import resilience as resilience_module
from app.main_fastapi import app
from app.models.user import User


def _user() -> User:
    uid = uuid.uuid4().int % 900_000_000 + 100_000
    return User(
        id=uid,
        email=f"res-router-{uid}@test.flowmanner.example",
        username=f"res_router_{uid}",
        full_name="Res Router Test",
        hashed_password="x",
        is_active=True,
        role="free",
    )


def _client(user: User) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _preview_payload(gate="escalate"):
    return {"gate": gate, "approver_role": "oncall", "approval_timeout": 2, "escalation_policy": "escalate"}


def test_preview_returns_ok_envelope():
    user = _user()
    client = _client(user)
    fake = AsyncMock()
    fake.preview.return_value = {
        "found": True,
        "template_id": str(uuid.uuid4()),
        "template_name": "Demo",
        "resilience": {"applied": True, "gate": "escalate", "wrapped_nodes": 1},
        "plan": {"nodes": [], "edges": []},
    }
    with patch.object(resilience_module, "ResilienceService", return_value=fake):
        resp = client.post(
            f"/api/v2/mission-templates/{uuid.uuid4()}/resilience/preview",
            json=_preview_payload(),
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["found"] is True
    assert body["data"]["resilience"]["gate"] == "escalate"
    # preview must NOT have persisted a variant
    fake.apply_and_persist.assert_not_called()


def test_preview_404_when_template_missing():
    user = _user()
    client = _client(user)
    fake = AsyncMock()
    fake.preview.return_value = {"found": False}
    with patch.object(resilience_module, "ResilienceService", return_value=fake):
        resp = client.post(
            f"/api/v2/mission-templates/{uuid.uuid4()}/resilience/preview",
            json=_preview_payload(),
        )
    assert resp.status_code == 404


def test_apply_persists_variant():
    user = _user()
    client = _client(user)
    fake = AsyncMock()
    fake.apply_and_persist.return_value = {
        "found": True,
        "template_id": str(uuid.uuid4()),
        "variant_id": str(uuid.uuid4()),
        "variant_name": "Demo (resilient-escalate)",
        "resilience": {"applied": True, "gate": "escalate", "wrapped_nodes": 1},
    }
    with patch.object(resilience_module, "ResilienceService", return_value=fake):
        resp = client.post(
            f"/api/v2/mission-templates/{uuid.uuid4()}/resilience/apply",
            json=_preview_payload(),
        )
    assert resp.status_code == 200
    assert resp.json()["data"]["variant_id"] is not None
    fake.apply_and_persist.assert_awaited_once()


def test_invalid_gate_rejected_with_422():
    user = _user()
    client = _client(user)
    fake = AsyncMock()
    with patch.object(resilience_module, "ResilienceService", return_value=fake):
        resp = client.post(
            f"/api/v2/mission-templates/{uuid.uuid4()}/resilience/preview",
            json={"gate": "explode"},
        )
    assert resp.status_code == 422
