# DEEPSEEK LONG JOB — H3: Observability + Backup/Restore + CI Gate Hardening

TASK: H3-HARDENING
HORIZON: Phase 4 completion gate + CI enforcement gate
PROJECT: FlowManner (backend + ops scripts)
ROOTS:
- Backend: /opt/flowmanner/backend
- Ops scripts/workflows: /opt/flowmanner

## Objective
Deliver production-grade H3 hardening with real evidence, not claims:
1) actionable observability alerts (multi-channel including ntfy)
2) reliable backup/restore pipeline (Postgres, Qdrant, RabbitMQ, config) with retention + restore verification
3) CI gating that blocks merges when substrate-critical checks fail

## Verified current state (must treat as facts)
- CI workflow exists: /opt/flowmanner/.github/workflows/ci.yml
  - has backend/frontend/docker jobs
  - lint/type checks are currently non-blocking (`|| true`)
- Alerting exists: /opt/flowmanner/backend/app/services/alerting.py
  - currently driven by single ALERT_WEBHOOK_URL
  - no explicit NOTIFY_CHANNELS fanout logic
- SLO engine exists: /opt/flowmanner/backend/app/core/slo.py
  - calls send_slo_alert for at-risk SLOs
- SLO dashboard config exists: /opt/flowmanner/backend/app/core/slo_dashboard.py
- Backup scripts exist:
  - /opt/flowmanner/scripts/backup-db.sh
  - /opt/flowmanner/scripts/backup-staging.sh
  - but roadmap-required scope (Qdrant snapshot API, RabbitMQ definitions/config backup/restore proof) is incomplete
- /opt/flowmanner/Docs/OBSERVABILITY.md does not exist yet

## Hard constraints
- English only.
- No VPS steps.
- No frontend code edits.
- Keep changes minimal and surgical.
- If new .py/.sh files are created, chmod 644 for .py and 755 for executable .sh.
- No fake success: every claim must include command output evidence.

## Required deliverables

### 1) Observability alerting hardening
Implement channel fanout and ntfy support.

Patch:
- /opt/flowmanner/backend/app/services/alerting.py

Requirements:
- Add NOTIFY_CHANNELS env support, CSV format, e.g. `NOTIFY_CHANNELS=ntfy,pagerduty,email,webhook`
- Add ntfy channel support:
  - topic via `NTFY_TOPIC` (or full URL via `NTFY_URL`)
  - default endpoint pattern: `https://ntfy.sh/<topic>`
- Keep existing webhook path backward-compatible
- Route both circuit alerts and SLO alerts through channel dispatcher
- Per-channel failure must be non-fatal and logged
- Preserve debounce behavior

Add tests (new file):
- /opt/flowmanner/backend/tests/test_alerting_channels.py

Must verify:
- channel parsing from env
- ntfy payload POST call formatting
- multi-channel fanout behavior
- per-channel failure isolation (one channel failing does not block others)

### 2) Observability docs + dashboard verification workflow
Create:
- /opt/flowmanner/Docs/OBSERVABILITY.md

Must include:
- where dashboard config lives (`app/core/slo_dashboard.py`)
- how to export/print dashboard JSON
- how to verify Langfuse health endpoint from homelab
- URLs/placeholders Glenn can open
- checklist for 4 SLO panels:
  - mission success rate
  - p99 SSE latency
  - model fallback success
  - deploy success rate

### 3) Backup + restore hardening
Patch scripts:
- /opt/flowmanner/scripts/backup-db.sh
- /opt/flowmanner/scripts/backup-staging.sh

Create script (new):
- /opt/flowmanner/scripts/restore-verify.sh

Requirements:
- PostgreSQL backup:
  - produce compressed dump under /opt/flowmanner/backups/postgres/
  - retention: 7 daily + 4 weekly
  - restore verification command included (`pg_restore --list` or equivalent for chosen dump format)
- Qdrant backup:
  - use Qdrant snapshot API (preferred) or documented container-volume fallback
  - retain 7 daily snapshots
- RabbitMQ backup:
  - export definitions (`rabbitmqadmin export` or equivalent)
  - include data snapshot strategy and retention (7 daily)
