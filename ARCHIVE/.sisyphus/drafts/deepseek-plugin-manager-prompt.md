# DeepSeek Build Prompt — Plugin Manager

You are a senior frontend engineer building a new page for **FlowManner**, an
agentic AI workflow platform. Your task is to build the **Plugin Manager** — a
new dashboard page that replaces the existing static Extensions page with a
fully wired plugin catalog supporting upload, health monitoring, enable/disable,
stats, test execution, and admin review.

This is the **third and final feature** in a frontend wiring roadmap. Features 1
(Reliability Center) and 2 (Tool Routing Inspector) are already built and
committed. Match their style exactly.

## Machine context

- You are on the **homelab** (172.16.1.1 / 10.99.0.3).
- **Frontend source** (edit here): `/home/glenn/FlowmannerV2-frontend/`
- **Backend source** (read-only reference): `/opt/flowmanner/backend/`
- Do NOT deploy. Do NOT run `deploy-frontend.sh`. Just build and verify locally.

## Design decision: Plugins vs Extensions

The codebase has **two separate extension systems**:

1. **Extensions** (`/api/extensions`) — a simpler system. The page at
   `src/app/[locale]/extensions/` uses raw `fetch()`, manual auth tokens,
   `prompt()` for install, and hardcoded English strings. **Do NOT touch this
   page** — leave it as-is.

2. **Plugins** (`/api/v1/plugins`) — the complete system (853 lines, Phase
   9.5/9.6). Has install from `.fmp` packages, health monitoring, admin review
   workflow, security scanning, kill-switch, and a proper data model. This is
   what you're wiring up.

You are building a **new page at `/plugins`** (under the dashboard group). The
existing `plugins-api.ts` file already has most of the API functions written.

## Backend API (already complete — do not modify)

Read `/opt/flowmanner/backend/app/api/v1/plugins.py` to see the exact endpoint
contracts. The router is mounted at `/api/v1/plugins` (with prefix `/plugins`
in the router + `/api/v1` from the app mount).

**IMPORTANT:** All list/detail endpoints are workspace-scoped via the
`X-Workspace-Id` header (derived from `get_workspace_id` dependency). The
existing `plugins-api.ts` handles this for install; the `apiClient` methods
(GET/PATCH/DELETE) inject auth automatically but do NOT send the workspace
header. You need to pass it explicitly.

### Regular endpoints

#### GET /api/v1/plugins
List installed plugins for the current workspace.
- Query param: `?status=<status>` (optional filter)
- Response: `{ items: PluginResponse[], total: number }`

Each `PluginResponse`:
```typescript
{
  id: string;
  name: string;
  version: string;
  description: string | null;
  author: string | null;
  source: string;              // "upload", "marketplace", etc.
  status: string;              // "enabled", "disabled", "error", "installed", "loaded"
  execution_count: number;
  error_count: number;
  last_executed_at: string | null;
  last_error: string | null;
  permissions: string[];
  node_types: Record<string, unknown>[];
  default_prompts: string[];
  created_at: string;
  updated_at: string;
}
```

#### POST /api/v1/plugins
Install a plugin from an uploaded `.fmp` package.
- Body: `multipart/form-data` with `file` field (must end in `.fmp`)
- Response: `PluginResponse` (201 Created)
- **This is NOT a JSON request** — it's a file upload. Use FormData. The
  existing `installPlugin()` in `plugins-api.ts` already handles this but uses
  `localStorage` for the workspace header — you'll fix that (see below).

#### GET /api/v1/plugins/{plugin_id}
Get a single plugin by ID.
- Response: `PluginResponse`

#### GET /api/v1/plugins/{plugin_id}/status
Get plugin health and execution stats.
- Response: `PluginStatusResponse`:
```typescript
{
  id: string;
  name: string;
  version: string;
  status: string;
  health: "healthy" | "degraded" | "unhealthy";
  execution_count: number;
  error_count: number;
  error_rate: number;            // 0–100
  last_executed_at: string | null;
  last_error: string | null;
  registered_node_types: string[];
}
```

#### PATCH /api/v1/plugins/{plugin_id}
Enable or disable a plugin.
- Body: `{ enabled: boolean }`
- Response: `PluginResponse`

#### DELETE /api/v1/plugins/{plugin_id}
Uninstall a plugin.
- Response: `{ status: "uninstalled", plugin_id: string }`

