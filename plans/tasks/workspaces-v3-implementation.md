# Workspaces v3 Implementation Blueprint

> **Derived from:** `v3-v4-migration-roadmap.md` Section 5 — Workspaces Service  
> **Codebase ground-truth:** All file paths, model classes, and column names verified against `/opt/flowmanner/backend/app/`  
> **Phase:** Phase 1 — Foundation (Week 1–6, parallel with Auth v3)  
> **Effort:** MEDIUM  
> **Generated:** 2026-05-31 by Buffy (DeepSeek V4 Pro)

**Prerequisite:** Auth v3 must be complete through Week 2 (core session endpoints working) before Workspaces v3 begins. Workspaces v3 uses v3 auth middleware (httpOnly cookies, session tracking, scope validation).

---

## 1. Exact Files to Create/Modify

### New files to create (all under `/opt/flowmanner/backend/app/`)

| # | File | Purpose |
|---|------|---------|
| 1 | `api/v3/workspaces.py` | Workspace CRUD + member management route handlers |
| 2 | `api/v3/workspace_invitations.py` | Invitation CRUD + accept flow |
| 3 | `api/v3/workspace_billing.py` | Billing/subscription endpoints |
| 4 | `api/v3/workspace_audit.py` | Audit log endpoints |
| 5 | `api/v3/teams.py` | Top-level team CRUD (extracted from workspace nesting) |
| 6 | `schemas/workspace_v3.py` | All v3 workspace + team + invitation Pydantic schemas |
| 7 | `services/workspace_v3_service.py` | Workspace business logic (invite dispatch, ownership xfer, billing, audit) |
| 8 | `services/invitation_email_service.py` | SMTP/Resend email dispatch for invitations |
| 9 | `templates/emails/workspace_invitation.html` | HTML email template for workspace invitations |
| 10 | `templates/emails/workspace_invitation.txt` | Plain text fallback |

### Existing files to modify

| # | File | Change |
|---|------|--------|
| 1 | `main_fastapi.py` | Register v3 workspace/team routers |
| 2 | `models/workspace_models.py` | Add columns: `logo_url`, `settings` (JSONB), `member_limit`, `storage_used`; add `expires_at` to WorkspaceInvitation (already exists, verify); add `role` enum to WorkspaceMember for "viewer" |
| 3 | `config.py` | Verify RESEND_API_KEY, SMTP_HOST/PORT/USERNAME/PASSWORD are usable; add `WORKSPACE_INVITE_EXPIRY_DAYS` |

### Files NOT modified (purity constraint)

- `api/v2/workspaces.py` — untouched (90-day deprecation via feature flag only)
- `api/v1/workspace.py` — untouched
- `models/workspace_models.py` — only additive column changes (no renames, no deletes)

---

## 2. Database Migration (Alembic)

### Migration file: `backend/alembic/versions/workspaces_v3_init.py`

```python
"""workspaces_v3_init — workspace settings, billing fields, team top-level support

Revision ID: workspaces_v3_001
Revises: auth_v3_001
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone

revision = 'workspaces_v3_001'
down_revision = 'auth_v3_001'
branch_labels = None
depends_on = None


def upgrade():
    # ── Add columns to workspaces ──
    op.add_column('workspaces', sa.Column('logo_url', sa.String(500), nullable=True))
    op.add_column('workspaces', sa.Column('settings', JSONB, nullable=True,
        server_default=sa.text("'{}'::jsonb")))
    op.add_column('workspaces', sa.Column('member_limit', sa.Integer(), nullable=True,
        server_default=sa.text('5')))  # Free tier: 5 members
    op.add_column('workspaces', sa.Column('storage_used_bytes', sa.BigInteger(), nullable=True,
        server_default=sa.text('0')))

    # ── Add columns to workspace_invitations ──
    # expires_at already exists in the model — verify in DB, add if missing
    # accepted_at already exists — verify
    op.add_column('workspace_invitations', sa.Column('invitation_message',
        sa.Text(), nullable=True, server_default=sa.text("''")))

    # ── Add workspace_invitations.expires_at if missing ──
    # (Check: the model has it but migration may not have added it)
    # ⚠️ If expires_at already exists, verify its type is DateTime(timezone=True).
    #    A plain DateTime (without timezone) will cause silent UTC offset bugs in v3.
    #    To fix: ALTER COLUMN expires_at TYPE TIMESTAMPTZ.
    try:
        op.add_column('workspace_invitations', sa.Column('expires_at_verify',
            sa.DateTime(timezone=True), nullable=True))
        op.drop_column('workspace_invitations', 'expires_at_verify')
    except Exception:
        pass  # Column already exists — verify TIMESTAMPTZ manually

    # ── Add workspace_activity_log table ──
    op.create_table(
        'workspace_activity_log',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),       # 'member.invited', 'member.joined', 'member.removed', 'role.changed', 'workspace.updated', 'ownership.transferred'
        sa.Column('target_type', sa.String(50), nullable=True),    # 'workspace', 'member', 'team', 'invitation'
        sa.Column('target_id', sa.String(100), nullable=True),
        sa.Column('metadata', JSONB, nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Index('ix_activity_log_workspace_time', 'workspace_id', 'created_at'),
    )

    # ── Add "viewer" role support — no migration needed (column is String(50)) ──

    # ── Seed feature flags ──
    op.execute("""
        INSERT INTO feature_flags (key, name, description, enabled_globally, created_at, updated_at)
        VALUES
            ('WORKSPACES_V3_ENDPOINTS', 'Workspaces v3 Endpoints',
             'Enable v3 workspace routes (invitations, billing, audit, top-level teams)',
             false, NOW(), NOW()),
            ('WORKSPACES_V3_INVITES', 'Workspaces v3 Email Invitations',
             'Enable email invitation send/accept flow',
             false, NOW(), NOW()),
            ('WORKSPACES_V3_BILLING', 'Workspaces v3 Billing',
             'Enable subscription and billing endpoints',
             false, NOW(), NOW()),
            ('WORKSPACES_V3_TEAMS_TOPLEVEL', 'Workspaces v3 Top-Level Teams',
             'Serve teams at /api/v3/teams instead of nested under workspaces',
             false, NOW(), NOW()),
            ('WORKSPACES_V3_AUDIT', 'Workspaces v3 Audit Log',
             'Enable workspace activity audit log endpoints',
             false, NOW(), NOW()),
            ('WORKSPACES_V3_ROLES', 'Workspaces v3 Extended Roles',
             'Support viewer role and custom workspace roles',
             false, NOW(), NOW())
        ON CONFLICT (key) DO NOTHING;
    """)

    # ── Data backfill: set member_limit for existing workspaces ──
    op.execute("""
        UPDATE workspaces
        SET member_limit = 5
        WHERE member_limit IS NULL;
    """)


def downgrade():
    op.drop_table('workspace_activity_log')
    op.drop_column('workspaces', 'logo_url')
    op.drop_column('workspaces', 'settings')
    op.drop_column('workspaces', 'member_limit')
    op.drop_column('workspaces', 'storage_used_bytes')
    op.drop_column('workspace_invitations', 'invitation_message')

    op.execute("""
        DELETE FROM feature_flags WHERE key IN (
            'WORKSPACES_V3_ENDPOINTS', 'WORKSPACES_V3_INVITES', 'WORKSPACES_V3_BILLING',
            'WORKSPACES_V3_TEAMS_TOPLEVEL', 'WORKSPACES_V3_AUDIT', 'WORKSPACES_V3_ROLES'
        );
    """)
```

