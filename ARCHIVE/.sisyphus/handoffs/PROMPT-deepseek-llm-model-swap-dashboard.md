# DEEPSEEK TASK: Fix LLM Model Swap Dashboard Integration

## Context

The FlowManner homelab dashboard at `/home/glenn/flowmanner-dashboard-HIL/` has a
complete LLM model swap UI (sidebar chip + modal panel + quick-swap section on the
homepage). The backend daemon (`llm-model-daemon` on port 9723) is also complete
and working. The problem: **the swap never worked from the dashboard** because of
data-shape mismatches between what the daemon returns and what the dashboard
frontend expects.

**I (Hermes) already fixed 3 bugs in the daemon layer** — those are done and
committed at `/opt/flowmanner`:

1. `config/llm-models.yaml`: Fixed 4 broken GGUF file paths (models had been
   moved from `/mnt/apps/models/` to `/mnt/apps/models/mtp/`)
2. `scripts/llm-model-manager.sh` line ~165: YAML `flash_attn: on` parses as
   Python `True` (boolean), crashing `shlex.quote()`. Fixed to coerce to string.
3. `scripts/llm-model-manager.sh` line ~175: `--spec-p-min` was removed from
   newer llama.cpp builds (the build at `/mnt/apps/llama.cpp-mtp` commit `b45b455e`
   does not support it). Removed the arg emission.

**The daemon swap now works end-to-end via API:**
- `POST http://localhost:9723/activate {"model_id":"ornith-1.0-35b"}` → activates, restarts systemd, waits for health, returns success. Tested and verified working.

**What remains for you (DeepSeek):** Fix the dashboard-side data translation so
the existing UI components display models correctly and swaps work from the
browser at `http://localhost:3000`.

---

## The Problem: Data Shape Mismatches

The daemon at `localhost:9723` returns these shapes:

### GET /models (daemon)
```json
{
  "active_model": "qwen3.6-27b-mtp",
  "models": {
    "qwen3.6-27b-mtp": {
      "display_name": "Qwen3.6-27B (MTP)",
      "architecture": "qwen35",
      "quantization": "Q5_K_M",
      "spec_type": "draft-mtp",
      "description": "Dense 27B with built-in MTP draft heads (~2x speedup)",
      "model_path": "/mnt/apps/models/mtp/Qwen3.6-27B-Q5_K_M-mtp.gguf",
      "ctx_size": 32768,
      "is_active": true
    },
    "ornith-1.0-35b": {
      "display_name": "Ornith-1.0-35B Q5_K_M (MoE)",
      "architecture": "qwen35moe",
      "quantization": "Q5_K_M",
      "spec_type": "ngram-simple",
      "is_active": false
    }
  }
}
```

### GET /status (daemon)
```json
{
  "active_model": "qwen3.6-27b-mtp",
  "display_name": "Qwen3.6-27B (MTP)",
  "service_status": "active",
  "health_status": "healthy",
  "health_url": "http://127.0.0.1:11434/health"
}
```

### GET /health (daemon)
```json
{"status": "ok"}
```

### POST /activate (daemon)
```json
// Request: {"model_id": "ornith-1.0-35b"}
// Response: {"status": "activated", "model_id": "ornith-1.0-35b", ...}
// Or on failure: {"error": "...", "exit_code": 1, "stderr": "...", "stdout": "..."}
```

---

## THREE MISMATCHES TO FIX

### Mismatch 1: `models` is a DICT, frontend expects a LIST

**Daemon returns:** `models` as a dict keyed by model ID: `{models: {"qwen3.6-27b-mtp": {...}}}`

**Frontend expects (route.ts line 73):** `models` as a list: `{models: [{id: "...", display_name: "..."}]}`

**Impact:** The dashboard route at `src/app/api/models/route.ts` line 73 does:
```ts
const modelList = Array.isArray(models) ? models : models.models ?? [];
```
Since `models.models` is a dict (not an array), `Array.isArray` is false, and
`models.models` is truthy so `??` doesn't kick in — the dict is passed through.
Then `.map()` on a dict fails silently or the list renders empty.

**Fix:** In `src/app/api/models/route.ts`, convert the daemon's dict to a list
of objects with an `id` field. In the `GET` handler, after parsing the daemon
response, normalize the models dict:

```ts
// After line 73, before building the response:
const rawModels = Array.isArray(models) ? models : Object.values(models.models ?? models);
// But we also need the dict keys as `id` — so:
const modelList = Array.isArray(models)
  ? models
  : Object.entries(models.models ?? {}).map(([id, m]: [string, any]) => ({
      id,
      ...(typeof m === "object" && m !== null ? m : {}),
    }));
```

Also set `active` on the model that matches `status.active_model`.

### Mismatch 2: `active_model` vs `current_model`

**Daemon returns:** `active_model` in `/status`

**Frontend expects:** `current_model` — used in:
- `model-swap-panel.tsx` line 216: `const activeId = status?.current_model;`
- `model-swap-chip.tsx` line 42: `data.status.current_model`
- `model-quick-swap.tsx` line 49: `data.status?.current_model`

**Fix:** In `src/app/api/models/route.ts`, normalize the status object in the
GET response. Map `active_model` → `current_model`:

```ts
const normalizedStatus = {
  ...status,
  current_model: status.active_model ?? status.current_model,
  healthy: status.health_status === "healthy",
};
```

Return `normalizedStatus` instead of raw `status`.

### Mismatch 3: `health_status` vs `healthy`

**Daemon returns:** `health_status: "healthy"` (string)

**Frontend expects:** `healthy: true` (boolean) — used in `model-swap-chip.tsx` line 49.