#### POST /api/v1/plugins/{plugin_id}/execute
Test-execute a plugin node.
- Body: `{ node_type_id: string, inputs: Record<string, unknown>, config?: Record<string, unknown> }`
- Response: `{ success: boolean, output?: Record<string, unknown>, error?: string, elapsed_ms: number, plugin?: string }`
- Plugin must be enabled (status `"enabled"`), else 400.

#### POST /api/v1/plugins/{plugin_id}/upgrade
Upgrade a plugin to a newer version from a new `.fmp` package.
- Body: `multipart/form-data` with `file` field
- Response: `PluginResponse`

#### GET /api/v1/plugins/node-types
List all available plugin node types across all plugins.
- Response: `NodeTypeResponse[]`
- Useful for showing what capabilities installed plugins provide.

### Admin-only endpoints (require `user.is_admin`)

All admin endpoints return 403 if `user.is_admin` is false. Gate the admin
section behind `user?.is_admin` from the auth store.

#### GET /api/v1/plugins/admin/pending
List plugins pending admin review.
- Response: `PluginListResponse` (same shape as list)

#### GET /api/v1/plugins/admin/health-report
Aggregated health report across ALL plugins.
- Response: `PluginHealthReport`:
```typescript
{
  total_plugins: number;
  healthy: number;
  degraded: number;
  unhealthy: number;
  pending_review: number;
  avg_error_rate: number;
  top_crashing: { name: string; version: string; crash_count: number; error_rate: number; workspace_id: string }[];
}
```

#### POST /api/v1/plugins/{plugin_id}/approve
Approve a plugin. Admin-only.

#### POST /api/v1/plugins/{plugin_id}/reject
Reject a plugin with reason. Body: `{ reason?: string }`. Admin-only.

#### POST /api/v1/plugins/{plugin_id}/kill-switch
Emergency kill-switch — disables a plugin across ALL workspaces.
Body: `{ reason?: string }`. Admin-only.
Response: `{ status: "disabled", plugin_name: string, instances_disabled: number, reason: string | null }`

#### POST /api/v1/plugins/{plugin_id}/scan
Run security scan on an installed plugin. Admin-only.
Response: `ScanResultResponse`:
```typescript
{
  risk_score: number;           // 0–100
  passed: boolean;
  findings_count: number;
  findings: Record<string, unknown>[];
  declared_permissions: string[];
  detected_permissions: string[];
  undeclared_permissions: string[];
  files_scanned: number;
}
```

## Existing code to study and use

1. **`src/lib/plugins-api.ts`** — **ALREADY EXISTS.** Most API functions are
   here: `fetchPlugins`, `getPlugin`, `executePlugin`, `installPlugin`,
   `togglePlugin`, `uninstallPlugin`. **Use these functions directly** — do NOT
   duplicate them in your component. However, you need to add the missing
   functions for admin endpoints and upgrade (see below).

2. **`src/app/[locale]/(dashboard)/tool-routing/page-client.tsx`** — the feature
   built just before this one. Match its layout, header, glass-card style,
   loading states. It was built by another agent and verified clean.

3. **`src/app/[locale]/(dashboard)/reliability/page-client.tsx`** — Feature 1,
   same style.

4. **`src/app/[locale]/(dashboard)/admin/admin-dashboard-content.tsx`** — the
   admin dashboard. Shows the card-grid pattern, admin section links, and how
   `useAuth()` provides `user.is_admin`.

5. **`src/app/[locale]/(dashboard)/admin/features/admin-features-page-content.tsx`**
   — table layout with toggle/delete actions, create modal, toast feedback.
   Match this for the plugin list table.

6. **`src/stores/workspace-store.ts`** — Zustand store for active workspace.

7. **`src/lib/api-client.ts`** — the API client. For most calls use
   `apiClient.get/post/patch/delete`. Auth JWT is injected automatically.

## What to build

### 1. Fix `plugins-api.ts` (add missing functions + fix workspace header)

The existing `plugins-api.ts` has most functions but is missing admin endpoints,
upgrade, and the workspace header. Make these changes:

**a)** Add workspace header support to all apiClient calls. The backend reads
`X-Workspace-Id` via `get_workspace_id`. Add an optional `workspaceId` param to
`fetchPlugins`:

```typescript
export async function fetchPlugins(params?: {
  status?: string;
  workspaceId?: string;
}): Promise<{ items: PluginResponse[]; total: number }> {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  const qs = sp.toString();
  return apiClient.get(`${BASE}${qs ? "?" + qs : ""}`, {
    headers: params?.workspaceId ? { "X-Workspace-Id": params.workspaceId } : undefined,
  });
}
```