### Data backfills

| Table | Column | Backfill | Risk |
|-------|--------|----------|------|
| `workspaces` | `settings` | `'{}'::jsonb` — empty settings for all existing workspaces | None |
| `workspaces` | `member_limit` | `5` for all existing workspaces (Free tier default) | None — additive only |
| `workspaces` | `storage_used_bytes` | `0` for all | None |
| `workspace_invitations` | `expires_at` | `NOW() + 7 days` for pending invitations with NULL expiry | **Verify before running** — check current state |

No data migration needed for existing workspace members or teams — the new `viewer` role and top-level team routes are additive.

---

## 3. Pydantic Models — New Request/Response Schemas

File: `backend/app/schemas/workspace_v3.py`

```python
"""Workspaces v3 Pydantic schemas — workspace, member, team, invitation, billing, audit."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


# ═══════════════════════════════════════════════
# Request Schemas
# ═══════════════════════════════════════════════

class WorkspaceCreateRequest(BaseModel):
    """POST /workspaces — create a new workspace."""
    name: str = Field(..., min_length=1, max_length=200)
    slug: Optional[str] = Field(default=None, max_length=100)

    @field_validator('slug')
    @classmethod
    def slug_must_be_valid(cls, v: str | None) -> str | None:
        if v and not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError('Slug must contain only alphanumeric characters, hyphens, or underscores')
        return v

class WorkspaceUpdateRequest(BaseModel):
    """PATCH /workspaces/{id} — update workspace."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    slug: Optional[str] = Field(default=None, max_length=100)
    logo_url: Optional[str] = Field(default=None, max_length=500)
    settings: Optional[dict[str, Any]] = Field(default=None)

    @field_validator('settings')
    @classmethod
    def validate_settings_keys(cls, v: dict | None) -> dict | None:
        if v is None:
            return v
        allowed = {'default_model', 'timezone', 'notifications_enabled', 'default_language'}
        for key in v:
            if key not in allowed:
                raise ValueError(f'Unknown settings key: {key}. Allowed: {allowed}')
        return v

class TransferOwnershipRequest(BaseModel):
    """POST /workspaces/{id}/transfer-ownership — transfer workspace to another member."""
    new_owner_user_id: int
    two_fa_code: Optional[str] = Field(default=None, description="Required if current owner has 2FA enabled")

class InviteMemberRequest(BaseModel):
    """POST /workspaces/{id}/invitations — invite a member by email."""
    email: EmailStr = Field(..., max_length=255)
    role: str = Field(default="member", pattern="^(member|viewer|admin)$")
    message: Optional[str] = Field(default=None, max_length=1000)

class AcceptInvitationRequest(BaseModel):
    """POST /workspaces/{id}/invitations/{invite_id}/accept — accept an invitation."""
    token: str = Field(..., min_length=64, max_length=64, description="Invitation token from email link")

class UpdateMemberRoleRequest(BaseModel):
    """PATCH /workspaces/{id}/members/{user_id} — update member role."""
    role: str = Field(..., pattern="^(member|viewer|admin)$")

class TeamCreateRequest(BaseModel):
    """POST /teams — create a team (top-level in v3)."""
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    workspace_id: str = Field(..., min_length=36)

class TeamUpdateRequest(BaseModel):
    """PATCH /teams/{id} — update a team."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)

class TeamAddMemberRequest(BaseModel):
    """POST /teams/{id}/members — add a member to a team."""
    user_id: int

class WebhookCreateRequest(BaseModel):
    """POST /workspaces/{id}/webhooks — create a workspace-level webhook."""
    url: str = Field(..., max_length=2000)
    events: list[str] = Field(..., min_length=1)


# ═══════════════════════════════════════════════
# Response Schemas
# ═══════════════════════════════════════════════

class WorkspaceResponse(BaseModel):
    """Workspace detail response."""
    id: str
    name: str
    slug: str
    owner_id: int
    owner_name: Optional[str] = None
    plan: str = "free"
    member_count: int = 0
    member_limit: int = 5
    logo_url: Optional[str] = None
    settings: dict[str, Any] = {}
    storage_used_bytes: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class WorkspaceListItem(BaseModel):
    """Workspace in list (abbreviated)."""
    id: str
    name: str
    slug: str
    plan: str
    member_count: int
    logo_url: Optional[str]
    role: str                                              # Current user's role in this workspace
    created_at: datetime

class MemberResponse(BaseModel):
    """Workspace member with optional inline user data."""
    id: int                                                 # WorkspaceMember.id
    user_id: int
    workspace_id: str
    role: str
    joined_at: datetime
    # Inline user data via ?include=user
    user: Optional["UserSummary"] = None

class MemberListResponse(BaseModel):
    """Member list item — always includes basic user info."""
    user_id: int
    email: str
    full_name: Optional[str]
    avatar_url: Optional[str]
    role: str
    joined_at: datetime

class InvitationResponse(BaseModel):
    """Invitation detail (list view — token never returned)."""
    id: str
    workspace_id: str
    email: str
    role: str
    status: str                                             # 'pending', 'accepted', 'expired', 'revoked'
    invited_by_name: Optional[str] = None
    message: Optional[str] = None
    created_at: datetime
    expires_at: datetime
    accepted_at: Optional[datetime] = None

class InvitationCreatedResponse(InvitationResponse):
    """Returned ONLY on POST /invitations creation.
    
    Includes the full token for building the email link.
    The token is shown ONCE here — list endpoints use InvitationResponse (no token).
    """
    token: str                                             # 64-char hex token shown ONLY on creation

class TeamResponse(BaseModel):
    """Team detail (top-level in v3, workspace-scoped)."""
    id: str
    workspace_id: str
    name: str
    description: str
    member_count: int
    created_at: datetime

class AuditLogEntry(BaseModel):
    """Workspace activity audit log entry."""
    id: str
    actor_id: Optional[int]
    actor_name: Optional[str]
    action: str
    target_type: Optional[str]
    target_id: Optional[str]
    metadata: dict[str, Any]
    created_at: datetime

class BillingResponse(BaseModel):
    """Workspace billing/subscription info."""
    workspace_id: str
    plan: str                                               # 'free', 'pro', 'enterprise'
    plan_display_name: str                                  # 'Free', 'Pro', 'Enterprise'
    member_limit: int
    storage_limit_bytes: int                                # In bytes
    storage_used_bytes: int
    billing_cycle_start: Optional[datetime] = None           # Subscription period start
    billing_cycle_end: Optional[datetime] = None
    trial_ends_at: Optional[datetime] = None
    payment_method: Optional[str] = None                     # 'paypal', 'stripe', 'none'

# Forward reference for MemberResponse.user
from app.schemas.auth_v3 import UserSummary
MemberResponse.model_rebuild()
```

---

## 4. Route Handlers — Endpoint Signatures, Status Codes, Error Responses

All workspace routes are under `/api/v3/workspaces`. Team routes are at `/api/v3/teams`.

### 4.1 Workspace CRUD

| Method | Path | Handler | Status | Purpose |
|--------|------|---------|--------|---------|
| `GET` | `/workspaces` | `list_workspaces()` | 200 | List current user's workspaces |
| `POST` | `/workspaces` | `create_workspace()` | 201 | Create a new workspace |
| `GET` | `/workspaces/{id}` | `get_workspace()` | 200 | Get workspace detail |
| `PATCH` | `/workspaces/{id}` | `update_workspace()` | 200 | Update workspace (name, slug, logo, settings) |
| `DELETE` | `/workspaces/{id}` | `delete_workspace()` | 204 | Delete workspace (owner only) |
| `POST` | `/workspaces/{id}/transfer-ownership` | `transfer_ownership()` | 200 | Transfer ownership to another member |

