# Draft: Team UI Gap Fixes

## Requirements (confirmed)
- Fix existing gaps in the Team UI that was just built
- User chose "Fix existing gaps" option

## Gaps Identified (verified)
1. **Delete Workspace button** — dead button, no onClick handler (team/page.tsx:619)
2. **No team edit/update** — can create/delete but not rename or update description
3. **No member-to-team assignment** — can't assign existing members to teams
4. **Settings page missing Team link** — /settings page has no Team card

## Technical Decisions
- All changes are in frontend only: `src/app/[locale]/(dashboard)/team/page.tsx` and `src/app/[locale]/(dashboard)/settings/page.tsx`
- Use existing patterns: modals for edit/create, dropdown selects for role/team assignment
- API helpers already exist in workspace-api.ts (teamApi.updateTeam, membershipApi methods)
- Delete workspace API: workspaceApi.deleteWorkspace already exists

## Scope Boundaries
- INCLUDE: The 4 gaps listed above
- EXCLUDE: My Invitations page, link invitation UI, email delivery, team permissions overhaul

---

## CRITICAL: API Path Mismatches (verified)

The frontend `workspace-api.ts` calls paths that **don't match** the backend routes. New UI will 404 without fixing these first.

### Team API Mismatches

| Frontend Method | Frontend Path | Backend Path | Fix |
|---|---|---|---|
| `teamApi.listTeams(wsId)` | `GET /api/workspaces/{wsId}/teams` | `GET /api/teams/{workspace_id}` | Change path |
| `teamApi.getTeam(teamId)` | `GET /api/teams/{teamId}` | `GET /api/teams/{workspace_id}/{team_id}` | Add workspaceId param |
| `teamApi.createTeam(data)` | `POST /api/workspaces/{wsId}/teams` | `POST /api/teams/{workspace_id}` | Change path |
| `teamApi.updateTeam(teamId, data)` | `PATCH /api/teams/{teamId}` | `PATCH /api/teams/{workspace_id}/{team_id}` | Add workspaceId param |
| `teamApi.deleteTeam(teamId)` | `DELETE /api/teams/{teamId}` | `DELETE /api/teams/{workspace_id}/{team_id}` | Add workspaceId param |

### Membership API Mismatches

| Frontend Method | Frontend Path | Backend Path | Fix |
|---|---|---|---|
| `membershipApi.inviteMember()` | `POST /api/workspaces/{id}/members/invite` | No such route | Use `invitationApi.createLinkInvitation()` or redirect to invitation flow |
| `membershipApi.transferOwnership()` | `POST /api/workspaces/{id}/transfer-ownership` | No such route | Feature doesn't exist backend-side; remove or stub |

### Frontend API Methods That DO Work

| Method | Path | Status |
|---|---|---|
| `workspaceApi.deleteWorkspace(id)` | `DELETE /api/workspaces/{id}` | ✅ Matches |
| `workspaceApi.listMyWorkspaces()` | `GET /api/workspaces/my` | ✅ Matches |
| `workspaceApi.createWorkspace(data)` | `POST /api/workspaces` | ✅ Matches |
| `membershipApi.listMembers(wsId)` | `GET /api/workspaces/{id}/members` | ✅ Matches |
| `membershipApi.updateMemberRole(wsId, mId, data)` | `PATCH /api/workspaces/{id}/members/{mId}/role` | ✅ Matches |
| `membershipApi.removeMember(wsId, mId)` | `DELETE /api/workspaces/{id}/members/{mId}` | ✅ Matches |
| `invitationApi.listInvitations(wsId)` | `GET /api/invitations/workspace/{wsId}` | ✅ Matches |
| `invitationApi.cancelInvitation(wsId, invId)` | `DELETE /api/invitations/{invId}?workspace_id={wsId}` | ✅ Matches |
| `invitationApi.resendInvitation(wsId, invId)` | `POST /api/invitations/{invId}/resend?workspace_id={wsId}` | ✅ Matches |

---

## Missing API Methods (need to add to workspace-api.ts)

Backend endpoints exist but have no frontend helper:

| Method Name | Backend Endpoint | Request Body | Purpose |
|---|---|---|---|
| `teamApi.addTeamMember(wsId, teamId, userId)` | `POST /api/teams/{wsId}/{teamId}/members` | `{user_id, role?}` | Gap #3 |
| `teamApi.removeTeamMember(wsId, teamId, userId)` | `DELETE /api/teams/{wsId}/{teamId}/members/{userId}` | — | Gap #3 |
| `teamApi.listTeamMembers(wsId, teamId)` | `GET /api/teams/{wsId}/{teamId}/members` | — | Gap #3 |

---

## Implementation Order

### Phase 0: Fix API paths in workspace-api.ts
**Must happen first** — all team operations will 404 without this.