**b)** Fix `installPlugin` — replace the `localStorage.getItem` hack with a
passed-in workspace ID:

```typescript
export async function installPlugin(file: File, workspaceId?: string): Promise<PluginResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const token = await getAuthToken();
  const res = await fetch(BASE, {
    method: "POST",
    body: formData,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(workspaceId ? { "X-Workspace-Id": workspaceId } : {}),
    },
    credentials: "include",
  });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}
```

(Import `getAuthToken` from `@/lib/get-auth-token` — it's already imported at the
top of the file.)

**c)** Add the missing API functions:

```typescript
// Plugin status/health
export async function getPluginStatus(pluginId: string): Promise<PluginStatusResponse> {
  return apiClient.get<PluginStatusResponse>(`${BASE}/${pluginId}/status`);
}

// Upgrade plugin
export async function upgradePlugin(pluginId: string, file: File, workspaceId?: string): Promise<PluginResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const token = await getAuthToken();
  const res = await fetch(`${BASE}/${pluginId}/upgrade`, {
    method: "POST",
    body: formData,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(workspaceId ? { "X-Workspace-Id": workspaceId } : {}),
    },
    credentials: "include",
  });
  if (!res.ok) throw new Error(`Upgrade failed: ${res.status}`);
  return res.json();
}

// Node types
export async function fetchPluginNodeTypes(): Promise<PluginNodeType[]> {
  return apiClient.get<PluginNodeType[]>(`${BASE}/node-types`);
}

// ── Admin endpoints ──
export async function fetchPendingPlugins(): Promise<{ items: PluginResponse[]; total: number }> {
  return apiClient.get(`${BASE}/admin/pending`);
}
export async function fetchPluginHealthReport(): Promise<PluginHealthReport> {
  return apiClient.get(`${BASE}/admin/health-report`);
}
export async function approvePlugin(pluginId: string): Promise<PluginResponse> {
  return apiClient.post<PluginResponse>(`${BASE}/${pluginId}/approve`);
}
export async function rejectPlugin(pluginId: string, reason?: string): Promise<PluginResponse> {
  return apiClient.post<PluginResponse>(`${BASE}/${pluginId}/reject`, reason ? { reason } : {});
}
export async function killSwitchPlugin(pluginId: string, reason?: string): Promise<{ status: string; plugin_name: string; instances_disabled: number; reason: string | null }> {
  return apiClient.post(`${BASE}/${pluginId}/kill-switch`, reason ? { reason } : {});
}
export async function scanPlugin(pluginId: string): Promise<ScanResultResponse> {
  return apiClient.post<ScanResultResponse>(`${BASE}/${pluginId}/scan`);
}
```

Add the missing TypeScript interfaces at the top of the file (`PluginStatusResponse`,
`PluginHealthReport`, `ScanResultResponse`). Infer the shapes from the backend
schemas above.

### 2. Page route (2 files)

**`src/app/[locale]/(dashboard)/plugins/page.tsx`** (server component):
```tsx
import { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import PluginsPageClient from "./page-client";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("pluginManager");
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
  };
}

export default function Page() {
  return <PluginsPageClient />;
}
```

**`src/app/[locale]/(dashboard)/plugins/page-client.tsx`** (`"use client"`):
The main component with **three sections**:

#### Section A: Plugin List (primary — all users)

- Fetch `fetchPlugins({ workspaceId })` on mount (derive workspace from store)
- Display as a table or card grid (match admin-features-page-content style):
  - Plugin name + version + author
  - Health badge (derive from status: `enabled` = green, `disabled` = grey,
    `error` = red, `installed`/`loaded` = blue)
  - Execution count + error count
  - Enable/disable toggle (PATCH)
  - Uninstall button (DELETE) with confirmation dialog
  - Expandable detail row: permissions, node_types, last_error, timestamps
- Upload `.fmp` button → hidden `<input type="file" accept=".fmp">` →
  `installPlugin(file, workspaceId)` → toast + refresh list
- Loading state, empty state, error state
- Refresh button

#### Section B: Test Execution (secondary — per-plugin)

- When a plugin is expanded/selected, show a test execution panel:
  - Dropdown of the plugin's `node_types` (if any)
  - JSON textarea for inputs (default `{}`)
  - "Execute" button → `executePlugin(pluginId, { node_type_id, inputs })`
  - Show output JSON or error, elapsed_ms