```python
# Example signatures:
@router.get("/workspaces")
async def list_workspaces(
    db: AsyncSession = Depends(get_db),
    session: AuthSession = Depends(get_current_session),
):
    """List workspaces. Returns abbreviated list with member counts.
    
    Returns:
        200: { data: [WorkspaceListItem], meta, error: null }
    """
    ...

@router.get("/workspaces/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    session: AuthSession = Depends(get_current_session),
    include: str | None = Query(None, description="Comma-separated: 'members,teams,settings'"),
):
    """Get workspace detail. Supports ?include=members,teams,settings.
    
    Returns:
        200: { data: WorkspaceResponse, meta, error: null }
        404: WORKSPACE_NOT_FOUND
    """
    ...

@router.post("/workspaces/{workspace_id}/transfer-ownership")
async def transfer_ownership(
    workspace_id: str,
    payload: TransferOwnershipRequest,
    db: AsyncSession = Depends(get_db),
    session: AuthSession = Depends(get_current_session),
):
    """Transfer workspace ownership. Requires 2FA if enabled.
    
    Returns:
        200: { data: WorkspaceResponse, meta, error: null }
        403: Not owner
        401: Invalid 2FA code
    """
    ...
```

### 4.2 Member Management

| Method | Path | Handler | Status | Purpose |
|--------|------|---------|--------|---------|
| `GET` | `/workspaces/{id}/members` | `list_members()` | 200 | List members (with ?include=user for inline user data) |
| `PATCH` | `/workspaces/{id}/members/{user_id}` | `update_member_role()` | 200 | Change member role |
| `DELETE` | `/workspaces/{id}/members/{user_id}` | `remove_member()` | 204 | Remove member from workspace |

**v3 change from v2:** `GET /members` no longer inlines user data by default. Use `?include=user` to get email and name.

```python
@router.get("/workspaces/{workspace_id}/members")
async def list_members(
    workspace_id: str,
    include: str | None = Query(None, description="'user' to include user profile data"),
    db: AsyncSession = Depends(get_db),
    session: AuthSession = Depends(get_current_session),
):
    """List workspace members.
    
    v2 behavior (always inlines user data): ?include=user
    v3 default: Returns membership records only (id, user_id, role, joined_at)
    
    Returns:
        200: { data: [MemberListResponse], meta, error: null }
    """
    ...
```

### 4.3 Invitations

> **⚠️ Transaction Safety:** `create_invitation()` must **commit the invitation record to the database first**,
> and only then dispatch the email (Resend/SMTP) **after** the DB transaction completes.
> If the email provider blocks, times out, or throws inside the live DB transaction, it will hold
> the connection open or roll back the entire operation. Use FastAPI `BackgroundTasks` or an async
> task queue (Celery/Arq) to decouple email dispatch from the request-response cycle.

| Method | Path | Handler | Status | Purpose |
|--------|------|---------|--------|---------|
| `POST` | `/workspaces/{id}/invitations` | `create_invitation()` | 201 | Send invitation email |
| `GET` | `/workspaces/{id}/invitations` | `list_invitations()` | 200 | List pending/accepted invitations |
| `DELETE` | `/workspaces/{id}/invitations/{invite_id}` | `revoke_invitation()` | 204 | Revoke a pending invitation |
| `POST` | `/workspaces/{id}/invitations/{invite_id}/accept` | `accept_invitation()` | 200 | Accept invitation (with token) |

```python
@router.post("/workspaces/{workspace_id}/invitations", status_code=status.HTTP_201_CREATED)
async def create_invitation(
    workspace_id: str,
    payload: InviteMemberRequest,
    db: AsyncSession = Depends(get_db),
    session: AuthSession = Depends(get_current_session),
):
    """Invite a user to a workspace by email. Sends invitation email via Resend/SMTP.
    
    Rate limit: 50 invites/hr per workspace.
    
    Returns:
        201: { data: InvitationCreatedResponse, meta, error: null }
              ^ NOTE: Includes token field — shown ONCE on creation
        400: MEMBER_LIMIT_REACHED
        400: INVITE_ALREADY_ACCEPTED — user is already a member
        429: Rate limited
    """
    ...

@router.post("/workspaces/{workspace_id}/invitations/{invite_id}/accept")
async def accept_invitation(
    workspace_id: str,
    invite_id: str,
    payload: AcceptInvitationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Accept a workspace invitation (no authentication required — token validates).
    
    The invitation link in the email includes the 64-char token.
    User must be logged in (or register) for this to work.
    
    Returns:
        200: { data: { workspace_id: "...", role: "member", message: "Welcome to ..." }, meta, error: null }
        400: INVITATION_EXPIRED
        404: INVITATION_NOT_FOUND
        400: INVITATION_ALREADY_ACCEPTED
    """
    ...
```

### 4.4 Billing

| Method | Path | Handler | Status | Purpose |
|--------|------|---------|--------|---------|
| `GET` | `/workspaces/{id}/billing` | `get_billing()` | 200 | Get subscription/billing info |
| `POST` | `/workspaces/{id}/billing/upgrade` | `upgrade_plan()` | 200 | Initiate plan upgrade (returns checkout URL) |
| `POST` | `/workspaces/{id}/billing/cancel` | `cancel_subscription()` | 200 | Cancel subscription |

### 4.5 Audit Log

| Method | Path | Handler | Status | Purpose |
|--------|------|---------|--------|---------|
| `GET` | `/workspaces/{id}/audit-log` | `get_audit_log()` | 200 | Get activity feed (cursor-paginated) |

### 4.6 Teams (Top-Level)

| Method | Path | Handler | Status | Purpose |
|--------|------|---------|--------|---------|
| `GET` | `/teams?workspace_id={id}` | `list_teams()` | 200 | List teams in a workspace |
| `POST` | `/teams` | `create_team()` | 201 | Create a team |
| `GET` | `/teams/{id}` | `get_team()` | 200 | Get team detail |
| `PATCH` | `/teams/{id}` | `update_team()` | 200 | Update team |
| `DELETE` | `/teams/{id}` | `delete_team()` | 204 | Delete team |
| `GET` | `/teams/{id}/members` | `list_team_members()` | 200 | List team members |
| `POST` | `/teams/{id}/members` | `add_team_member()` | 201 | Add member to team |
| `DELETE` | `/teams/{id}/members/{user_id}` | `remove_team_member()` | 204 | Remove from team |

**v2 fallback:** `GET /api/v2/workspaces/{id}/teams` continues to work for 90 days.

### Error Response Format

```json
{
  "data": null,
  "meta": { "request_id": "abc-123", "timestamp": "2026-06-01T12:00:00Z" },
  "error": {
    "code": "MEMBER_LIMIT_REACHED",
    "message": "This workspace has reached its member limit (5). Upgrade to Pro for unlimited members.",
    "details": { "current": 5, "limit": 5, "upgrade_url": "/api/v3/workspaces/ws_1/billing/upgrade" },
    "trace_id": "trc_abc123"
  }
}
```

