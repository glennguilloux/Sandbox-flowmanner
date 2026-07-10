# Exit Audit — 2026-06-24

## What changed (this session)

- backend/scripts/model_snapshot.json: regenerated — workspace_id UUID→VARCHAR(36) matches migration
- backend/tests/test_chat_service_byok.py: patched _resolve_provider so default _client path fires deterministically (2 tests)
- .github/workflows/pr-check.yml: added 15-min job cap + 10-min pytest step cap (PR #22, merged)
- /etc/systemd/system/actions.runner.glennguilloux-flowmanner.flowmanner-homelab.service: added Restart=on-failure + RestartSec=30s
- .gitignore: added .sisyphus/exit-audit-*.md pattern (PR #26, open)
- AGENTS.homelab.md: added troubleshooting row for exit-audit deploy guard (PR #26, open)

## What did not change but was touched

- /tmp/prcheck-venv: was cleaned (5.5 GB freed) but re-created by CI runs. Disk, not compute.
- deploy-backend.sh / deploy-frontend.sh: not touched. The deploy guard worked correctly — it refused to deploy off a dirty tree.

## PRs merged this session

- PR #22 (26d75d9): ci/workflow timeout cap — merged
- PR #24 (492ac06): sync model snapshot + tighten byok mock fixture — merged

## PRs open

- PR #26: ci/deploy gitignore exit-audit pattern — waiting for Glenn to merge
- Issue #25: k6 FK bug (playground_sandboxes.workspace_id) — separate work item, not blocking

## Tests run + result

pytest tests/test_chat_service_byok.py → 43 passed (0.26s)
test_validate_migration_gate.py runs inside CI, passes in ~50s (verified via gh run logs)

## Status

□ git status — clean, working tree clean
□ git fetch origin && git log --oneline origin/main..main — empty (nothing unpushed)
□ alembic current — 20260617_pending_writes (head)
□ Runner — Listener idle, no orphan Workers, Restart=on-failure active

## Next session handoff

The CI bleed from today is resolved. PR #24 fixed the two root causes (snapshot drift + byok fixture leak). PR #22 added timeout caps. The deletion guard now passes in ~50s consistently. PR #26 is the last piece (gitignore for agent artifacts) — merge it when ready.

The k6 FK bug (Issue #25) is independent and non-blocking. It runs on ubuntu-latest, fails every time, but doesn't block PR merges. Ticket it, fix it when you want to.

## Files this agent did not touch

- Untracked: .sisyphus/exit-audit-2026-06-24-end-of-session.md, .sisyphus/exit-audit-2026-06-24-pr16-load-test-repair.md, .sisyphus/exit-audit-2026-06-24-pr21-health-fix-merged.md (DeepSeek's session artifacts — leave untracked, PR #26 gitignores them)

## What I learned this session

- "Bleeding stopped" requires checking: ps tree + systemctl + gh pr checks + gh run list. If I haven't done all four, I haven't checked.
- The real cost of CI bleed is attention, not compute. Frame everything in Glenn's hours, not dollars.
- Don't trust my own narrative about why something failed. Verify the actual log output before diagnosing.
- Don't push CI changes without flagging the second-order cost (its own CI run).
