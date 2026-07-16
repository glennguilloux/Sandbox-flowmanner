"""Regression test for G-4: ControlFlowAgent approval endpoint authz.

The POST /governance/agents/{session_id}/approval endpoint (app/api/v1/
governance.py) is UN-WIRED SCAFFOLDING (the real gate is the HITL inbox),
but if it is ever wired it MUST fail closed: only the session owner or an
admin may record a decision. A non-owner non-admin caller must get 403.

These tests assert the authz guard only (the callback is not the live gate).
They fail before the guard is added (any authenticated user was allowed) and
pass after.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock


class FakeAgent:
    """Stand-in for ControlFlowAgent in the approval endpoint path.

    Implements only what resolve_agent_approval touches: ``_load_state``
    (to discover the session owner) and ``resolve_approval`` (the callback).
    """

    def __init__(self, owner_id):
        # None => no session state found (owner unknown)
        self._owner_id = owner_id
        self.last_resolve = None

    def _load_state(self, session_id):
        if self._owner_id is None:
            return None
        return {
            "session_id": session_id,
            "user_id": self._owner_id,
            "awaiting_approval": True,
            "pending_tools": [],
            "tool_history": [],
            "messages": [],
            "current_message": "",
            "current_approval_request": None,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "auto_approve_safe_tools": True,
            "require_approval_for_all": False,
            "context": {},
        }

    async def resolve_approval(
        self,
        *,
        session_id,
        decision,
        approved_by,
        tool_index=None,
        owner_id=None,
    ):
        self.last_resolve = {
            "session_id": session_id,
            "decision": decision,
            "approved_by": approved_by,
            "tool_index": tool_index,
            "owner_id": owner_id,
        }
        return {"success": True, "decision": decision}


def _make_user(user_id, *, is_admin=False, is_superuser=False):
    return MagicMock(
        id=user_id,
        is_active=True,
        is_admin=is_admin,
        is_superuser=is_superuser,
        role="admin" if is_admin else "user",
    )


@pytest.fixture
def client(monkeypatch):
    from app.api.v1 import governance as gov_mod
    from app.api.deps import get_current_user, get_db

    app = FastAPI()
    app.include_router(gov_mod.router, prefix="/api/v1")

    state = {"owner_id": None}

    def _get_agent():
        return FakeAgent(state["owner_id"])

    monkeypatch.setattr(gov_mod, "get_agent", _get_agent)

    async def override_db():
        yield MagicMock()

    def _install(user):
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_db] = override_db
        return app

    ctx = {"install": _install, "set_owner": lambda oid: state.__setitem__("owner_id", oid)}
    with TestClient(app) as c:
        yield c, ctx


def _request(c, session_id, decision="approved"):
    return c.post(
        f"/api/v1/governance/agents/{session_id}/approval",
        json={"decision": decision},
    )


def test_non_owner_non_admin_is_denied(client):
    c, ctx = client
    # Session owned by someone else; requester is a plain non-admin user.
    ctx["set_owner"](999)
    user = _make_user(1, is_admin=False, is_superuser=False)
    ctx["install"](user)

    resp = _request(c, "sess_x")
    assert resp.status_code == 403, resp.text


def test_owner_is_allowed(client):
    c, ctx = client
    ctx["set_owner"](1)  # session owned by requester id=1
    user = _make_user(1, is_admin=False, is_superuser=False)
    ctx["install"](user)

    resp = _request(c, "sess_x")
    assert resp.status_code == 200, resp.text
    # The callback was invoked with the owner passed through as owner_id.
    assert resp.json()["success"] is True


def test_admin_is_allowed_even_if_not_owner(client):
    c, ctx = client
    ctx["set_owner"](999)  # owned by someone else
    user = _make_user(1, is_admin=True, is_superuser=False)
    ctx["install"](user)

    resp = _request(c, "sess_x")
    assert resp.status_code == 200, resp.text


def test_unknown_session_fails_closed_for_non_admin(client):
    c, ctx = client
    # No session state -> owner unknown. A plain non-admin user cannot approve.
    ctx["set_owner"](None)
    user = _make_user(1, is_admin=False, is_superuser=False)
    ctx["install"](user)

    resp = _request(c, "sess_unknown")
    assert resp.status_code == 403, resp.text