**Error codes in v3:**
- `WORKSPACE_NOT_FOUND` — 404
- `SLUG_CONFLICT` — 409 (workspace slug already taken)
- `MEMBER_LIMIT_REACHED` — 400
- `INVITE_ALREADY_ACCEPTED` — 400
- `INVITATION_EXPIRED` — 400
- `NOT_WORKSPACE_MEMBER` — 403
- `INSUFFICIENT_ROLE` — 403 (needs admin/owner)
- `OWNERSHIP_TRANSFER_INVALID` — 400 (target not a member, self-transfer)
- `TEAM_NOT_FOUND` — 404

---

## 5. Middleware — Not Applicable (Reuses Auth v3)

Workspaces v3 does not introduce new middleware. It relies on:
- **Auth v3 middleware:** httpOnly cookie parsing (`AuthCookieMiddleware`), scope validation (`ScopeValidationMiddleware`), session tracking
- **v3 exception handlers:** registered in `api/v3/middleware.py` (created during Auth v3 week 1)

### v2 Endpoint Deprecation Gating

Same mechanism as Auth v3 (see auth-v3-implementation.md Section 5.8):

1. **Frontend-level routing:** When `WORKSPACES_V3_ENDPOINTS` is `true`, the frontend
   routes workspace calls to `/api/v3/workspaces/...`. Teams switch from
   `/api/v2/workspaces/{id}/teams` to `/api/v3/teams?workspace_id={id}`.
2. **Backend v2 endpoints stay alive:** `api/v2/workspaces.py` remains registered and
   functional for the full 90-day deprecation window. Removed in a later Phase.
3. **Deprecation headers:** The versioning middleware adds `Deprecation: true` and
   `Sunset: <date>` headers to v2 workspace responses after v3 reaches 100%.
4. **No server-side routing by flag:** The backend does NOT inspect feature flags to
   route between v2 and v3 — frontend decides based on flag state.

### Permission Model

All workspace endpoints check via `_check_workspace_access()` (ported from v2 pattern, enhanced):

```python
async def _check_workspace_access(
    db: AsyncSession, workspace_id: str, user_id: int, required_roles: list[str] | None = None
) -> WorkspaceMember:
    """Verify user has access to workspace. Optionally check role.
    
    Roles: 'viewer' (read-only), 'member' (CRUD), 'admin' (manage), 'owner' (full)
    """
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=404, detail="Workspace not found")
    
    if required_roles and membership.role not in required_roles:
        raise HTTPException(status_code=403, detail="Insufficient role")
    
    return membership
```

Role hierarchy:
- `viewer` — can read workspace, members, teams
- `member` — can create/invite, read all
- `admin` — can update workspace, manage members/teams
- `owner` — can delete workspace, transfer ownership

---

## 6. Feature Flags

| Flag Key | Purpose | Default | Rollout |
|----------|---------|---------|---------|
| `WORKSPACES_V3_ENDPOINTS` | Master flag — gates all v3 workspace routes | `false` | 5% → 25% → 50% → 100% |
| `WORKSPACES_V3_INVITES` | Enables email invitation send/accept | `false` | Workspace opt-in → global |
| `WORKSPACES_V3_BILLING` | Enables billing endpoints | `false` | Per-workspace (Pro trial) |
| `WORKSPACES_V3_TEAMS_TOPLEVEL` | Teams served at `/api/v3/teams` | `false` | 100% when ready |
| `WORKSPACES_V3_AUDIT` | Enables audit log | `false` | 100% when ready |
| `WORKSPACES_V3_ROLES` | Enables viewer role + role updates | `false` | 100% when ready |

### Flag Resolution Pattern

Same as Auth v3 — check `feature_flags` table per-request:

```python
async def is_workspace_v3_enabled(db: AsyncSession) -> bool:
    result = await db.execute(
        text("SELECT enabled_globally FROM feature_flags WHERE key = 'WORKSPACES_V3_ENDPOINTS'")
    )
    flag = result.scalar()
    return bool(flag)
```

---

## 7. Frontend Contract — Next.js Changes Required

### 7.1 API Client Changes

| v2 Endpoint | v3 Endpoint | Notes |
|-------------|-------------|-------|
| `GET /api/v2/workspaces` | `GET /api/v3/workspaces` | Response shape similar, adds `logo_url`, `settings`, `role` |
| `POST /api/v2/workspaces` | `POST /api/v3/workspaces` | Same shape |
| `GET /api/v2/workspaces/{id}` | `GET /api/v3/workspaces/{id}?include=members,settings` | Supports `?include=` for related data |
| `PATCH /api/v2/workspaces/{id}` | `PATCH /api/v3/workspaces/{id}` | Adds `logo_url` and `settings` fields |
| `GET /api/v2/workspaces/{id}/members` | `GET /api/v3/workspaces/{id}/members?include=user` | User data inlined only with `?include=user` |
| N/A | `POST /api/v3/workspaces/{id}/invitations` | **NEW** — send invite |
| N/A | `GET /api/v3/workspaces/{id}/invitations` | **NEW** — list invites |
| N/A | `POST /api/v3/workspaces/{id}/transfer-ownership` | **NEW** — ownership transfer |
| N/A | `GET /api/v3/workspaces/{id}/billing` | **NEW** — billing page |
| N/A | `GET /api/v3/workspaces/{id}/audit-log` | **NEW** — activity feed |
| `GET /api/v2/workspaces/{id}/teams` | `GET /api/v3/teams?workspace_id={id}` | Teams are now top-level |
| `POST /api/v2/workspaces/{id}/teams` | `POST /api/v3/teams` | `workspace_id` in body instead of path |

### 7.2 New UI Components

| Component | Route | Description |
|-----------|-------|-------------|
| **Invite Members Dialog** | Workspace → Members → "Invite" | Email input, role selector, custom message |
| **Pending Invitations Panel** | Workspace → Members | List pending invites with "Revoke" button |
| **Accept Invitation Page** | `/invite/{invite_id}?token=...` | Landing page for invitation links |
| **Workspace Settings Page** | Workspace → Settings | Logo upload, default model, timezone, notifications |
| **Billing Page** | Workspace → Billing | Current plan, member limits, upgrade CTA |
| **Audit Log** | Workspace → Activity | Chronological feed of workspace events |
| **Transfer Ownership Dialog** | Workspace → Settings → Danger Zone | Member selector, 2FA confirmation |
| **Team Management Page** | Workspace → Teams | Create, rename, delete teams; manage members |

### 7.3 Invitation Email Link Format

```
https://flowmanner.com/invite/{workspace_id}/{invite_id}?token={64_char_token}

Example:
https://flowmanner.com/invite/ws_abc123/inv_xyz789?token=a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4
```

Frontend parses the token from the URL, calls `POST /api/v3/workspaces/{workspace_id}/invitations/{invite_id}/accept` with `{ token: "..." }` in the body.

---

## 8. Test Plan

### 8.1 Unit Tests

File: `backend/tests/test_workspace_v3_unit.py`