**Fix:** Covered by Mismatch 2 normalization above. Map
`health_status === "healthy"` → `healthy: boolean`.

---

## FILES TO EDIT (all in `/home/glenn/flowmanner-dashboard-HIL/`)

### 1. `src/app/api/models/route.ts` (PRIMARY FIX)

This is the only file that needs real logic changes. The GET handler must
normalize the daemon response shapes before returning them to the frontend.

**Current GET handler** (lines 44-90) passes daemon data straight through.
**Required:** Transform models dict → list with `id` field, transform status
field names.

**Current POST handler** (lines 92-129) looks correct — it sends
`{"model_id": "..."}` to the daemon's `/activate`. But verify it handles the
daemon's success/error response correctly. The daemon returns:
- Success 200: `{"status": "activated", "model_id": "...", "raw": "..."}`
- Failure 500: `{"error": "...", "exit_code": 1, "stderr": "...", "stdout": "..."}`

The POST handler already spreads `...data` into the response, so `ok: true` is
added alongside the daemon fields. This should work, but test it.

### 2. Frontend components (LIKELY NO CHANGES NEEDED)

These components should work correctly once the route.ts fix normalizes the
data shape — **do not edit them unless testing reveals issues:**
- `src/components/model-swap-panel.tsx`
- `src/components/model-swap-chip.tsx`
- `src/components/model-quick-swap.tsx`

They all expect:
- `models`: array of `{id, display_name, architecture, quantization, spec_type, active, healthy}`
- `status`: `{current_model, healthy, service_status}`

### 3. `src/app/api/models/health/route.ts`

This looks correct — it proxies to the daemon's `/health` endpoint and returns
`{ok: true, health: data}`. The panel polls this during swaps. Verify it
returns the right shape: the panel checks `data.health?.status === "ok"`.

---

## VERIFICATION STEPS

After making changes, verify:

```bash
# 1. Dashboard API route returns normalized data
curl -s http://localhost:3000/api/models | jq .
# Expected: models is a LIST of objects with `id` field, status has `current_model` and `healthy`

# 2. Daemon direct (unchanged, for comparison)
curl -s http://localhost:9723/models | jq .

# 3. TypeScript compiles
cd /home/glenn/flowmanner-dashboard-HIL && npx tsc --noEmit

# 4. Dashboard dev server runs
cd /home/glenn/flowmanner-dashboard-HIL && pnpm dev
# Open http://localhost:3000 — sidebar chip should show "Qwen3.6-27B (MTP)" with green Online badge

# 5. Swap works from UI
# Click the chip → panel opens → shows model list → click Activate on another model
# Panel should show swap progress → success after 10-30s
```

---

## ACTIVE MODELS IN CONFIG (for reference)

File: `/opt/flowmanner/config/llm-models.yaml`

| ID | Display Name | Path | Quant | Spec |
|----|-------------|------|-------|------|
| `qwen3.6-27b-mtp` | Qwen3.6-27B (MTP) | /mnt/apps/models/mtp/Qwen3.6-27B-Q5_K_M-mtp.gguf | Q5_K_M | draft-mtp |
| `ornith-1.0-35b` | Ornith-1.0-35B Q5_K_M (MoE) | /mnt/apps/models/mtp/deepreinforce-ai_Ornith-1.0-35B-Q5_K_M.gguf | Q5_K_M | ngram-simple |
| `ornith-1.0-35b-q6-mtp` | Ornith-1.0-35B Q6_K (MTP) | /mnt/apps/models/mtp/Ornith-1.0-35B-Q6_K-MTP.gguf | Q6_K | draft-mtp |
| `qwopus3.6-35b-a3b-coder-mtp` | Qwopus3.6-35B-A3B (Coder MTP) | /mnt/apps/models/mtp/Qwopus3.6-35B-A3B-Coder-MTP-Q5_K_M.gguf | Q5_K_M | draft-mtp |

Note: `ornith-1.0-35b-q6-mtp` (28GB Q6) **does not fit** on 2x RTX 5060 Ti
(16GB each). It OOMs. Leave it in the config for future use but it will fail
to activate. The other three models all fit and work.

---

## STOP RULES (DO NOT)

1. **DO NOT** edit files in `/opt/flowmanner/scripts/` or
   `/opt/flowmanner/config/` — Hermes already fixed those. Only edit the
   dashboard at `/home/glenn/flowmanner-dashboard-HIL/`.
2. **DO NOT** edit the frontend components unless they genuinely don't work
   after the route.ts fix. They are well-written and should work with
   normalized data.
3. **DO NOT** change the daemon code or the YAML config.
4. **DO NOT** commit. Write changes, report results, Hermes will verify and
   commit.
5. **DO NOT** write meta-docs, plan docs, or handoff docs. Implement the fix.
6. **DO NOT** activate `ornith-1.0-35b-q6-mtp` from the UI — it will OOM and
   crash the server. Use `ornith-1.0-35b` or `qwopus3.6-35b-a3b-coder-mtp`
   for testing swaps.
7. After testing, leave the active model as `qwen3.6-27b-mtp` (the default).

## WORK DIRECTORY

```
cd /home/glenn/flowmanner-dashboard-HIL
pnpm dev    # dashboard runs on http://localhost:3000
```

## SUMMARY FOR DEEPSEEK

The entire model-swap system is ALREADY BUILT — daemon, API route, and 3
React components. It just never worked because the daemon returns models as a
dict and the frontend expects a list, plus two field name mismatches
(`active_model` → `current_model`, `health_status` → `healthy`).

Fix the data normalization in ONE file (`src/app/api/models/route.ts` GET
handler), test in the browser, report back. That's the whole job.
