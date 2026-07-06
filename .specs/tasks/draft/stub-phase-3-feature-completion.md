# Task: Phase 3 — Feature Completion

**Status:** DRAFT
**Priority:** P1 — completes partially-built features
**Estimated effort:** 1–2 sessions
**Created:** 2026-07-06
**Audited:** 2026-07-06 (ground-truth verification)
**Source:** `docs/STUB-COMPLETION-PLAN-2026-07-06.md` §Phase 3

---

## Problem

Three features are partially built — the UI exists but the implementation is stubbed:

1. **Canvas `file-diff` tile** — renders "coming soon" stub
2. **Marketplace uninstall** — returns 501
3. **Canvas `mission_status` tile** — renders "coming soon" stub

Additionally, `image-gen` tile (4.4 in the plan) shares the same stub pattern in `Canvas.tsx:182-184`.

---

## ⚠️ Critical Context Corrections

### 3.1 (file-diff tile):
- **No `tiles/` directory exists.** Create `src/components/chat/tiles/` first.
- **`react-diff-viewer-continued` is NOT installed.** Need `pnpm add`.
- **No sandbox diff API endpoint was found in the backend** (`grep` for "diff" in `backend/app/api/v1/` returned nothing). The diff data source needs investigation. Likely approach: the tile receives old/new file content strings in its payload and does client-side diff rendering.
- **Canvas.tsx stub:** Lines 54-67 define `stubMessage` for `file-diff` (line 57: "File diff viewer — coming soon."). Lines 182-184 route `file-diff`, `image-gen`, and `mission_status` all to the same generic stub renderer.

### 3.2 (marketplace uninstall):
- **Model name is `UserInstallationModel`** (not `MarketplaceInstall`). Found at `app/models/models.py:91`.
- **Service is `backend/app/services/nexus/marketplace_db.py`** (not `app/services/marketplace_service.py`). The `app/services/marketplace_service.py` is a different file (seed data only).
- **Install method already exists** at `marketplace_db.py:573` — creates a `UserInstallationModel` row. Uninstall just needs to delete that row.
- **CapabilityEngine does not exist** in the codebase. The uninstall is simply: delete the `UserInstallationModel` row where `user_id` + `listing_id` match.
- **The v2 route** at `v2/marketplace.py:223-231` correctly returns 501 with "Uninstall not yet implemented."

### 3.3 (mission_status tile):
- **`MissionStatusBadge` component does not exist** in the codebase. The tile must render its own status UI.
- **`GET /api/v2/missions/{id}/status` endpoint EXISTS** at `missions.py:336-343`. Returns mission status via CQRS query handler.
- **No `tiles/` directory** — create it or put tile in `src/components/chat/` alongside existing `AgentTraceTile.tsx`, `BrowserSandboxTile.tsx`.

---

## Acceptance Criteria

- [ ] Canvas `file-diff` tile renders actual diffs (client-side or API-backed)
- [ ] Marketplace uninstall endpoint returns 200 (not 501)
- [ ] Canvas `mission_status` tile renders mission status card from real API
- [ ] Frontend typechecks clean
- [ ] All tests pass

---

## Sub-tasks

### 3.1 — Canvas `file-diff` tile

**Current:** `src/components/chat/Canvas.tsx:54-57` (stub message), `:182-184` (stub renderer).

**Steps:**

1. **Install diff library:**
   ```bash
   cd /home/glenn/FlowmannerV2-frontend
   pnpm add react-diff-viewer-continued
   ```

2. **Create tiles directory:**
   ```bash
   mkdir -p src/components/chat/tiles
   ```

3. **Create `src/components/chat/tiles/FileDiffTile.tsx`:**
   - Accept `tile: CanvasTile` prop
   - Extract `payload.oldContent` and `payload.newContent` as strings (client-side diff)
   - Also support `payload.filePath` — if provided, fetch diff from the sandbox API (see investigation note below)
   - Render using `<DiffViewer>` from `react-diff-viewer-continued`
   - Support split-view (side-by-side) and unified (inline) toggle via local state
   - Show file path in header bar
   - Handle loading/error states

4. **Investigate sandbox diff API:**
   ```bash
   grep -rn "diff" backend/app/api/v1/sandbox*.py
   # If no diff endpoint exists, use client-side diff only for now.
   # The payload should contain oldContent + newContent strings.
   ```

5. **Wire into `Canvas.tsx`:**
   - Add import: `import FileDiffTile from "./tiles/FileDiffTile";`
   - Replace lines 182-184: create a separate case for `"file-diff"` that returns `<FileDiffTile tile={tile} />`

**Verify:**
```bash
npx tsc --noEmit && npx vitest run
```

**Commit:** `feat: implement Canvas file-diff tile`

---

### 3.2 — Marketplace uninstall

**⚠️ CORRECTED model and service paths.**

**Current:** `backend/app/api/v2/marketplace.py:223-231` — returns 501.

**Real service:** `backend/app/services/nexus/marketplace_db.py`
**Real model:** `UserInstallationModel` (at `app/models/models.py:91`)
**Install reference:** `marketplace_db.py:573` — `async def install(self, listing_id, user_id)` creates a `UserInstallationModel` row.

**Steps:**

1. **Read the install method** at `marketplace_db.py:573-610` — understand the pattern (it checks for existing install, creates `UserInstallationModel` row, increments `install_count`).

