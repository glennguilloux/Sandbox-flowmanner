#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Phase 10.2-10.4 Soak Period Reminder
#
# Scheduled to run on 2026-06-23 (2 weeks after Phase 10.1 deployment).
# Checks soak readiness and logs a reminder to apply the remaining
# Blueprint/Run migration phases.
#
# To apply after soak verification:
#   export PHASE10_SOAK_COMPLETE=1
#   docker compose exec -T backend alembic upgrade head
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

LOG="/opt/flowmanner/logs/phase10_soak_reminder.log"
mkdir -p "$(dirname "$LOG")"

{
  echo ""
  echo "════════════════════════════════════════════════════════════════"
  echo "  ⏰  PHASE 10 SOAK PERIOD REMINDER — $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "════════════════════════════════════════════════════════════════"
  echo ""
  echo "  2-week soak period for Phase 10.1 (blueprints/runs tables)"
  echo "  has elapsed. Review the following before applying 10.2-10.4:"
  echo ""
  echo "  Soak Checklist:"
  echo "  [ ] Zero 500 errors on /api/v2/blueprints/* endpoints (14 days)"
  echo "  [ ] Zero 500 errors on /api/v2/runs/* endpoints (14 days)"
  echo "  [ ] All runs completing without InFailedSQLTransactionError"
  echo "  [ ] substrate_events blueprint_id column populated correctly"
  echo "  [ ] No orphaned rows in blueprints/runs/blueprint_versions"
  echo "  [ ] Database backup taken before applying Phase 10.3"
  echo ""
  echo "  If all checks pass, apply the remaining migrations:"
  echo ""
  echo "    export PHASE10_SOAK_COMPLETE=1"
  echo "    cd /opt/flowmanner"
  echo "    docker compose exec -T backend alembic upgrade head"
  echo ""
  echo "  Migrations to apply (in order):"
  echo "    10.2  phase102_compat_views        — compat views for zero-downtime cut-over"
  echo "    10.3  phase103_drop_old_tables     — drop old execution tables (⚠️ NO DOWNGRADE)"
  echo "    10.4  phase104_retarget_aux_tables — retarget aux table FKs to blueprints/runs"
  echo ""
  echo "  ⚠️  Phase 10.3 is the point of no return — take a DB backup first!"
  echo ""
  echo "════════════════════════════════════════════════════════════════"
  echo ""

  # Check if migrations are already applied
  APPLIED=$(docker compose -f /opt/flowmanner/docker-compose.yml exec -T backend \
    python3 -c "
from sqlalchemy import create_engine, text
import os
url = os.environ.get('DATABASE_URL','').replace('+asyncpg','')
e = create_engine(url)
with e.connect() as c:
    r = c.execute(text('SELECT version_num FROM alembic_version')).fetchone()
    print(r[0] if r else 'unknown')
" 2>/dev/null || echo "check_failed")

  if [[ "$APPLIED" == *"phase102"* ]] || [[ "$APPLIED" == *"phase103"* ]] || [[ "$APPLIED" == *"phase104"* ]]; then
    echo "  ✅ Phase 10.2-10.4 migrations appear to already be applied (current: $APPLIED)"
    echo "  This reminder can be removed from crontab."
  else
    echo "  📋 Current DB revision: $APPLIED"
    echo "  Phase 10.2-10.4 migrations are still pending. Run the checklist above."
  fi

  echo ""
  echo "════════════════════════════════════════════════════════════════"
} >> "$LOG" 2>&1

# Also print to stderr so it shows in cron mail if configured
cat "$LOG" | tail -30 >&2
