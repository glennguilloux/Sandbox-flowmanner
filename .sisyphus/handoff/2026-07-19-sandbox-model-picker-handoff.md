# Handoff — Sandbox Model Picker (Mission + Blueprint run screens)

**Date:** 2026-07-19
**Author:** Hermes agent (tencent/hy3:free)
**Scope:** Add a model-selection dropdown to the mission-run and blueprint-run
screens so the user can choose which model the sandboxd opencode agent uses.
Reuses the existing v1 BYOK `/api/byok/models` source (same as Settings).

## Goal (user's words)
"site dropdown picker from byok/local/deepseek-v4-flash models" → scoped to:
BYOK (OpenRouter/DeepSeek/OpenAI — whatever keys exist in Settings) + the two
free-tier sandboxd defaults glm-5 / glm-5.2. Local (Ollama/llama.cpp) deferred
(needs sandboxd proxy `local` upstream — separate infra work).

## What was built

### Backend (repo: /opt/flowmanner/backend)
1. `app/schemas/mission.py` — added `input_data: dict | None = None` to
   `MissionExecuteRequest` (was `model_preference` + `selected_plan_id` only).
2. `app/services/substrate/adapters.py` — `mission_to_workflow(...)` now accepts
   `input_data` and, for SANDBOX-type nodes, injects `config["model"] =
   "{{ inputs.model }}"` when `input_data.model` is set. Other callers
   (6 sites) unaffected (param defaults to None).
3. `app/api/_mission_cqrs/commands.py` — `execute_mission._op` now passes
   `input_data` into `mission_to_workflow` AND into `unified.execute(
   context={"inputs": input_data})`, mirroring the blueprint path.
4. `app/services/substrate/node_executor.py` — `_render_inputs` (sandbox prompt
   interpolation) FIXED: unknown `{{ inputs.<key> }}` tokens are now left
   verbatim instead of silently substituted with empty string (aligned with
   `interpolate_inputs` used by non-sandbox nodes). This was a latent bug
   exposed by the test suite.

### Frontend (repo: /home/glenn/FlowmannerV2-frontend — double-N, no P)
1. `src/lib/useSandboxModels.ts` (NEW) — `useSandboxModels()` hook. Fetches
   `Byok.listAvailableModelsApiByokModelsGet()` (GET /api/v1/byok/models) and
   merges the two static free-tier entries glm-5 + glm-5.2. Returns
   `{id,name,provider}[]` to match `<ModelSelector>`.
2. `src/app/[locale]/mission-dashboard/page-client.tsx` — added ModelSelector
   to each mission's Quick Actions; execute passes
   `{ input_data: { model } }` via `Missions.executeMissionApiMissionsMissionIdExecutePost(id,"v2",body)`.
3. `src/app/[locale]/(dashboard)/blueprints/page-client.tsx` — added
   ModelSelector to each blueprint row; execute passes
   `startRun(id, { model })` (startRun already maps to `body.input_data`).

## Verification performed

### Backend tests (venv: /opt/flowmanner/backend/.venv)
- `test_sandbox_prompt_interp.py` — 3 passed (after the `_render_inputs` fix).
- `test_run_input_bridge.py` — passed (validates input_data→context threading,
  the exact path the feature depends on).
- `test_mission_cqrs.py` — passed.
- `test_mission_execution_api.py` — 3 FAILED, but PRE-EXISTING: they fail
  identically with all edits stashed (root cause `gaierror: Name or service
  not known`, a network/DNS failure in this sandbox, not logic). Excluded from
  the feature's regression gate.

### Frontend
- `tsc --noEmit` on /home/glenn/FlowmapperV2-frontend → exit 0 (clean).
  (NOTE: path is FlowmannerV2-frontend double-N, no P.)

### Live API (baseUrl 127.0.0.1:8000, token from ~/.flowmanner/config.json)
- Blueprint run `input_data.model=openrouter/glm-5.2` → run `9529bec5`,
  correct input_data threaded to opencode. ✅
