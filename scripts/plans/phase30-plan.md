# Phase 30: Developer Experience & SDK Unification

**Effort:** 3 weeks
**Impact:** High — unblocks all future frontend work

---

## Current State Assessment

### What Exists
- ✅ TypeScript SDK: `/opt/flowmanner/frontend/src/lib/sdk/` (openapi-typescript-codegen, 53+ services)
- ✅ SDK wrapper: `sdk-client.ts` with auth configuration
- ✅ Python SDK: `/opt/flowmanner/sdk-python/flowmanner-api-client/` (openapi-python-client)
- ✅ API versioning middleware: v1 support, v2 framework ready
- ✅ OpenAPI spec: `/opt/flowmanner/openapi.json` (273 paths)
- ✅ Raw apiClient: `api-client.ts` (281 lines, fetch-based)

### What's Missing
- ❌ 46 files still use `apiClient` directly (not SDK)
- ❌ No `/api/v2/` routes (middleware ready, no v2 router)
- ❌ No developer portal
- ❌ No branded API playground
- ❌ No SDK codegen pipeline (manual regeneration)

---

## Week 1: SDK Migration + Codegen Pipeline

### 1A. SDK Code Generation Pipeline
**Goal:** One command regenerates both TS and Python SDKs from OpenAPI spec.

**Files to create/modify:**
- `/opt/flowmanner/Makefile` — add `generate-sdk` target
- `/opt/flowmanner/scripts/generate-ts-sdk.sh` — TS SDK generation script
- `/opt/flowmanner/scripts/generate-python-sdk.sh` — Python SDK generation script
- `/opt/flowmanner/frontend/package.json` — add `openapi-typescript-codegen` devDependency, `sdk:generate` script
- `/opt/flowmanner/sdk-python/pyproject.toml` — ensure openapi-python-client dependency

**Pipeline:**
1. Fetch fresh OpenAPI spec from running backend: `curl http://localhost:8000/openapi.json > openapi.json`
2. Generate TS SDK: `npx @openapitools/openapi-generator-cli generate -i openapi.json -g typescript-axios -o frontend/src/lib/sdk/`
3. Generate Python SDK: `openapi-python-client generate --path openapi.json --output sdk-python/`
4. Commit if changed

### 1B. Frontend SDK Migration (46 files)
**Goal:** Zero direct `apiClient` calls — 100% SDK usage.

**Migration pattern per file:**
```typescript
// BEFORE
import { apiClient } from "@/lib/api-client";
const missions = await apiClient.get<Mission[]>("/api/v1/missions");

// AFTER
import { Missions } from "@/lib/sdk-client";
const missions = await Missions.listMissionsApiV1MissionsGet();
```

**Priority order (by impact):**
1. **lib/ files** (12 files) — shared API modules, highest reuse
   - `auth.ts`, `admin-api.ts`, `orchestration-api.ts`, `mission-builder/api.ts`, etc.
2. **hooks/ files** (7 files) — React hooks used across pages
   - `use-missions.ts`, `use-agents.ts`, `use-notifications.ts`, etc.
3. **lib/ - remaining** (6 files)
   - `usage-api.ts`, `workspace-api.ts`, `billing-api.ts`, etc.
4. **components/ files** (4 files)
   - `newsletter-form.tsx`, `TriggerManagement.tsx`, etc.
5. **app/ page files** (17 files) — individual pages
   - Tools pages, dashboard pages, browser page, etc.

**Key mapping (apiClient → SDK service):**
| apiClient path | SDK Service |
|---|---|
| `/api/v1/auth/*` | `AuthService` |
| `/api/v1/missions/*` | `MissionsService` |
| `/api/v1/agents/*` | `AgentsService` |
| `/api/v1/graphs/*` | `GraphsService` |
| `/api/v1/admin/*` | `AdminService` |
| `/api/v1/analytics/*` | `AnalyticsService` |
| `/api/v1/workspaces/*` | `WorkspacesService` |
| `/api/v1/users/*` | (via Auth or Users) |
| `/api/v1/search` | `SearchService` |
| `/api/v1/notifications/*` | `NotificationsService` |

### 1C. Preserve ApiError compatibility
The SDK throws `ApiError` with different shape than our custom `ApiError` class.
- Create adapter layer in `sdk-client.ts` that maps SDK errors to our `ApiError` shape
- OR update all catch blocks to handle both error types

---

## Week 2: API Versioning v2 + Developer Portal

### 2A. API Versioning v2
**Goal:** `/api/v2/` namespace with header-based negotiation.

**Backend changes:**
- `/opt/flowmanner/backend/app/api/v2/` — new router directory (copy v1 structure)
- `/opt/flowmanner/backend/app/api/v2/__init__.py` — router registration
- `/opt/flowmanner/backend/app/api/middleware/versioning.py` — add "v2" to SUPPORTED_VERSIONS
- `/opt/flowmanner/backend/app/main.py` — mount v2 router

**v2 changes from v1:**
- Standardized response envelope: `{ data, meta, error }`
- Consistent pagination: `{ items, total, page, per_page }`
- ISO 8601 timestamps everywhere
- Remove deprecated fields

### 2B. Developer Portal
**Goal:** Branded developer portal at `/developers` with docs, SDK info, API reference.

**Frontend pages:**
- `/app/[locale]/developers/page.tsx` — portal landing
- `/app/[locale]/developers/docs/page.tsx` — API documentation
- `/app/[locale]/developers/sdk/page.tsx` — SDK guides (TS + Python)
- `/app/[locale]/developers/changelog/page.tsx` — API changelog

**Content:**
- Auto-generated from OpenAPI spec
- SDK installation guides
- Authentication examples
- Rate limiting docs
- Error reference

---

## Week 3: Interactive API Playground

### 3A. Branded API Playground
**Goal:** Custom Swagger-like UI at `/developers/playground` with auth token injection.

**Approach:**
- Use `swagger-ui-react` or build custom UI
- Embed at `/app/[locale]/developers/playground/page.tsx`
- Auto-inject JWT token from localStorage
- Branded with Flowmanner theme
- Try-it-out functionality for all 273 endpoints

### 3B. CI/CD Integration
**Goal:** SDK regeneration on every API change.

**CI changes:**
- Add `sdk:generate` to CI pipeline
- Compare generated SDK with committed version
- Fail build if OpenAPI changed but SDK not regenerated
- Auto-PR option for SDK updates

---

## Success Criteria
- [ ] Frontend: `grep -r 'from.*api-client' src/` returns 0 results
- [ ] `make generate-sdk` regenerates both SDKs in one command
- [ ] `/api/v2/` endpoints functional with version negotiation
- [ ] `/developers` portal accessible with docs, SDK guides, playground
- [ ] CI blocks deployment if SDK out of sync with OpenAPI spec