```python
"""Unit tests for Workspace v3 schemas and service functions (no DB)."""

import pytest
from pydantic import ValidationError
from app.schemas.workspace_v3 import (
    WorkspaceCreateRequest, InviteMemberRequest, TeamCreateRequest,
    WorkspaceResponse, AcceptInvitationRequest,
)
from app.services.workspace_v3_service import (
    generate_invite_token, validate_role, slugify_workspace_name,
)

class TestWorkspaceCreateRequest:
    def test_valid_creation(self):
        req = WorkspaceCreateRequest(name="My Team Workspace")
        assert req.name == "My Team Workspace"

    def test_slug_validation(self):
        WorkspaceCreateRequest(name="Test", slug="my-slug")
        WorkspaceCreateRequest(name="Test", slug="my_slug")

    def test_invalid_slug_rejected(self):
        with pytest.raises(ValidationError):
            WorkspaceCreateRequest(name="Test", slug="invalid slug!")

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            WorkspaceCreateRequest(name="")

class TestInviteMemberRequest:
    def test_valid_invite(self):
        req = InviteMemberRequest(email="colleague@example.com", role="member")
        assert req.email == "colleague@example.com"

    def test_invalid_email_rejected(self):
        with pytest.raises(ValidationError):
            InviteMemberRequest(email="not-an-email", role="member")

    def test_invalid_role_rejected(self):
        with pytest.raises(ValidationError):
            InviteMemberRequest(email="a@b.com", role="superadmin")

    def test_viewer_role_accepted(self):
        req = InviteMemberRequest(email="a@b.com", role="viewer")
        assert req.role == "viewer"

class TestAcceptInvitationRequest:
    def test_valid_token(self):
        req = AcceptInvitationRequest(token="a" * 64)
        assert len(req.token) == 64

    def test_short_token_rejected(self):
        with pytest.raises(ValidationError):
            AcceptInvitationRequest(token="short")

class TestInviteTokenGeneration:
    def test_token_is_64_chars(self):
        token = generate_invite_token()
        assert len(token) == 64
        assert token.isalnum()  # All hex characters

    def test_tokens_are_unique(self):
        tokens = {generate_invite_token() for _ in range(100)}
        assert len(tokens) == 100

class TestRoleValidation:
    def test_valid_roles(self):
        for role in ["viewer", "member", "admin", "owner"]:
            assert validate_role(role) is True

    def test_invalid_role(self):
        assert validate_role("bogus") is False

class TestSlugGeneration:
    def test_simple_name(self):
        assert slugify_workspace_name("My Workspace") == "my-workspace"

    def test_special_chars_removed(self):
        assert slugify_workspace_name("John's Team!") == "johns-team"

    def test_multi_dash_collapsed(self):
        assert slugify_workspace_name("My   Workspace") == "my-workspace"
```

### 8.2 Integration Tests

File: `backend/tests/test_workspace_v3_integration.py`

```python
"""Integration tests for Workspace v3 endpoints (requires test DB)."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main_fastapi import app

pytestmark = pytest.mark.anyio

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.fixture
async def auth_headers(client):
    """Register → login → return auth headers."""
    await client.post("/api/v3/auth/users", json={
        "email": "wsowner@example.com",
        "password": "TestPass123!",
        "full_name": "Workspace Owner",
    })
    login = await client.post("/api/v3/auth/sessions", json={
        "login": "wsowner@example.com",
        "password": "TestPass123!",
    })
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}

class TestWorkspaceCRUD:
    async def test_create_workspace(self, client, auth_headers):
        resp = await client.post("/api/v3/workspaces", json={
            "name": "Test Workspace",
            "slug": "test-ws",
        }, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Test Workspace"
        assert data["slug"] == "test-ws"
        assert data["plan"] == "free"
        assert data["member_count"] == 1  # Creator auto-added
        assert data["member_limit"] == 5

    async def test_list_workspaces(self, client, auth_headers):
        await client.post("/api/v3/workspaces", json={"name": "WS A"}, headers=auth_headers)
        await client.post("/api/v3/workspaces", json={"name": "WS B"}, headers=auth_headers)

        resp = await client.get("/api/v3/workspaces", headers=auth_headers)
        assert resp.status_code == 200
        workspaces = resp.json()["data"]
        assert len(workspaces) >= 2
        assert all("role" in w for w in workspaces)

    async def test_get_workspace(self, client, auth_headers):
        create = await client.post("/api/v3/workspaces", json={"name": "Detail WS"}, headers=auth_headers)
        ws_id = create.json()["data"]["id"]

        resp = await client.get(f"/api/v3/workspaces/{ws_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Detail WS"
        assert "settings" in resp.json()["data"]

    async def test_update_workspace_settings(self, client, auth_headers):
        create = await client.post("/api/v3/workspaces", json={"name": "Settings WS"}, headers=auth_headers)
        ws_id = create.json()["data"]["id"]

        resp = await client.patch(f"/api/v3/workspaces/{ws_id}", json={
            "settings": {"default_model": "deepseek-v4", "timezone": "Europe/Paris"}
        }, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["settings"]["default_model"] == "deepseek-v4"

    async def test_delete_workspace(self, client, auth_headers):
        create = await client.post("/api/v3/workspaces", json={"name": "Delete Me"}, headers=auth_headers)
        ws_id = create.json()["data"]["id"]

        resp = await client.delete(f"/api/v3/workspaces/{ws_id}", headers=auth_headers)
        assert resp.status_code == 204

class TestMemberManagement:
    async def test_list_members_default(self, client, auth_headers):
        create = await client.post("/api/v3/workspaces", json={"name": "Member WS"}, headers=auth_headers)
        ws_id = create.json()["data"]["id"]

        resp = await client.get(f"/api/v3/workspaces/{ws_id}/members", headers=auth_headers)
        assert resp.status_code == 200
        members = resp.json()["data"]
        assert len(members) == 1
        # v3 default: no inline user data
        assert "email" not in members[0] or members[0].get("email") is None

    async def test_list_members_with_user_data(self, client, auth_headers):
        create = await client.post("/api/v3/workspaces", json={"name": "Inline WS"}, headers=auth_headers)
        ws_id = create.json()["data"]["id"]

        resp = await client.get(f"/api/v3/workspaces/{ws_id}/members?include=user", headers=auth_headers)
        assert resp.status_code == 200
        members = resp.json()["data"]
        assert len(members) == 1
        assert members[0]["email"] == "wsowner@example.com"
        assert members[0]["full_name"] == "Workspace Owner"

class TestInvitations:
    async def test_create_and_list_invitation(self, client, auth_headers):
        create = await client.post("/api/v3/workspaces", json={"name": "Invite WS"}, headers=auth_headers)
        ws_id = create.json()["data"]["id"]

        invite_resp = await client.post(
            f"/api/v3/workspaces/{ws_id}/invitations",
            json={"email": "invited@example.com", "role": "member", "message": "Join us!"},
            headers=auth_headers,
        )
        assert invite_resp.status_code == 201
        assert invite_resp.json()["data"]["status"] == "pending"
        assert invite_resp.json()["data"]["email"] == "invited@example.com"

        # List invitations — token NOT returned (uses InvitationResponse, not InvitationCreatedResponse)
        list_resp = await client.get(
            f"/api/v3/workspaces/{ws_id}/invitations",
            headers=auth_headers,
        )
        assert list_resp.status_code == 200
        assert len(list_resp.json()["data"]) == 1
        # Token must NOT appear in list response — only in creation response
        assert "token" not in list_resp.json()["data"][0]

    async def test_revoke_invitation(self, client, auth_headers):
        create = await client.post("/api/v3/workspaces", json={"name": "Revoke WS"}, headers=auth_headers)
        ws_id = create.json()["data"]["id"]

        invite = await client.post(
            f"/api/v3/workspaces/{ws_id}/invitations",
            json={"email": "temp@example.com", "role": "member"},
            headers=auth_headers,
        )
        invite_id = invite.json()["data"]["id"]

        revoke = await client.delete(
            f"/api/v3/workspaces/{ws_id}/invitations/{invite_id}",
            headers=auth_headers,
        )
        assert revoke.status_code == 204

    async def test_accept_invitation(self, client, auth_headers):
        # Create workspace and send invite
        create = await client.post("/api/v3/workspaces", json={"name": "Accept WS"}, headers=auth_headers)
        ws_id = create.json()["data"]["id"]

        invite = await client.post(
            f"/api/v3/workspaces/{ws_id}/invitations",
            json={"email": "joiner@example.com", "role": "member"},
            headers=auth_headers,
        )
        invite_id = invite.json()["data"]["id"]
        # token is only in InvitationCreatedResponse (creation), not InvitationResponse (list)
        token = invite.json()["data"]["token"]  # 64-char hex, shown ONCE

        # Register the invited user
        await client.post("/api/v3/auth/users", json={
            "email": "joiner@example.com",
            "password": "TestPass123!",
            "full_name": "Joiner",
        })
        login = await client.post("/api/v3/auth/sessions", json={
            "login": "joiner@example.com",
            "password": "TestPass123!",
        })
        joiner_headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

        # Accept invitation
        accept = await client.post(
            f"/api/v3/workspaces/{ws_id}/invitations/{invite_id}/accept",
            json={"token": token},
            headers=joiner_headers,
        )
        assert accept.status_code == 200
        assert accept.json()["data"]["role"] == "member"

        # Verify member count increased
        ws_resp = await client.get(f"/api/v3/workspaces/{ws_id}", headers=auth_headers)
        assert ws_resp.json()["data"]["member_count"] == 2

class TestTeams:
    async def test_create_team_top_level(self, client, auth_headers):
        create = await client.post("/api/v3/workspaces", json={"name": "Team WS"}, headers=auth_headers)
        ws_id = create.json()["data"]["id"]

        team_resp = await client.post("/api/v3/teams", json={
            "name": "Engineering",
            "description": "Core engineering team",
            "workspace_id": ws_id,
        }, headers=auth_headers)
        assert team_resp.status_code == 201
        assert team_resp.json()["data"]["workspace_id"] == ws_id

    async def test_list_teams_by_workspace(self, client, auth_headers):
        create = await client.post("/api/v3/workspaces", json={"name": "List Teams WS"}, headers=auth_headers)
        ws_id = create.json()["data"]["id"]

        await client.post("/api/v3/teams", json={"name": "Team A", "workspace_id": ws_id}, headers=auth_headers)
        await client.post("/api/v3/teams", json={"name": "Team B", "workspace_id": ws_id}, headers=auth_headers)

        resp = await client.get(f"/api/v3/teams?workspace_id={ws_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

class TestBilling:
    async def test_get_billing_free_tier(self, client, auth_headers):
        create = await client.post("/api/v3/workspaces", json={"name": "Billing WS"}, headers=auth_headers)
        ws_id = create.json()["data"]["id"]

        # NOTE: requires WORKSPACES_V3_BILLING flag enabled in test setup
        resp = await client.get(f"/api/v3/workspaces/{ws_id}/billing", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()["data"]
            assert data["plan"] == "free"
            assert data["member_limit"] == 5
```
```

### 8.3 E2E Scenarios (Playwright + Manual)

1. **Full invitation flow:** Owner creates workspace → sends invite → invitee receives email → clicks link → accepts → appears in member list
2. **Ownership transfer:** Owner → Settings → "Transfer" → selects member → confirms 2FA → new owner has full control
3. **Viewer role restriction:** Viewer can read workspace → tries to invite → 403 → tries to change settings → 403
4. **Team management:** Create "Engineering" and "Design" teams → add members → remove member → delete team
5. **Billing upgrade:** Free workspace → Upgrade to Pro → PayPal flow → billing page shows Pro plan

### 8.4 Mock Strategies

```python
# Mock email service for invitation tests
@pytest.fixture
def mock_email_service(mocker):
    mock = mocker.patch("app.services.invitation_email_service.send_invitation_email")
    mock.return_value = {"success": True, "message_id": "msg_test123"}
    return mock