- Config backup:
  - archive /opt/flowmanner/.env and /opt/flowmanner/docker-compose.yml
  - retention 30 daily
- Add explicit dry-run/verify mode where feasible
- Provide restore verification script that checks backup artifact integrity and outputs PASS/FAIL summary

### 4) Scheduling backup jobs
Create one canonical scheduling artifact (pick ONE):
- cron file template under /opt/flowmanner/scripts/cron/flowmanner-backups.cron
OR
- systemd timer/service templates under /opt/flowmanner/scripts/systemd/

Requirement:
- daily run at 03:00 UTC
- logs path documented
- installation instructions documented (do not assume manual memory)

### 5) CI gating hardening (merge-blocking for substrate-critical)
Patch:
- /opt/flowmanner/.github/workflows/ci.yml

Requirements:
- add explicit substrate-critical job running:
  - tests/test_substrate_event_log.py
  - tests/test_substrate_replay.py
  - tests/test_substrate_executor_v2.py
  - tests/test_failure_analyzer_budgets.py
  - tests/test_meta_loop_orchestrator_budgets.py
  - tests/test_trigger_bridge.py
  - tests/test_nexus_orchestrator_singleton.py
  - tests/chaos/test_kill_worker_mid_mission.py
  - tests/chaos/test_kill_worker_mid_mission_process.py
- this substrate job must be blocking (no `|| true`)
- backend main test job remains required and blocking
- remove/avoid silent-pass patterns on critical gates
- keep workflow runtime reasonable (parallelize jobs where appropriate)

Add workflow validation command output in report:
- `python -c "import yaml,sys; yaml.safe_load(open('/opt/flowmanner/.github/workflows/ci.yml')); print('ci.yml valid')"`

### 6) Final H3 evidence report
Create:
- /opt/flowmanner/backend/H3-OBS-BACKUP-CI-HARDENING-REPORT.md

Must include:
1. exact files changed
2. exact commands run
3. test results table (pass/fail/skip)
4. proof snippets for:
   - ntfy + multi-channel dispatch path
   - backup artifacts created with retention evidence
   - restore verification output
   - CI substrate-critical blocking job definition
5. remaining risks
6. verdict: `H3_READY: YES/NO` with reason

## Allowed file scope
You may edit only:
- /opt/flowmanner/backend/app/services/alerting.py
- /opt/flowmanner/backend/tests/test_alerting_channels.py (new)
- /opt/flowmanner/Docs/OBSERVABILITY.md (new)
- /opt/flowmanner/scripts/backup-db.sh
- /opt/flowmanner/scripts/backup-staging.sh
- /opt/flowmanner/scripts/restore-verify.sh (new)
- /opt/flowmanner/scripts/cron/flowmanner-backups.cron (new, if cron path chosen)
- /opt/flowmanner/scripts/systemd/* (new, if systemd path chosen)
- /opt/flowmanner/.github/workflows/ci.yml
- /opt/flowmanner/backend/H3-OBS-BACKUP-CI-HARDENING-REPORT.md (new)

If anything outside this scope is required, stop and explain first.

## Execution steps (strict order)

Step 1 — Read current files and design smallest patch set
Step 2 — Apply code/script/workflow/docs changes in one batch
Step 3 — chmod new scripts properly
Step 4 — Run targeted backend tests:
- cd /opt/flowmanner/backend
- PYTHONPATH=/opt/flowmanner/backend pytest -q tests/test_alerting_channels.py

Step 5 — Run backup + restore verification commands:
- bash /opt/flowmanner/scripts/backup-db.sh
- bash /opt/flowmanner/scripts/backup-staging.sh
- bash /opt/flowmanner/scripts/restore-verify.sh

Step 6 — Validate CI workflow syntax
Step 7 — Write final H3 report with command-output evidence

## Required final chat output format
Return exactly:
- STATUS: SUCCESS | PARTIAL | BLOCKED
- FILES:
- TESTS:
- EVIDENCE:
- RISKS:
- H3_READY: YES | NO
- NEXT:

No vague claims. Every success statement must be backed by command output evidence.