1. Fix `teamApi.listTeams` — change path from `/api/workspaces/{wsId}/teams` to `/api/teams/{wsId}`
2. Fix `teamApi.getTeam` — add workspaceId param, path becomes `/api/teams/{wsId}/{teamId}`
3. Fix `teamApi.createTeam` — change path from `/api/workspaces/{wsId}/teams` to `/api/teams/{wsId}`
4. Fix `teamApi.updateTeam` — add workspaceId param, path becomes `/api/teams/{wsId}/{teamId}`
5. Fix `teamApi.deleteTeam` — add workspaceId param, path becomes `/api/teams/{wsId}/{teamId}`
6. Add `teamApi.addTeamMember(wsId, teamId, userId)` — `POST /api/teams/{wsId}/{teamId}/members`
7. Add `teamApi.removeTeamMember(wsId, teamId, userId)` — `DELETE /api/teams/{wsId}/{teamId}/members/{userId}`
8. Add `teamApi.listTeamMembers(wsId, teamId)` — `GET /api/teams/{wsId}/{teamId}/members`
9. Update all call sites in team/page.tsx to pass workspaceId

### Phase 1: Gap #1 — Delete Workspace button
- Wire `onClick` handler on team/page.tsx:619
- Call `workspaceApi.deleteWorkspace(activeWorkspace.id)`
- Use `useConfirm()` for confirmation dialog
- After deletion: redirect to `/dashboard` or another workspace, clear workspace store
- Edge case: if this is the user's only workspace, redirect to onboarding or create-workspace flow

### Phase 2: Gap #4 — Settings page Team card
- Add entry to `settings/page.tsx` sections array:
  ```tsx
  { href: "/team", icon: Users, label: "Team", desc: "Manage members, teams, and invitations" }
  ```
- No other changes needed — simplest gap

### Phase 3: Gap #2 — Team edit/update modal
- Add `showEditTeam` state, `editTeamId`, `editTeamName`, `editTeamDesc`
- Add edit button (Pencil icon) to each team card in the Teams tab
- Reuse the Create Team modal pattern with pre-filled values
- Call `teamApi.updateTeam(activeWorkspace.id, teamId, { name, description })`
- After update: close modal, reload data

### Phase 4: Gap #3 — Member-to-team assignment
- Add team assignment UI to the Members tab
- For each member: show current team(s) as badges + a dropdown to assign to team
- Call `teamApi.addTeamMember(activeWorkspace.id, teamId, member.user_id)` on assign
- Call `teamApi.removeTeamMember(activeWorkspace.id, teamId, member.user_id)` on unassign
- Load team members per team or use a combined view

---

## Acceptance Criteria

### Gap #1: Delete Workspace
- [ ] Delete button opens confirmation dialog (useConfirm, destructive variant)
- [ ] On confirm: calls DELETE /api/workspaces/{id}
- [ ] After deletion: redirects to another workspace or create-workspace flow
- [ ] Only visible to owner (already gated by `currentRole === "owner"`)

### Gap #2: Team Edit
- [ ] Edit icon button visible on each team card (for owner/admin)
- [ ] Click opens modal pre-filled with current name and description
- [ ] Save calls PATCH /api/teams/{wsId}/{teamId}
- [ ] Modal closes, team list refreshes

### Gap #3: Member-to-Team Assignment
- [ ] Each member row shows assigned team(s) as badges
- [ ] Dropdown to assign member to a team
- [ ] Remove button to unassign from team
- [ ] Only visible to users with canManageTeams permission

### Gap #4: Settings Team Card
- [ ] Team card appears in settings grid
- [ ] Links to /team
- [ ] Follows existing card pattern exactly

---

## Guardrails

1. **Frontend-only changes** — no new backend endpoints, no schema changes
2. **Fix API paths first** — Phase 0 is mandatory, otherwise gaps 1-3 will hit 404
3. **Reuse modal pattern exactly** — `fixed inset-0 bg-black/50` → `bg-white rounded-2xl p-6 w-full max-w-md`
4. **Use useConfirm() for destructive actions** — not browser confirm()
5. **Preserve RBAC gating** — only show edit/delete/assign UI to owner/admin
6. **Don't change api-client.ts** — only workspace-api.ts and the two page files
7. **Don't add new npm packages** — use existing lucide-react icons, existing patterns

## Edge Cases

1. **Delete last workspace** — user has no workspace after deletion; redirect to onboarding or auto-create new workspace
2. **Team rename collision** — backend doesn't enforce team name uniqueness (unlike workspace slugs); allow duplicates
3. **Member already in team** — backend returns 409 "User is already a team member"; show toast
4. **Workspace with 0 teams** — member assignment dropdown shows "No teams available"
5. **Owner can't delete themselves from workspace** — already handled in existing removeMember logic