# Mock PayPal for billing tests
@pytest.fixture
def mock_paypal(mocker):
    mock = mocker.patch("app.services.paypal_service.create_checkout_session")
    mock.return_value = {"checkout_url": "https://sandbox.paypal.com/checkout?token=test"}
    return mock
```

---

## 9. Rollback Plan

### Stage Summary

| Stage | Rollout % | Duration | Trigger to Rollback |
|-------|-----------|----------|---------------------|
| 1 | 5% new workspaces | 48h | Invite email delivery failure > 5% |
| 2 | 25% new workspaces | 72h | Member count accuracy issues |
| 3 | 50% | 168h | Ownership transfer bugs |
| 4 | 100% | Permanent | Catastrophic data corruption |

### Stage 1 Rollback (5% — Low Risk)

**Trigger:** Invitation emails bounce rate > 5% or SMTP failures
**Action:**
1. Set `WORKSPACES_V3_ENDPOINTS = false`
2. Set `WORKSPACES_V3_INVITES = false`
3. Users who created workspaces in v3 keep them (data persisted)
4. Pending invitations remain in DB but no new ones sent

### Stage 2 Rollback (25% — Medium Risk)

**Action:**
1. Set `WORKSPACES_V3_ENDPOINTS = false`
2. No data loss — workspaces, members, teams all persist
3. Users fall back to v2 endpoints for all workspace operations

### Stage 3–4 Rollback (50–100%)

**Action:**
1. `WORKSPACES_V3_ENDPOINTS = false`
2. If teams are at top-level in production: set `WORKSPACES_V3_TEAMS_TOPLEVEL = false` — frontend falls back to v2 `/workspaces/{id}/teams`
3. `UPDATE workspace_activity_log` is not needed (just stops being written)
4. No DB migration rollback needed — all changes are additive

### Instant Rollback Command

```bash
docker compose exec backend python -c "
from app.database import AsyncSessionLocal
from sqlalchemy import text
import asyncio

async def rollback():
    async with AsyncSessionLocal() as db:
        await db.execute(text(\"UPDATE feature_flags SET enabled_globally = false WHERE key LIKE 'WORKSPACES_V3_%'\""))
        await db.commit()
    print('Workspaces v3 rolled back')

