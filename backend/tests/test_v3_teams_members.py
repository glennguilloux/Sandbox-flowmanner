"""Tests for v3 Team Member management endpoints.

Mirrors the mock-DB pattern used by other v3 unit tests: the app's
``get_db`` is overridden with ``mock_db_session`` (a MagicMock-backed async
session), and ``get_current_user`` with ``sample_user``. Each handler performs
a deterministic sequence of ``db.execute`` calls, which we replay by returning
pre-built result mocks via ``AsyncMock(side_effect=[...])``.

Call order per endpoint (flag gate first):
  GET    /teams/{id}/members            -> flag, team, membership, members
  POST   /teams/{id}/members            -> flag, team, membership, user, dup
  DELETE /teams/{id}/members/{uid}      -> flag, team, membership, member
  PATCH  /teams/{id}                    -> flag, team, membership
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

WS_ID = "ws-1"
WS_UUID = "11111111-1111-1111-1111-111111111111"  # 36-char, satisfies TeamCreateRequest.workspace_id
TEAM_ID = "team-1"
ADMIN_USER_ID = 1
MEMBER_USER_ID = 2
OTHER_USER_ID = 3


def _result(entity: object | None) -> MagicMock:
    """A DB result mock whose scalar / scalar_one_or_none return ``entity``."""
    r = MagicMock()
    r.scalar.return_value = entity
    r.scalar_one_or_none.return_value = entity
    return r


def _flag(on: bool) -> MagicMock:
    return _result(on)


def _team() -> MagicMock:
    t = MagicMock()
    t.id = TEAM_ID
    t.workspace_id = WS_ID
    t.name = "Design Guild"
    t.description = "Original description"
    t.created_at = "2026-01-01T00:00:00Z"
    return _result(t)


def _membership(role: str) -> MagicMock:
    m = MagicMock()
    m.role = role
    return _result(m)


def _member(user_id: int) -> MagicMock:
    m = MagicMock()
    m.user_id = user_id
    m.role = "member"
    m.joined_at = "2026-01-02T00:00:00Z"
    return m


def _team_obj() -> MagicMock:
    t = MagicMock()
    t.id = TEAM_ID
    t.workspace_id = WS_ID
    t.name = "Design Guild"
    t.description = "Original description"
    t.created_at = "2026-01-01T00:00:00Z"
    return t


def _user(user_id: int) -> MagicMock:
    u = MagicMock()
    u.id = user_id
    return _result(u)


def _set_side_effects(session, results):
    """Replay ``results`` for every ``db.execute`` call in order."""
    session.execute = AsyncMock(side_effect=results)


# ── Feature flag off → 404 ──────────────────────────────────────────────────


class TestFlagOff:
    def test_list_returns_404(self, v3_client, mock_db_session):
        _set_side_effects(mock_db_session, [_flag(False)])
        resp = v3_client.get(f"/api/v3/teams/{TEAM_ID}/members")
        assert resp.status_code == 404

    def test_add_returns_404(self, v3_client, mock_db_session):
        _set_side_effects(mock_db_session, [_flag(False)])
        resp = v3_client.post(
            f"/api/v3/teams/{TEAM_ID}/members",
            json={"user_id": MEMBER_USER_ID},
        )
        assert resp.status_code == 404

    def test_remove_returns_404(self, v3_client, mock_db_session):
        _set_side_effects(mock_db_session, [_flag(False)])
        resp = v3_client.delete(f"/api/v3/teams/{TEAM_ID}/members/{MEMBER_USER_ID}")
        assert resp.status_code == 404

    def test_update_returns_404(self, v3_client, mock_db_session):
        _set_side_effects(mock_db_session, [_flag(False)])
        resp = v3_client.patch(f"/api/v3/teams/{TEAM_ID}", json={"name": "Renamed"})
        assert resp.status_code == 404


# ── GET /teams/{id}/members ──────────────────────────────────────────────────


class TestListMembers:
    def test_empty(self, v3_client, mock_db_session):
        members = _result([])
        members.scalars.return_value.all.return_value = []
        _set_side_effects(
            mock_db_session,
            [_flag(True), _team(), _membership("admin"), members],
        )
        resp = v3_client.get(f"/api/v3/teams/{TEAM_ID}/members")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 0
        assert data["items"] == []

    def test_populated(self, v3_client, mock_db_session):
        members = _result([_member(MEMBER_USER_ID)])
        members.scalars.return_value.all.return_value = [_member(MEMBER_USER_ID)]
        _set_side_effects(
            mock_db_session,
            [_flag(True), _team(), _membership("admin"), members],
        )
        resp = v3_client.get(f"/api/v3/teams/{TEAM_ID}/members")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["user_id"] == MEMBER_USER_ID
        assert data["items"][0]["role"] == "member"


# ── POST /teams/{id}/members ───────────────────────────────────────────────


class TestAddMember:
    def test_success(self, v3_client, mock_db_session):
        # The mock DB doesn't apply the server-side default; mirror refresh()
        # populating joined_at the way a real session would.
        async def _refresh(member):
            member.joined_at = "2026-01-02T00:00:00Z"

        mock_db_session.refresh.side_effect = _refresh
        dup = _result(None)
        _set_side_effects(
            mock_db_session,
            [
                _flag(True),
                _team(),
                _membership("admin"),
                _user(MEMBER_USER_ID),
                dup,
            ],
        )
        resp = v3_client.post(
            f"/api/v3/teams/{TEAM_ID}/members",
            json={"user_id": MEMBER_USER_ID},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["user_id"] == MEMBER_USER_ID
        assert data["role"] == "member"
        mock_db_session.add.assert_called_once()

    def test_duplicate_returns_409(self, v3_client, mock_db_session):
        dup = _result(_member(MEMBER_USER_ID))
        _set_side_effects(
            mock_db_session,
            [
                _flag(True),
                _team(),
                _membership("admin"),
                _user(MEMBER_USER_ID),
                dup,
            ],
        )
        resp = v3_client.post(
            f"/api/v3/teams/{TEAM_ID}/members",
            json={"user_id": MEMBER_USER_ID},
        )
        assert resp.status_code == 409

    def test_unknown_user_returns_404(self, v3_client, mock_db_session):
        user_result = _result(None)
        _set_side_effects(
            mock_db_session,
            [
                _flag(True),
                _team(),
                _membership("admin"),
                user_result,
            ],
        )
        resp = v3_client.post(
            f"/api/v3/teams/{TEAM_ID}/members",
            json={"user_id": OTHER_USER_ID},
        )
        assert resp.status_code == 404


# ── DELETE /teams/{id}/members/{uid} ─────────────────────────────────────────


class TestRemoveMember:
    def test_success(self, v3_client, mock_db_session):
        member_result = _result(_member(MEMBER_USER_ID))
        _set_side_effects(
            mock_db_session,
            [_flag(True), _team(), _membership("admin"), member_result],
        )
        resp = v3_client.delete(f"/api/v3/teams/{TEAM_ID}/members/{MEMBER_USER_ID}")
        assert resp.status_code == 204
        mock_db_session.delete.assert_called_once()

    def test_missing_returns_404(self, v3_client, mock_db_session):
        member_result = _result(None)
        _set_side_effects(
            mock_db_session,
            [_flag(True), _team(), _membership("admin"), member_result],
        )
        resp = v3_client.delete(f"/api/v3/teams/{TEAM_ID}/members/{MEMBER_USER_ID}")
        assert resp.status_code == 404


# ── PATCH /teams/{id} ────────────────────────────────────────────────────────


class TestUpdateTeam:
    def test_partial_name(self, v3_client, mock_db_session):
        _set_side_effects(
            mock_db_session,
            [_flag(True), _team(), _membership("admin")],
        )
        resp = v3_client.patch(f"/api/v3/teams/{TEAM_ID}", json={"name": "Renamed Guild"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Renamed Guild"
        assert data["description"] == "Original description"

    def test_partial_description(self, v3_client, mock_db_session):
        _set_side_effects(
            mock_db_session,
            [_flag(True), _team(), _membership("admin")],
        )
        resp = v3_client.patch(
            f"/api/v3/teams/{TEAM_ID}",
            json={"description": "New description"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Design Guild"
        assert data["description"] == "New description"


# ── POST /teams (create_team authz: 404 before 403) ─────────────────────────


class TestCreateTeamAuthz:
    def test_nonmember_returns_404(self, v3_client, mock_db_session):
        # membership lookup returns None → must be 404 (never 403, never leak existence)
        _set_side_effects(mock_db_session, [_flag(True), _result(None)])
        resp = v3_client.post(
            "/api/v3/teams",
            json={"name": "New Team", "workspace_id": WS_UUID},
        )
        assert resp.status_code == 404

    def test_member_role_returns_403(self, v3_client, mock_db_session):
        # workspace member with role != admin/owner → 403 (they know it exists)
        _set_side_effects(
            mock_db_session,
            [_flag(True), _membership("member")],
        )
        resp = v3_client.post(
            "/api/v3/teams",
            json={"name": "New Team", "workspace_id": WS_UUID},
        )
        assert resp.status_code == 403


# ── DELETE /teams/{id} (delete_team authz: 404 before 403) ──────────────────


class TestDeleteTeamAuthz:
    def test_nonmember_returns_404(self, v3_client, mock_db_session):
        # team exists (404 not triggered), but membership lookup returns None → 404
        _set_side_effects(
            mock_db_session,
            [_flag(True), _result(_team_obj()), _result(None)],
        )
        resp = v3_client.delete(f"/api/v3/teams/{TEAM_ID}")
        assert resp.status_code == 404


# ── TeamResponse.member_count removed (dead/misleading field) ───────────────


class TestMemberCountField:
    def test_field_absent_from_create_response(self, v3_client, mock_db_session):
        async def _refresh(t):
            t.created_at = "2026-01-01T00:00:00Z"

        mock_db_session.refresh.side_effect = _refresh
        _set_side_effects(
            mock_db_session,
            [_flag(True), _membership("admin")],
        )
        resp = v3_client.post(
            "/api/v3/teams",
            json={"name": "New Team", "workspace_id": WS_UUID},
        )
        assert resp.status_code == 201
        assert "member_count" not in resp.json()["data"]

    def test_field_absent_from_update_response(self, v3_client, mock_db_session):
        _set_side_effects(
            mock_db_session,
            [_flag(True), _team(), _membership("admin")],
        )
        resp = v3_client.patch(f"/api/v3/teams/{TEAM_ID}", json={"name": "Renamed Guild"})
        assert resp.status_code == 200
        assert "member_count" not in resp.json()["data"]
