# Exit Audit — 2026-06-27 — Plans + Backend Deploy + search_vector Fix

**Session:** Hermes (GLM-5.2) — planning, verification, deploy, migration
**Repo state:** clean, pushed to origin/main
**Deploy:** Backend deployed + migrated by Glenn; frontend NOT yet deployed

---

## WHAT CHANGED (one bullet per file, what + why)

### Plans written by this agent (documentation only)

- `.sisyphus/plans/PLAN-fix-search-vector-orphan-trigger.md` (new, 259 lines)
  — Plan for DeepSeek: fix orphaned `search_vector` trigger on `chat_messages`
  causing every chat INSERT to crash. Includes migration code, tests, verify steps.
- `.sisyphus/plans/PLAN-working-tree-cleanup.md` (new, 242 lines)
  — Plan for DeepSeek: triage 4 unrelated working-tree modifications + 2 lockfiles.
  Verdicts: gitignore uv.lock, revert broken symlink, commit sandboxd fix, commit plan docs.

### Committed by DeepSeek (verified + pushed by this agent)

- `899c9da` — `.gitignore` + `backend/.gitignore`: exclude `uv.lock` (agent tooling artifacts)
- `4c7f048` — `sandboxd/Dockerfile.sandboxd-base` + `sandboxd/entrypoint-wrapper.sh`:
  move runtimed socket to `/tmp` to avoid CapDrop=ALL bind-mount permission errors
- `b253ea9` — `.sisyphus/plans/frontend-awesome-react-adoption.md`: React adoption
  false-positive audits + nav companion-track §6

### Committed by this agent (Plan B fix)

- `60a449a` — `backend/alembic/versions/20260627_fix_orphaned_search_vector_trigger.py`:
  Alembic migration dropping orphaned trigger + function
- `60a449a` — `backend/tests/test_search_vector_trigger_fix.py`: 5 tests
  (3 file-level pass, 2 integration skip until DB at this revision)

### Deployed this session (by Glenn, verified by this agent)

- Backend image rebuilt (`089987ae7d66`), all 3 containers recreated (backend,
  celery-worker, celery-beat), all healthy
- Alembic migrated: `integration_status_page_001` → `fix_search_vector_trigger_001`
  (3 migrations: onboarding flag seed, onboarding flag enable, search_vector trigger fix)

---

## WHAT DID NOT CHANGE BUT WAS TOUCHED

- `backend/tests/test_search_vector_trigger_fix.py` — reformatted by pre-commit's
  ruff v0.6.9 (local ruff is v0.14.5; version mismatch causes format disagreement).
  Applied pre-commit's format to resolve. No `--no-verify` needed.

---

## TESTS RUN + RESULT

```
$ cd /opt/flowmanner/backend && python -m pytest tests/test_search_vector_trigger_fix.py -v
============================= test session starts =============================
platform linux -- Python 3.14.5, pytest-9.0.2, pluggy-1.6.0 -- /usr/bin/python
cachedir: .pytest_cache
rootdir: /opt/flowmanner/backend
configfile: pyproject.toml
plugins: asyncio-1.3.0, langsmith-0.7.30, mock-3.5.1, anyio-4.13.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False

collecting ... collected 5 items

tests/test_search_vector_trigger_fix.py::test_migration_file_exists PASSED [ 20%]
tests/test_search_vector_trigger_fix.py::test_migration_chains_after_source_head PASSED [ 40%]
tests/test_search_vector_trigger_fix.py::test_upgrade_drops_trigger_and_function PASSED [ 60%]
tests/test_search_vector_trigger_fix.py::test_post_deploy_db_state_has_no_trigger SKIPPED [ 80%]
tests/test_search_vector_trigger_fix.py::test_post_deploy_db_state_has_no_function SKIPPED [100%]

========================= 3 passed, 2 skipped in 0.09s =========================
```