asyncio.run(rollback())
"
```

---

## 10. Week-by-Week Breakdown (6 Weeks)

### Week 1: Models + DB Migration + Schemas

**Goal:** New tables and columns exist; all Pydantic schemas code-complete.

- [ ] Add columns to `workspaces`: `logo_url`, `settings`, `member_limit`, `storage_used_bytes`
- [ ] Create `workspace_activity_log` table
- [ ] Write Alembic migration
- [ ] Run migration on dev DB
- [ ] Create `schemas/workspace_v3.py` — all request/response schemas
- [ ] Write unit tests for schemas (section 8.1)
- [ ] Enhance `models/workspace_models.py` — add new column definitions
- [ ] Seed feature flags in migration

### Week 2: Core Workspace CRUD + Member Management

**Goal:** Workspace CRUD and member management endpoints working end-to-end.

- [ ] Create `api/v3/workspaces.py` — WS CRUD + member management
- [ ] Implement `services/workspace_v3_service.py` — core business logic
- [ ] Implement `_check_workspace_access()` with role hierarchy (viewer/member/admin/owner)
- [ ] Register v3 workspace routers in `main_fastapi.py`
- [ ] Add `?include=user` query param support to member listing
- [ ] Write integration tests for CRUD + member management
- [ ] Manual smoke test: create → update → add member → remove member → delete

### Week 3: Invitations + Email Service

**Goal:** Full invitation flow with email delivery operational.

- [ ] Create `api/v3/workspace_invitations.py` — invitation CRUD + accept
- [ ] Implement `services/invitation_email_service.py` — Resend/SMTP integration
- [ ] Create HTML email template (`templates/emails/workspace_invitation.html`)
- [ ] Create plain text fallback (`templates/emails/workspace_invitation.txt`)
- [ ] Implement invitation token generation and validation
- [ ] Implement bounce handling (webhook receiver for Resend bounce events)
- [ ] Implement rate limiting for invitation sending (50/hr per workspace)
- [ ] Write integration tests for invitation flow (section 8.2)
- [ ] Set up Resend API key in dev/staging
- [ ] **Enable `WORKSPACES_V3_INVITES` flag** for dev workspace

### Week 4: Teams Extraction + Billing + Audit Log

**Goal:** Teams at top-level; billing endpoints functional; audit log operational.

- [ ] Create `api/v3/teams.py` — top-level team CRUD
- [ ] Create `api/v3/workspace_billing.py` — billing endpoints
- [ ] Create `api/v3/workspace_audit.py` — audit log endpoints
- [ ] Write audit events for: member invited, member joined, member removed, role changed, workspace updated, ownership transferred
- [ ] Integrate with PayPal service (existing `paypal_service.py`) for billing
- [ ] Write integration tests for teams, billing, audit
- [ ] Enable `WORKSPACES_V3_TEAMS_TOPLEVEL`, `WORKSPACES_V3_BILLING`, `WORKSPACES_V3_AUDIT`
- [ ] **Stage 1 canary: 5% new workspaces**

### Week 5: Ownership Transfer + Frontend Alignment

**Goal:** Ownership transfer operational; frontend team integrating.

- [ ] Implement `POST /workspaces/{id}/transfer-ownership` (with 2FA confirmation)
- [ ] Implement workspace settings validation (allowed keys, value types)
- [ ] Write integration tests for ownership transfer
- [ ] Publish frontend contract (section 7) — coordinate on API client changes
- [ ] Support frontend team with invitation link format, accept flow
- [ ] **Stage 2 canary: 25% new workspaces**
- [ ] Monitor: invitation acceptance rate, bounce rate, member count accuracy

### Week 6: Full Rollout + Monitoring + Polish

**Goal:** 100% rollout; monitoring live; edge cases resolved.

- [ ] Enable `WORKSPACES_V3_ENDPOINTS = true` globally (100%)
- [ ] Monitor metrics:
  - Workspace creation rate
  - Invitation send success rate (target: > 99%)
  - Invitation acceptance rate
  - Member count accuracy (vs v2 member count)
  - Billing checkout completion rate
- [ ] Add alerts:
  - `workspace_invite_bounce_rate > 5%` → Slack
  - `workspace_ownership_transfer_failure > 1%` → PagerDuty
- [ ] Load test: 50 workspace creations/sec → verify
- [ ] Bug bash: all tests pass at 100%
- [ ] Clean up any v2 migration edge cases
- [ ] Mark v2 workspace endpoints as deprecated
- [ ] Run `PROD_READY` checklist: all integration tests green, no known bugs, logging verified, alerts configured

---

## 11. Invitation Email Flow

### Architecture

```
POST /workspaces/{id}/invitations
    │
    ├── Validation: email, role, member_limit check, rate limit
    ├── DB: INSERT workspace_invitations (token, email, role, expires_at, invited_by)
    ├── Audit: INSERT workspace_activity_log (action='member.invited')
    │
    └── Email dispatch (background task):
        │
        ├── Resend API (primary):
        │   POST https://api.resend.com/emails
        │   Headers: Authorization: Bearer {RESEND_API_KEY}
        │   Body: { from, to, subject, html, text }
        │
        └── SMTP fallback (if Resend fails):
            smtplib.SMTP → SMTP_HOST:SMTP_PORT
```

### SMTP Setup (Resend primary, SMTP fallback)

```python
# services/invitation_email_service.py

import resend
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import settings

resend.api_key = settings.RESEND_API_KEY

async def send_invitation_email(
    to_email: str,
    workspace_name: str,
    inviter_name: str,
    role: str,
    invite_url: str,
    message: str | None = None,
) -> dict:
    """Send workspace invitation email. Returns delivery status."""
    
    subject = f"{inviter_name} invited you to {workspace_name} on Flowmanner"
    
    # Load and populate templates
    html_body = _render_html_template(...)
    text_body = _render_text_template(...)
    
    # Primary: Resend API
    if settings.RESEND_API_KEY:
        try:
            response = resend.Emails.send({
                "from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>",
                "to": [to_email],
                "subject": subject,
                "html": html_body,
                "text": text_body,
            })
            return {"success": True, "message_id": response["id"], "provider": "resend"}
        except Exception as e:
            logger.warning(f"Resend failed, falling back to SMTP: {e}")
    
    # Fallback: SMTP
    if settings.SMTP_HOST:
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>"
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))
            
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                if settings.SMTP_USERNAME:
                    server.starttls()
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)
            
            return {"success": True, "message_id": None, "provider": "smtp"}
        except Exception as e:
            logger.error(f"SMTP delivery failed: {e}")
            return {"success": False, "error": str(e), "provider": None}
    
    return {"success": False, "error": "No email provider configured"}