2. **Add `async def uninstall(cls, db, listing_id, user_id)` to `MarketplaceDB` class:**
   ```python
   async def uninstall(self, listing_id: str, user_id: str) -> dict[str, Any]:
       """Uninstall a listing — delete the UserInstallationModel row."""
       from app.models.models import MarketplaceListingModel, UserInstallationModel

       with self._get_session() as db:
           installation = (
               db.query(UserInstallationModel)
               .filter(
                   UserInstallationModel.user_id == user_id,
                   UserInstallationModel.listing_id == listing_id,
               )
               .first()
           )
           if not installation:
               return {"success": False, "error": "Not installed"}

           db.delete(installation)

           # Decrement install count on listing
           listing = db.query(MarketplaceListingModel).filter(
               MarketplaceListingModel.id == listing_id
           ).first()
           if listing and listing.install_count > 0:
               listing.install_count -= 1

           db.commit()
           return {"success": True, "message": "Uninstalled"}
   ```
   **Note:** There is no CapabilityEngine to revoke. The install is purely a DB row.

3. **Replace the 501 in `v2/marketplace.py:223-231`:**
   ```python
   @router.delete("/listings/{listing_id}/install")
   async def uninstall_listing(
       listing_id: str,
       user=Depends(get_current_user),
   ):
       """Uninstall a marketplace listing."""
       service = get_marketplace_service()
       result = await asyncio.to_thread(service.uninstall, listing_id, str(user.id))
       if not result.get("success"):
           raise HTTPException(status_code=400, detail=result.get("error", "Uninstall failed"))
       return ok(result)
   ```

4. **Check `get_marketplace_service()` import** — it comes from `app.services.nexus.marketplace_db`. Verify this at the top of `v2/marketplace.py`:
   ```python
   from app.services.nexus.marketplace_db import get_marketplace_service
   ```

**Verify:**
```bash
curl -X DELETE http://127.0.0.1:8000/api/v2/marketplace/listings/{id}/install \
  -H "Authorization: Bearer ***"
# → 200, not 501
```

**Commit:** `feat: implement marketplace listing uninstall`

---

### 3.3 — Canvas `mission_status` tile

**⚠️ `MissionStatusBadge` does not exist — build from scratch.**

**Steps:**

1. **Create `src/components/chat/tiles/MissionStatusTile.tsx`:**
   - Accept `tile: CanvasTile` prop
   - Extract `payload.missionId` (UUID string)
   - Fetch `GET /api/v2/missions/{missionId}/status` on mount (this endpoint exists at `missions.py:336`)
   - Render a compact status card:
     - Mission title
     - Status badge (build inline — no existing component to reuse)
     - Progress (completed tasks / total tasks — if available in status response)
     - Token usage
     - Elapsed time (started_at → now or completed_at)
   - Auto-refresh while status is active (poll every 5s, stop when status is terminal)
   - Handle loading/error/not-found states

2. **Check the status endpoint response shape:**
   ```bash
   # Read what get_status returns
   grep -A20 "async def get_status" backend/app/api/_mission_cqrs/queries.py
   ```

3. **Wire into `Canvas.tsx`:**
   - Add import: `import MissionStatusTile from "./tiles/MissionStatusTile";`
   - In the switch at lines 182-184, add a separate case for `"mission_status"`:
     ```tsx
     case "mission_status":
       return <MissionStatusTile tile={tile} />;
     ```

**Verify:**
```bash
npx tsc --noEmit && npx vitest run
```

**Commit:** `feat: implement Canvas mission_status tile`

---

## Verification Gate

```bash
# Frontend
cd /home/glenn/FlowmannerV2-frontend
npx tsc --noEmit
npx vitest run

# Backend
cd /opt/flowmanner
docker compose exec backend pytest app/tests/ -q --tb=no 2>&1 | tail -5
```

---

## File Map

| File | Action |
|------|--------|
| `src/components/chat/tiles/` | **NEW** — create tiles directory |
| `src/components/chat/tiles/FileDiffTile.tsx` | **NEW** — file diff viewer tile |
| `src/components/chat/tiles/MissionStatusTile.tsx` | **NEW** — mission status tile |
| `src/components/chat/Canvas.tsx` | Wire `file-diff`, `mission_status` cases (lines 182-184) |
| `backend/app/services/nexus/marketplace_db.py` | Add `uninstall` method (mirrors `install` at line 573) |
| `backend/app/api/v2/marketplace.py` | Replace 501 with real uninstall (line 223-231) |
| `backend/app/models/models.py` | Read `UserInstallationModel` (line 91) |
| `package.json` | Add `react-diff-viewer-continued` |

---

## Risks

| Risk | Mitigation |
|------|------------|
| `react-diff-viewer-continued` may not be React 19 compatible | Check npm page before installing; fallback: simple `<pre>` with syntax highlighting |
| No sandbox diff API exists | Use client-side diff: tile payload should carry `oldContent` + `newContent` strings. The backend can send these as part of tile creation. |
| `UserInstallationModel` uses sync SQLAlchemy session, not async | Follow the existing `install` method pattern exactly — it uses `self._get_session()` context manager |
| `MissionStatusTile` API shape unknown | Read the CQRS query handler at `app/api/_mission_cqrs/queries.py` for `get_status` return shape before building UI |
| `get_marketplace_service()` uses `asyncio.to_thread` for sync methods | The install route already does this — follow the same pattern for uninstall |