Lint:
```
$ ruff check alembic/versions/20260627_fix_orphaned_search_vector_trigger.py tests/test_search_vector_trigger_fix.py
All checks passed!

$ pre-commit run --files <both files>
trim trailing whitespace.................................................Passed
fix end of files.........................................................Passed
check yaml...........................................(no files to check)Skipped
check for added large files..............................................Passed
ruff.....................................................................Passed
ruff-format..............................................................Passed
mypy.................................................(no files to check)Skipped
Detect hardcoded secrets.................................................Passed
```

Live DB verification (post-deploy):
```
$ docker exec workflow-postgres psql -U flowmanner -c \
    "SELECT tgname FROM pg_trigger WHERE tgrelid = 'chat_messages'::regclass AND NOT tgisinternal;"
 tgname
 --------
 (0 rows)

$ docker exec workflow-postgres psql -U flowmanner -c \
    "SELECT proname FROM pg_proc WHERE proname = 'chat_messages_search_update';"
 proname
 ---------
 (0 rows)

$ docker exec workflow-postgres psql -U flowmanner -c \
    "INSERT INTO chat_messages (thread_id, user_id, role, content) \
     VALUES (25, 33, 'user', 'post-migration test') RETURNING id;"
 id
 ----
 260
 INSERT 0 1
```

Backend logs (post-deploy, no errors):
```
$ docker logs backend --since 5m 2>&1 | grep "search_vector"
(empty — zero occurrences)
```

---

## STATUS (raw command output)

### □ git status

```
$ git status
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean
```

### □ git fetch origin && git log --oneline origin/main..main

```
$ git fetch origin && git log --oneline origin/main..main
(empty — already pushed)
```

### □ alembic current

```
$ docker exec backend alembic current
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
fix_search_vector_trigger_001 (head)
```

### □ git log --oneline -6

```
60a449a fix(db): drop orphaned search_vector trigger crashing chat_messages inserts
b253ea9 docs(plan): React adoption false-positive audits + nav companion track
4c7f048 fix(sandboxd): move runtimed socket to /tmp to avoid bind-mount permission errors
899c9da chore(gitignore): exclude uv.lock
6816a23 feat(integrations): enable integration_onboarding_v1 feature flag
26f6f0e feat(integrations): Phase 6 TTFC onboarding wizard backend
```

---

## NEXT SESSION HANDOFF

> Backend is fully deployed + migrated. The search_vector bug (every chat INSERT
> crashing) is FIXED and verified live. Phase 6 onboarding wizard flag is enabled.
>
> **Frontend deploy still needed:** `bash /opt/flowmanner/deploy-frontend.sh`
> (~4 min). This ships the onboarding wizard UI (Phase 6 TTFC). After deploy,
> spot-check `flowmanner.com/integrations` for the wizard on first visit.
>
> **Deploy script issue:** `deploy-backend.sh --migrate` hit a container name
> conflict (`9e14ca469a2c_celery-worker` leftover). Compose still recreated all
> containers on the new image successfully, but the script aborted before the
> alembic step. Migration was run manually (`docker exec backend alembic upgrade
> head`). The deploy script should handle this edge case — worth a fix.
>
> **Pre-commit ruff version mismatch:** Local ruff is 0.14.5, pre-commit pins
> v0.6.9. They disagree on assertion formatting. Workaround: run
> `pre-commit run ruff-format --files <file>` to format in pre-commit's style.
> Permanent fix: pin local ruff to v0.6.9 or bump pre-commit's pin.
>
> **Non-blocking issues spotted in logs:**
> 1. SQLAlchemy connection pool leak in SSE streaming path (connection not
>    returned to pool when client disconnects). GC warning, not a crash.
> 2. Circular import warning: `app.services.unified_tools` → `UnifiedToolBridge`
>    (non-fatal, app starts fine).

---

## FILES THIS AGENT DID NOT TOUCH BUT EXIST

- Untracked files: none (working tree clean)
- Deleted files: none

---

## END
