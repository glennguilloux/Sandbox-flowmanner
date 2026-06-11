from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.workspace_v3 import (
    AcceptInvitationRequest,
    InviteMemberRequest,
    TeamCreateRequest,
    WorkspaceCreateRequest,
    WorkspaceUpdateRequest,
)


class TestWorkspaceCreateRequest:
    def test_valid_creation(self):
        req = WorkspaceCreateRequest(name="My Team Workspace")
        assert req.name == "My Team Workspace"

    def test_slug_optional(self):
        req = WorkspaceCreateRequest(name="Test")
        assert req.slug is None

    def test_valid_slug(self):
        req = WorkspaceCreateRequest(name="Test", slug="my-slug")
        assert req.slug == "my-slug"

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            WorkspaceCreateRequest(name="")


class TestWorkspaceUpdateRequest:
    def test_partial_update(self):
        req = WorkspaceUpdateRequest(name="New Name")
        assert req.name == "New Name"
        assert req.logo_url is None
        assert req.settings is None

    def test_all_fields(self):
        req = WorkspaceUpdateRequest(
            name="Updated",
            logo_url="https://example.com/logo.png",
            settings={"timezone": "Europe/Paris"},
        )
        assert req.name == "Updated"


class TestInviteMemberRequest:
    def test_valid_invite(self):
        req = InviteMemberRequest(email="colleague@example.com", role="member")
        assert req.email == "colleague@example.com"
        assert req.role == "member"

    def test_viewer_role_accepted(self):
        req = InviteMemberRequest(email="a@b.com", role="viewer")
        assert req.role == "viewer"

    def test_invalid_role_rejected(self):
        with pytest.raises(ValidationError):
            InviteMemberRequest(email="a@b.com", role="superadmin")

    def test_invalid_email_rejected(self):
        with pytest.raises(ValidationError):
            InviteMemberRequest(email="not-an-email", role="member")


class TestAcceptInvitationRequest:
    def test_valid_token(self):
        req = AcceptInvitationRequest(token="a" * 64)
        assert len(req.token) == 64

    def test_short_token_rejected(self):
        with pytest.raises(ValidationError):
            AcceptInvitationRequest(token="short")

    def test_long_token_rejected(self):
        with pytest.raises(ValidationError):
            AcceptInvitationRequest(token="a" * 65)


class TestTeamCreateRequest:
    def test_valid_team(self):
        req = TeamCreateRequest(name="Engineering", workspace_id="ws_abc1234567890123456789012345678901")
        assert req.name == "Engineering"
        assert req.description == ""

    def test_with_description(self):
        req = TeamCreateRequest(
            name="Design",
            workspace_id="ws_abc1234567890123456789012345678901",
            description="Core design team",
        )
        assert req.description == "Core design team"