#### Section C: Admin Panel (admin-only — conditionally rendered)

- Gate behind `user?.is_admin` from `useAuth()`
- **Health report summary**: fetch `fetchPluginHealthReport()` → show stat cards
  (total, healthy, degraded, unhealthy, pending_review, avg_error_rate)
- **Pending review queue**: fetch `fetchPendingPlugins()` → table with
  approve/reject buttons
- **Per-plugin admin actions** (in the plugin list for admin users):
  - Scan button → `scanPlugin(id)` → show scan results modal
  - Kill-switch button → confirmation dialog with reason input →
    `killSwitchPlugin(id, reason)` → toast + refresh

If the user is NOT admin, Section C is completely hidden. Do not render it.

### 3. i18n keys

Add a `pluginManager` namespace to ALL 5 locale files:
`src/i18n/locales/{en,de,es,fr,ja}.json`

Minimum keys needed (translate properly for each language):
```json
{
  "pluginManager": {
    "metaTitle": "Plugin Manager — FlowManner",
    "metaDescription": "Install, monitor, and manage FlowManner plugins",
    "title": "Plugin Manager",
    "subtitle": "Install, monitor, and manage plugins",
    "plugins": "Plugins",
    "noPlugins": "No plugins installed",
    "noPluginsDescription": "Install a .fmp package to extend FlowManner with custom capabilities",
    "installPlugin": "Install Plugin",
    "uploadFmp": "Upload .fmp Package",
    "selectFile": "Select .fmp file",
    "installing": "Installing…",
    "installSuccess": "Plugin installed successfully",
    "installError": "Failed to install plugin",
    "loadError": "Failed to load plugins",
    "refresh": "Refresh",
    "name": "Name",
    "version": "Version",
    "author": "Author",
    "status": "Status",
    "health": "Health",
    "executions": "Executions",
    "errors": "Errors",
    "lastExecuted": "Last Executed",
    "lastError": "Last Error",
    "permissions": "Permissions",
    "nodeTypes": "Node Types",
    "actions": "Actions",
    "enable": "Enable",
    "disable": "Disable",
    "enabled": "Enabled",
    "disabled": "Disabled",
    "uninstall": "Uninstall",
    "confirmUninstall": "Are you sure you want to uninstall this plugin?",
    "uninstallSuccess": "Plugin uninstalled",
    "uninstallError": "Failed to uninstall plugin",
    "toggleSuccess": "Plugin status updated",
    "toggleError": "Failed to toggle plugin",
    "testExecution": "Test Execution",
    "selectNodeType": "Select node type",
    "inputs": "Inputs (JSON)",
    "execute": "Execute",
    "executing": "Executing…",
    "executeSuccess": "Execution successful",
    "executeError": "Execution failed",
    "output": "Output",
    "elapsedMs": "Elapsed (ms)",
    "upgrade": "Upgrade",
    "upgradePlugin": "Upgrade Plugin",
    "upgradeSuccess": "Plugin upgraded successfully",
    "upgradeError": "Failed to upgrade plugin",
    "adminPanel": "Admin Panel",
    "healthReport": "Health Report",
    "totalPlugins": "Total Plugins",
    "healthy": "Healthy",
    "degraded": "Degraded",
    "unhealthy": "Unhealthy",
    "pendingReview": "Pending Review",
    "avgErrorRate": "Avg Error Rate",
    "topCrashing": "Top Crashing",
    "reviewQueue": "Review Queue",
    "approve": "Approve",
    "reject": "Reject",
    "approveSuccess": "Plugin approved",
    "rejectSuccess": "Plugin rejected",
    "rejectReason": "Rejection reason (optional)",
    "killSwitch": "Kill Switch",
    "killSwitchConfirm": "EMERGENCY: This will disable the plugin across ALL workspaces immediately. Continue?",
    "killSwitchReason": "Reason (optional)",
    "killSwitchSuccess": "Kill-switch activated",
    "killSwitchError": "Failed to activate kill-switch",
    "scan": "Scan",
    "scanning": "Scanning…",
    "scanResults": "Scan Results",
    "riskScore": "Risk Score",
    "scanPassed": "Passed",
    "scanFailed": "Failed",
    "findings": "Findings",
    "filesScanned": "Files Scanned",
    "declaredPermissions": "Declared Permissions",
    "detectedPermissions": "Detected Permissions",
    "undeclaredPermissions": "Undeclared Permissions",
    "noNodeTypes": "This plugin has no registered node types",
    "cancel": "Cancel",
    "confirm": "Confirm"
  }
}
```