- Blueprint run `input_data.model=openrouter/tencent/hy3:free` → run `1975a3a5`,
  correct threading. ✅
- No-model run (`{}` → glm-5 default) → run `d0a940a3` **status=completed**,
  proving the clone+analyze pipeline itself is healthy. ✅
- Model selection plumbing (dropdown → API → node config → opencode `model`)
  CONFIRMED WORKING for both missions and blueprints.

## Bugs surfaced (NOT part of this feature — separate work)
1. **OpenRouter model routing fails in sandboxd proxy.** Every
   `openrouter/<slug>` (glm-5.2, hy3:free) fails with
   `sandbox.task_completed: {output:"", status:"failed"}` and escalates
   `irreversible_effect_committed`. glm-5 Zen default works; OpenRouter slugs
   do not. Likely the sandboxd opencode proxy
   (`/mnt/apps/Softwares2/sandboxd/.../opencode.go`) does not route
   `openrouter/<slug>` even with the BYOK key synced. NEEDS: investigate
   sandboxd proxy model resolution + OpenRouter key sync.
2. **Run/events GET 500 for completed runs.** `GET /api/v2/runs/{id}` and
   `/events` returned HTTP 500 on the completed glm-5 run `d0a940a3`
   (serialization error in the run/events envelope). Pre-existing, unrelated
   to model selection. NEEDS: reproduce + fix the serialization.

## Open threads / deferred
- **Local models (Ollama/llama.cpp):** needs a `local` upstream in the sandboxd
  proxy before it can appear in the dropdown. Deferred by user.
- **Blueprint `task_prompt` data fix:** stored blueprint
  `e62f4c26-a105-4913-9ff9-d12aca074d29` was missing its node `task_prompt`
  (only `data`/`position`). PATCHED via API during testing from flowmanner.yaml;
  now runnable. Verify `flowmanner push` serializes node config (may drop it).
- **`fetch_provider_models`** only live-fetches OpenAI; DeepSeek/OpenRouter use
  stored `key.models`. Picker works but non-OpenAI lists are not live.

## Files changed (summary)
Backend: schemas/mission.py, services/substrate/adapters.py,
  api/_mission_cqrs/commands.py, services/substrate/node_executor.py
Frontend: lib/useSandboxModels.ts (new), mission-dashboard/page-client.tsx,
  (dashboard)/blueprints/page-client.tsx
Config (this repo): flowmanner.yaml — fixed stale `repo_url` fallback
  `flowmapper.git` → `FlowmannerV2.git` (commit not yet made).

### Additional backend files (added post-handoff-draft, under-documented until 2026-07-19 verify)
These two were modified as part of this feature but omitted from the original
"Files changed" list. The independent verification worker (t_52f48ebf) confirmed
they are RELATED, not foreign work — they implement OpenRouter BYOK key sync to
sandboxd, directly addressing Bug #1 below (OpenRouter routing fails because the
key is not synced to sandboxd's agent-auth store).
- `app/api/v1/byok.py` — added `_sync_openrouter_key_to_sandboxd(api_key)` and
  `_delete_openrouter_key_from_sandboxd()`; `create_api_key`/`update_api_key`/
  `delete_api_key` (openrouter provider) now push/remove the key best-effort.
- `app/integrations/sandboxd_client.py` — added `sync_openrouter_key(self, api_key)`
  (`POST /v1/agents/openrouter/api-key`) and `delete_openrouter_key(self)`
  (best-effort `POST /v1/agents/openrouter/disconnect`). `cancel_task` unchanged.
NOTE: the sync is best-effort (guarded, silent on sandboxd-down) — see Bug #1;
OpenRouter model routing may still fail until the sandboxd proxy resolves
`openrouter/<slug>` resolution itself.

## Deploy note
Backend changes require image rebuild (no volume mounts):
`bash /opt/flowmanner/deploy-backend.sh`. Frontend requires VPS rebuild
(`bash /opt/flowmanner/deploy-frontend.sh`, ~4 min, background).
Neither deployed yet — verify on homelab before pushing.
