# R10 — Replace or delete the simulated `runtime/` reliability cluster

**Context:** Swarm audit REPORT.md §4 R10 + Architect ledger F4 (VERIFIED by
orchestrator). `backend/app/services/runtime/predictive_scaler.py:27-43` returns
`random.uniform` fake telemetry; `self_healing.py:44-45` does `asyncio.sleep(0.5)`
"recovery" + in-memory-only history; and grep confirms **zero imports outside
`runtime/`** — the entire self-healing/auto-scaling subsystem is decorative and
unwired. A 99.9% SLA claim is unsupported by code.

**Your task (pick ONE, prefer the honest minimal real version; block-for-review before deleting):**
1. PREFERRED: wire `runtime/` to real signals — `predictive_scaler.py` reads
   Prometheus metrics instead of `random`; `self_healing.py` calls a real restart
   hook (Celery task or deploy/restart path) instead of `sleep(0.5)`; persist
   history. Keep it thin.
2. IF the real version is too large for this card: instead DELETE the cluster
   (`runtime/` + its singletons) and remove it from the OpenAPI/observability
   surface + add a doc note that self-healing is not yet operational.
3. Either way, do NOT claim capabilities the code doesn't deliver.

**Constraints:** Choose the minimal honest path. If deleting, do it carefully and
note it; otherwise implement the real thin version. Commit to this branch. Do NOT
push, deploy, or merge. Stop and block-for-review when done.