### 4. Navigation

Add a nav entry to `src/components/layout/nav-config.ts`. In the `tools` group
of `topTier`, add a "Plugins" entry after the existing items:

```typescript
{
  id: "tools",
  labelKey: "nav.tools",
  items: [
    { labelKey: "nav.tools", href: "/tools" },
    { labelKey: "nav.toolsHub", href: "/tools/catalog" },
    { labelKey: "nav.memoryInspector", href: "/memory-inspector" },
    { labelKey: "nav.toolRouting", href: "/tool-routing" },
    { labelKey: "nav.plugins", href: "/plugins" },  // ADD THIS
  ],
},
```

Add `nav.plugins` translation key to all 5 locale files under the existing `nav`
namespace (e.g. `"plugins": "Plugins"` for en).

## Must do

- Match the existing codebase style exactly (glass-card, btn-clay, lucide-react
  icons, sonner toasts, next-intl translations).
- Use TypeScript interfaces for all API response shapes.
- **Use the existing functions from `src/lib/plugins-api.ts`** — do NOT
  re-implement them in the component. Add the missing functions to that file.
- Derive `workspaceId` from the workspace Zustand store, NOT from localStorage.
- Derive `user.is_admin` from `useAuth()` (from `@/providers/auth-provider`).
- Handle loading and errors gracefully for all three sections independently.
- The admin section must be completely hidden for non-admin users — not just
  disabled.
- Use `useConfirm()` from `@/components/ui/confirm-dialog` for destructive
  actions (uninstall, kill-switch), matching admin-features-page-content.
- `npx tsc --noEmit` must pass after your changes.
- `npx vitest run` must pass (no test regressions).
- Commit message: `feat(frontend): add plugin manager with health monitoring and admin review`

## Must NOT do

- Do NOT modify any backend files.
- Do NOT run `deploy-frontend.sh` or any deploy commands.
- Do NOT create test files — this is a UI page, not a test task.
- Do NOT add new npm dependencies — use what's already installed.
- Do NOT touch `.env` or credential files.
- Do NOT use `as any` type assertions.
- Do NOT modify the existing extensions page (`src/app/[locale]/extensions/`).
- Do NOT use `React.FC` — use plain function components.
- Do NOT use `localStorage` for workspace ID — use the Zustand store.
- Do NOT use `prompt()` for any user input — use proper modals/dialogs.
- Do NOT define `ADMIN_ONLY_NAV_KEYS` — that constant already exists in
  `floating-nav.tsx`. If you need admin-only nav filtering, use the existing
  one.

## Acceptance criteria

- [ ] `src/app/[locale]/(dashboard)/plugins/page.tsx` exists
- [ ] `src/app/[locale]/(dashboard)/plugins/page-client.tsx` exists
- [ ] `src/lib/plugins-api.ts` updated with missing functions + workspace fix
- [ ] Plugin list fetches from `GET /api/v1/plugins` with workspace header
- [ ] Upload `.fmp` calls `POST /api/v1/plugins` (FormData)
- [ ] Enable/disable calls `PATCH /api/v1/plugins/{id}`
- [ ] Uninstall calls `DELETE /api/v1/plugins/{id}` with confirmation
- [ ] Test execution calls `POST /api/v1/plugins/{id}/execute`
- [ ] Admin section visible only when `user.is_admin` is true
- [ ] Admin health report fetches `GET /api/v1/plugins/admin/health-report`
- [ ] Admin pending review fetches `GET /api/v1/plugins/admin/pending`
- [ ] Admin actions: approve, reject, scan, kill-switch all call correct endpoints
- [ ] `pluginManager` i18n namespace added to all 5 locale files
- [ ] `nav.plugins` key added to `nav` namespace in all 5 locale files
- [ ] Nav entry added to `tools` group in `nav-config.ts`
- [ ] `npx tsc --noEmit` passes
- [ ] `npx vitest run` passes
- [ ] No localStorage usage for workspace ID

## When done

Report:
- Files created/modified (list)
- `npx tsc --noEmit` output (pass/fail)
- `npx vitest run` output (pass/fail)
- Any blockers or notes (especially regarding the upload flow or admin gating)

Do NOT push to origin. Glenn reviews, then Hermes verifies and commits.