```

### Email Template (`templates/emails/workspace_invitation.html`)

```html
<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 40px 20px;">
  <div style="max-width: 560px; margin: 0 auto; background: #16213e; border: 1px solid #2a2a4a; border-radius: 12px; padding: 40px;">
    <div style="text-align: center; margin-bottom: 32px;">
      <h1 style="color: #6c63ff; font-size: 24px; margin: 0;">Flowmanner</h1>
    </div>
    
    <h2 style="color: #e0e0e0; font-size: 20px; margin: 0 0 8px 0;">
      {{inviter_name}} invited you to join {{workspace_name}}
    </h2>
    
    <p style="color: #b0b0b0; font-size: 14px; line-height: 1.6; margin: 0 0 24px 0;">
      You've been invited as a <strong>{{role}}</strong> to collaborate on {{workspace_name}}.
    </p>
    
    {{#message}}
    <blockquote style="border-left: 3px solid #6c63ff; margin: 0 0 24px 0; padding: 12px 16px; background: #1a1a2e; border-radius: 0 8px 8px 0;">
      <p style="color: #b0b0b0; font-size: 14px; font-style: italic; margin: 0;">{{message}}</p>
    </blockquote>
    {{/message}}
    
    <a href="{{invite_url}}" style="display: inline-block; background: #6c63ff; color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-size: 16px; font-weight: 600; margin-bottom: 24px;">
      Accept Invitation
    </a>
    
    <p style="color: #888; font-size: 12px; margin: 0 0 8px 0;">
      This invitation expires in 7 days.
    </p>
    <p style="color: #888; font-size: 12px; margin: 0;">
      If you don't have a Flowmanner account, you'll be prompted to create one.
    </p>
    
    <hr style="border: none; border-top: 1px solid #2a2a4a; margin: 32px 0 0 0;">
    <p style="color: #666; font-size: 11px; margin: 8px 0 0 0;">
      This email was sent by {{inviter_name}} via Flowmanner. If you weren't expecting this invitation, you can safely ignore it.
    </p>
  </div>
</body>
</html>
```

### Bounce Handling

Resend webhook receiver endpoint (can be added to `api/v3/workspace_webhooks.py`):

```
POST /api/v3/webhooks/resend/bounce
- Receives Resend bounce events
- Marks invitation as "bounced"
- Logs bounce to workspace_activity_log
- (Future: notify workspace admin of bounce)
```

### Rate Limiting

```python
# Invitation rate limit: 50 invites per workspace per hour
from app.api.middleware.rate_limit_v3 import check_rate_limit

allowed, remaining, retry_after = check_rate_limit(
    f"invite:{workspace_id}",
    max_requests=50,
    window_seconds=3600,
)
if not allowed:
    raise HTTPException(status_code=429, detail=f"Too many invitations. Try again in {retry_after}s")
```

---

## 12. Teams Extraction — Migration Detail

### Current State (v2)

```
GET /api/v2/workspaces/{id}/teams          → List teams in workspace
POST /api/v2/workspaces/{id}/teams         → Create team in workspace
GET /api/v2/workspaces/{id}/teams/{tid}    → (not implemented in v2)
DELETE /api/v2/workspaces/{id}/teams/{tid} → (not implemented in v2)
```

### Target State (v3)

```
GET /api/v3/teams?workspace_id={id}        → List teams in workspace
POST /api/v3/teams                         → Create team (workspace_id in body)
GET /api/v3/teams/{id}                     → Get team detail
PATCH /api/v3/teams/{id}                   → Update team
DELETE /api/v3/teams/{id}                  → Delete team
GET /api/v3/teams/{id}/members             → List team members
POST /api/v3/teams/{id}/members            → Add member to team
DELETE /api/v3/teams/{id}/members/{uid}    → Remove member from team
```

### Implementation

The `teams` table already has `workspace_id` as a FK. No DB migration needed for team data — the change is purely routing.

```python
# api/v3/teams.py

router = APIRouter(prefix="/teams", tags=["v3-teams"])

@router.get("")
async def list_teams(
    workspace_id: str = Query(..., description="Workspace ID"),
    db: AsyncSession = Depends(get_db),
    session: AuthSession = Depends(get_current_session),
):
    """List teams in a workspace. workspace_id is REQUIRED — top-level but workspace-scoped."""
    # Verify workspace access
    await _check_workspace_access(db, workspace_id, session.user_id)
    
    result = await db.execute(select(Team).where(Team.workspace_id == workspace_id))
    teams = result.scalars().all()
    # ... build response with member counts
    return ok(teams_data)
```

### v2 Backward Compatibility

The v2 route `GET /api/v2/workspaces/{id}/teams` continues to work for 90 days. It internally delegates to the same database queries. When `WORKSPACES_V3_TEAMS_TOPLEVEL` is enabled, the frontend switches from v2 to v3 routes.

### Frontend Migration

```typescript
// Before (v2):
const teams = await api.get(`/api/v2/workspaces/${workspaceId}/teams`);

// After (v3):
const teams = await api.get(`/api/v3/teams`, { params: { workspace_id: workspaceId } });
```

---

## 13. Observability & Logging

### 13.1 Structured Logging

All v3 workspace endpoints emit structured logs reusing the Auth v3 trace context:

```json
{
  "timestamp": "2026-06-08T12:00:00.000Z",
  "level": "INFO",
  "service": "workspaces-v3",
  "trace_id": "trc_abc123",
  "user_id": 42,
  "workspace_id": "ws_xyz",
  "endpoint": "POST /api/v3/workspaces/ws_xyz/invitations",
  "status_code": 201,
  "duration_ms": 120,
  "action": "member.invited",
  "message": "Invitation sent to colleague@example.com"
}
```

### 13.2 Key Metrics

| Metric | Type | Alert Threshold |
|--------|------|-----------------|
| `workspace_create_total` | Counter | — |
| `workspace_invite_sent_total` | Counter | — |
| `workspace_invite_bounce_rate` | Gauge | > 5% → Slack |
| `workspace_invite_accept_rate` | Gauge | < 50% over 7d → investigate |
| `workspace_member_count_accuracy` | Gauge | Any mismatch → Slack |
| `workspace_ownership_transfer_total` | Counter | > 1% failure → PagerDuty |
| `workspace_audit_events_total` | Counter | — |

### 13.3 Alerts

| Alert | Condition | Channel |
|-------|-----------|---------|
| Invite bounce rate spike | > 5% over 1 hour | Slack #alerts |
| Invite email delivery failure | Any SMTP/Resend error | Slack #eng |
| Ownership transfer failure | Any failure (rollback on error) | PagerDuty |
| Member count drift | Workspace member_count ≠ actual count | Slack #data-integrity |

---

## Appendix A: v2 → v3 Curl Diffs

```bash
# ── Create Workspace ──
# v2:
curl -X POST https://flowmanner.com/api/v2/workspaces \
  -H "Authorization: Bearer <token>" \
  -d '{"name": "My Team", "slug": "my-team"}'

# v3 (same shape):
curl -X POST https://flowmanner.com/api/v3/workspaces \
  -H "Authorization: Bearer <token>" \
  -d '{"name": "My Team", "slug": "my-team"}'

# ── List Members ──
# v2 (always inlines user data):
curl https://flowmanner.com/api/v2/workspaces/ws_abc/members \
  -H "Authorization: Bearer <token>"
# → [{ id: 1, user_id: 42, user_email: "a@b.com", ... }]

# v3 (optional inline via ?include=user):
curl https://flowmanner.com/api/v3/workspaces/ws_abc/members \
  -H "Authorization: Bearer <token>"
# → [{ user_id: 42, role: "owner", joined_at: "..." }]

curl "https://flowmanner.com/api/v3/workspaces/ws_abc/members?include=user" \
  -H "Authorization: Bearer <token>"
# → [{ user_id: 42, email: "a@b.com", full_name: "A", role: "owner", ... }]

# ── Invite Member (NEW in v3) ──
curl -X POST https://flowmanner.com/api/v3/workspaces/ws_abc/invitations \
  -H "Authorization: Bearer <token>" \
  -d '{"email": "colleague@example.com", "role": "member", "message": "Join our workspace!"}'

# ── Accept Invitation (NEW in v3) ──
curl -X POST https://flowmanner.com/api/v3/workspaces/ws_abc/invitations/inv_xyz/accept \
  -H "Authorization: Bearer <token>" \
  -d '{"token": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"}'

# ── Transfer Ownership (NEW in v3) ──
curl -X POST https://flowmanner.com/api/v3/workspaces/ws_abc/transfer-ownership \
  -H "Authorization: Bearer <token>" \
  -d '{"new_owner_user_id": 99, "two_fa_code": "123456"}'

# ── Teams (now top-level) ──
# v2:
curl https://flowmanner.com/api/v2/workspaces/ws_abc/teams

# v3:
curl "https://flowmanner.com/api/v3/teams?workspace_id=ws_abc"
```

---

## Appendix B: Invitation Token Lifecycle

```
Create invitation:
  1. Generate 64-char hex token (os.urandom(32).hex())
  2. Hash with SHA-256 → store in workspace_invitations.token
  3. Set expires_at = NOW() + INVITE_EXPIRY_DAYS (default: 7 days)
  4. Send email with token in URL
  5. Status: 'pending'

Accept invitation:
  1. Validate token (SHA-256 match against stored hash)
  2. Check expires_at > NOW()
  3. Check status == 'pending'
  4. Check member_limit not reached
  5. Create WorkspaceMember record
  6. Set status = 'accepted', accepted_at = NOW()
  7. Log to workspace_activity_log

Expiry (background task or on-access):
  1. Check expires_at < NOW() AND status == 'pending'
  2. Set status = 'expired'

Revoke (manual):
  1. Owner/admin calls DELETE /invitations/{id}
  2. Set status = 'revoked'
  3. Token becomes invalid immediately
```
