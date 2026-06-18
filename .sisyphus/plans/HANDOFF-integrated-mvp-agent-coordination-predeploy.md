# HANDOFF: Integrated MVP — Agent Coordination + Pre-Deploy Gate

**Source plan:** `.sisyphus/plans/integrated-mvp-agent-coordination-predeploy.md`
**Audit date:** 2026-06-18 (v1) → 2026-06-18 (v2)
**Auditor:** Hermes (manual repo inspection — no agent claims to be exhaustive)
**v2 changes:** incorporated GLM-5.2 deep-dive findings
(`.sisyphus/plans/Reply-to-PROMPT-glm52-deepdive-integrated-mvp.md`) + 3
user decisions (this document, §0 below).
**Verdict:** Plan is sound with v2 corrections in scope. Three critical
integration-boundary gaps added to Task 7. Decisions locked. Ready for
Wave 1 after one operator setup (sudoers + .gitignore).

---

## 0. Decisions log (v2 — locked 2026-06-18)

Three open questions resolved by glenn. Each is binding for Wave 1+.

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| D1 | Sudo-wg passwordless? | **Fail-closed default + one-time NOPASSWD sudoers setup documented in SESSION-RITUAL.md + `WG_CHECK=skip` env override. Implementation on this homelab: user-specific `glenn` rule (no `flowmanner` group exists).** | Persistent fix beats per-deploy friction. Override is the documented escape hatch. Group can be added later if a second operator joins. |
| D2 | Reroute `make deploy-backend` through `deploy-backend.sh`? | **Yes — 1-line Makefile edit. `make deploy-backend` becomes `bash deploy-backend.sh`.** | Plan's "no deploy path bypasses precheck" guarantee is otherwise false. Mirror `make deploy-frontend` (L169). |
| D3 | `STATUS.md` gitignore policy? | **`.gitignore STATUS.md` + commit `STATUS.example.md` template. Active file is per-agent session state, not version-controlled.** | Avoids per-agent edit polluting repo. Template is the canonical reference. |

---

## 1. What the plan delivers (TL;DR)

A coordination MVP at the repo root + a fail-closed pre-deploy gate, all built with existing Bats/helper scaffolding. Six implementation tasks across two parallel waves, plus a four-agent final review wave. Estimated ~2 days. Estimated effort assumes the implementation agents verify everything against the real filesystem, not the plan's text.

Files to create:

- `/opt/flowmanner/STATUS.md` (created on first use; gitignored — see D3)
- `/opt/flowmanner/STATUS.example.md` (committed template)
- `/opt/flowmanner/scripts/pre-deploy-check.sh`
- `/opt/flowmanner/scripts/tests/pre_deploy_check.bats`

Files to modify:

- `/opt/flowmanner/scripts/tests/run_tests.sh`
- `/opt/flowmanner/deploy-frontend.sh`
- `/opt/flowmanner/deploy-backend.sh`
- `/opt/flowmanner/Makefile` — see D2 + §3.8
- `/opt/flowmanner/.gitignore` — see D3 + §3.10
- `/opt/flowmanner/SESSION-RITUAL.md` — see §3.9 (sudoers setup), §3.10 (STATUS.md exclusion note)

Files to remove (pre-MVP cleanup):

- `/opt/flowmanner/.pre-commit-config.yaml` (dangling symlink — see §3.9)

Not in scope (per plan + v2 reaffirmation): web dashboard, DB-backed
locks, CI provider, broad deploy redesign, automatic rollback on
precheck failure, distributed lock daemon.

---

## 2. Verification of plan's stated assumptions

I verified each file the plan names. Status (v2 adds 4 rows):

| Plan claim | Reality | OK? |
|---|---|---|
| `/opt/flowmanner/STATUS.md` does not exist | absent | OK |
| `/opt/flowmanner/scripts/pre-deploy-check.sh` does not exist | absent | OK |
| `deploy-frontend.sh` has no arg parsing / `--dry-run` not implemented | 25 lines, only `set -e`, no arg parsing, no `--dry-run`, no `--rollback`, no `--help` | OK (plan correct, but see §3.2) |
| `deploy-backend.sh` has `--dry-run`, `--rollback`, `--migrate`, `--validate`, `--no-validate` | confirmed at L60-83 | OK |
| `deploy-backend.sh` `--dry-run` not fully side-effect-free because `save_current_image()` tags images even in dry-run | confirmed — `save_current_image()` at L113-127 runs unconditionally; `main()` at L374-375 calls it on every normal deploy without a `DRY_RUN` guard | OK |
| `/opt/flowmanner/scripts/` exists with deploy/health conventions and Bats tests | confirmed; pre-flight.sh, post-deploy-verify.sh, validate-migration.sh, health-monitor.sh, mission-gate.sh, deploy_flowmanner.sh, run_tests.sh, helpers.bash all present | OK |
| Bats installed and used for deploy-tooling tests | `scripts/tests/deploy_flowmanner.bats` exists (19320 bytes) | OK |
| `.sisyphus/drafts/agent-coordination-working-system.md` exists | **DOES NOT EXIST** in `.sisyphus/drafts/` (only `audit-round5-fixes.md`, `enable-mtp.md`, `future-architecture-paradigm.md`, `next-level-growth.md`, `q2-q3-chunk9-lenient-validation-gate-prompt.md`, `task-10-deepseek-continue-prompt.md`, `team-ui-gaps.md`) | **DISCREPANCY** |
| `plans/TEMP/GITHUB-DEPENDENCY-AUDIT.md` exists | confirmed | OK |
| Plan refers to `deploy_flowmanner.sh` calling both backend and frontend deploys | there are TWO orchestrators: `scripts/deploy_flowmanner.sh` (calls deploy-frontend.sh, runs docker build for backend inline) AND root `deploy-all.sh` (calls deploy-backend.sh + deploy-frontend.sh) | **DISCREPANCY** |
| `pre-flight.sh` uses `http://127.0.0.1:8000/api/health` | confirmed at L89 | OK |
| `deploy-backend.sh` uses `http://localhost:8000/health` | confirmed at L27 | OK (URL split between scripts) |
| `deploy-frontend-remote.sh` exists, forwards args to homelab deploy-frontend.sh | confirmed (5510 bytes, 105 lines, line 26 sets `DEPLOY_SCRIPT=/opt/flowmanner/deploy-frontend.sh`, line 81 forwards all args) | OK |
| `backend/tests/test_validate_migration_gate.py` exists | not re-verified; mentioned in plan only | unverified |
| `Makefile` `deploy-backend` target calls `deploy-backend.sh` | **FALSE — Makefile:160-164 runs `docker compose up -d --no-deps --force-recreate backend` directly, bypassing precheck** | **DISCREPANCY (v2)** |
| `.pre-commit-config.yaml` exists and works | **DANGLING symlink → `backend/.pre-commit-config.yaml` (target absent)** | **DISCREPANCY (v2)** |
| `STATUS.md` is in `.gitignore` | NOT ignored (`git check-ignore STATUS.md` rc=1); `.gitignore` has only `.sisyphus/handoffs/` for session markers | **DISCREPANCY (v2 — D3)** |
| `wg0` is the WireGuard interface on homelab | confirmed (`ip -o link show` → `wg0: <POINTOPOINT,NOARP,UP>`) | OK (v2) |

---

## 3. Critical discrepancies the plan does not address

These are bugs in scope that the plan's text either ignores or actively forbids. They will cause silent failures or actively break existing functionality if not resolved.

### 3.1 Two orchestrators, not one

Plan Task 6 mentions "Avoid double-running precheck when `deploy_flowmanner.sh` calls both scripts." That is incomplete:

- `/opt/flowmanner/scripts/deploy_flowmanner.sh` (13056 bytes) — calls `bash deploy-frontend.sh` (L211) and runs docker build for backend inline (L43 BACKEND_DEPLOY_CMD is a docker command, NOT a call to deploy-backend.sh).
- `/opt/flowmanner/deploy-all.sh` (9679 bytes) — calls `bash deploy-backend.sh --rollback` (L196) and `bash deploy-frontend.sh --rollback` (L192).

Both orchestrators will double-trigger precheck if the implementation just adds `pre-deploy-check.sh` calls inside deploy-frontend.sh and deploy-backend.sh.

**Required:** define the policy (recommended: orchestrators pass `--skip-precheck` to inner scripts, OR inner scripts detect they're being called from an orchestrator via env var and skip). Either is fine — but the plan must explicitly pick one before Wave 2 Task 6 begins. Pick whichever the implementation agent proposes; do not leave it implicit.

### 3.2 `deploy-frontend.sh --rollback` is documented but unimplemented

Plan Task 6 says: "Keep argument parsing minimal; do not add rollback to frontend unless already needed by docs."

Docs that need it (and will break without it):

- `deploy-frontend-remote.sh:12` — usage line shows `--rollback` as a documented flag.
- `deploy-frontend-remote.sh:81` — forwards all args including `--rollback` to `/opt/flowmanner/deploy-frontend.sh` on homelab.
- `deploy-all.sh:192` — calls `bash "$DEPLOY_FRONTEND" --rollback`.
- `scripts/deploy_flowmanner.sh:327` — user-facing help text mentions `deploy-frontend.sh --rollback`.

Today this is a latent bug: running `deploy-frontend-remote.sh --rollback` or `deploy-all.sh --rollback --skip-backend` will fail with "Unknown argument: --rollback" the moment anyone tries. The MVP is the right moment to fix it — `--rollback` is in scope.

**Required:** add `--rollback` to deploy-frontend.sh alongside `--dry-run` and `--help` in Task 6. MVP-scope rollback for frontend means: do not deploy new image; instead rsync last-known-good source from a backup tag (or skip — frontend has no image-tag flow like backend, so the rollback may just be a no-op + log message that says "manual rollback: revert last commit and redeploy"). **Decide the rollback semantics before coding.** The simplest MVP-correct implementation: print "frontend rollback requires manual revert of last commit + redeploy; see DEPLOY-RUNBOOK.md" and exit 0 — but document that limitation in the help text.

### 3.3 `STATUS.md` exclusion must be implemented both in precheck AND documented in deploy scripts

Plan says `STATUS.md` is excluded from working-tree cleanliness checks. The exclusion is a single line in pre-deploy-check.sh (`check_working_tree` skips STATUS.md). That is enough for the precheck to pass when only STATUS.md is dirty.

But the broader question: when a human runs `git status` and sees STATUS.md dirty, they may still feel they need to commit it. The exclusion should be documented in two places:

1. STATUS.md itself (already in plan Task 1 — explicit note about exclusion).
2. SESSION-RITUAL.md — add one line under "What 'done' actually means" clarifying STATUS.md is intentionally mutable. **This file modification is not in the plan; flag it as in-scope.**

**v2 addition (D3):** the file should be `.gitignore`d (so `git status` does not show it as dirty at all) AND a `STATUS.example.md` template should be committed in its place. See §3.10.

### 3.4 Missing reference: `.sisyphus/drafts/agent-coordination-working-system.md`

The plan cites this file at L246 and L536. It does not exist. Either:

- The file was archived/moved and the references are stale, OR
- The Metis review that produced these defaults was done elsewhere and the file was never committed.

**Action:** drop or replace these references in any tasks that cite them. The substantive defaults (STATUS.md advisory, rollback bypass, dirty-tree policy) are still in scope — they just can't be cross-referenced. Don't let the implementing agent pause on this; flag it and move on.

### 3.5 `run_tests.sh` is Bats-only and only knows one test file

Plan Task 3 says update `run_tests.sh` so it runs both `deploy_flowmanner.bats` and `pre_deploy_check.bats`. Current state at L22: `BATS_FILE="${SCRIPT_DIR}/deploy_flowmanner.bats"` — single file, hardcoded.

**Required:** convert `BATS_FILE` to `BATS_FILES=(...)` array and loop over them. Keep `--filter <pattern>` semantics by passing the same filter to each `bats` invocation. Existing 19320-byte `deploy_flowmanner.bats` must keep passing — the helper `load helpers.bash` and stub fixtures are reusable for the new file.

### 3.6 `deploy_flowmanner.bats` symlinks the real `/opt/flowmanner/deploy-frontend.sh` over

L20-22 in `deploy_flowmanner.bats`:

```
ln -sf "${FAKE_BIN}/deploy-frontend.sh" /opt/flowmanner/deploy-frontend.sh
```

This test pattern **silently overwrites the real deploy-frontend.sh with a fake stub for the duration of the test**. Today this is safe because the file is only ~25 lines and the symlink gets cleaned up. But once Task 6 modifies deploy-frontend.sh to add arg parsing + precheck call, a `bash -n` failure on the fake stub will produce confusing errors. The new `pre_deploy_check.bats` must NOT use this pattern.

**Required:** in `pre_deploy_check.bats`, do NOT symlink deploy-frontend.sh or deploy-backend.sh. Test pre-deploy-check.sh in isolation, with env var overrides (`PROJECT_ROOT`, `HEALTH_URL`, `CURL_BIN`, etc.) and fake-bin PATH. The plan already implies this in the "Must NOT do" section of Task 3 — enforce it.

### 3.7 Health URL split between scripts

- `pre-flight.sh` and `health-monitor.sh`: `http://127.0.0.1:8000/api/health`
- `deploy-backend.sh` and `scripts/deploy_flowmanner.sh`: `http://localhost:8000/health`

Both reach the same backend (localhost == 127.0.0.1) but `/api/health` and `/health` are likely different endpoints. Plan Task 5 says default `HEALTH_URL=http://127.0.0.1:8000/api/health`. That's consistent with pre-flight/health-monitor but inconsistent with deploy-backend.sh.

**v2 finding (GLM-5.2 find-8):** `/api/health` IS valid. `backend/app/main_fastapi.py:359-360` mounts the health router at BOTH `/health` (root) and `/api/health` (prefix). Both return the same `HealthResponse`. Plan's default stands.

**Action:** let the env var `HEALTH_URL` override remain as the plan specifies. Document in pre-deploy-check.sh header comment that the default matches `pre-flight.sh` and that both prefixes work because of the dual router mount in main_fastapi.py:359-360.

### 3.8 Makefile `deploy-backend` bypasses precheck (v2 — GLM-5.2 find-1)

`Makefile:160-164`:

```
.PHONY: deploy-backend
deploy-backend: build-backend ## Build and deploy backend
	@echo -e "$(GREEN)Restarting backend container...$(RESET)"
	cd $(PROJECT_ROOT) && docker compose up -d --no-deps --force-recreate backend
	@echo -e "$(GREEN)Backend deployed.$(RESET)"
```

`make deploy-backend` calls `docker compose up` directly. It does NOT call `deploy-backend.sh`. So the precheck wired into `deploy-backend.sh` (Task 6) is silently bypassed when an operator uses the Makefile target — defeating the plan's "no deploy path bypasses the precheck" guarantee in the final checklist.

`make deploy-frontend` (Makefile:166-169) already does the right thing: `bash $(PROJECT_ROOT)/deploy-frontend.sh`. `make deploy-backend` should mirror this.

**Decision (D2):** change Makefile:163 to `bash $(PROJECT_ROOT)/deploy-backend.sh`. One-line edit. Behavior change is "slower deploy due to validation gate" — acceptable per glenn.

**Required:** Task 6 / Task 7 must include Makefile in scope. Acceptance criterion: every `make deploy*` target routes through a precheck-wired script.

### 3.9 Dangling `.pre-commit-config.yaml` symlink (v2 — GLM-5.2 find-2)

```
$ ls -la .pre-commit-config.yaml
lrwxrwxrwx ... .pre-commit-config.yaml -> backend/.pre-commit-config.yaml
$ test -e .pre-commit-config.yaml && echo exists || echo DANGLING
DANGLING
$ find /opt/flowmanner -maxdepth 3 -name '.pre-commit-config*' -type f
(no results)
```

The symlink claims a pre-commit config exists; the target does not. Any teammate running `pre-commit install` or `pre-commit run` will fail. The plan's commit trailers say "Pre-commit: bash -n ..." which implies the framework runs — but those are just labels, not framework invocations.

**Action (v2 — pre-MVP cleanup, can be folded into Task 1):** `git rm .pre-commit-config.yaml`. The minimal-viable fix is to remove the misleading symlink. If a real pre-commit config is wanted later, commit `backend/.pre-commit-config.yaml` with `check-yaml` + `shellcheck` hooks — out of MVP scope.

**Required:** rename commit-trailer label from `Pre-commit:` to `Pre-flight:` (or `Pre-merge:`) in any commit message that uses the old label. Bash `-n` syntax checks are still performed, just not labeled as "Pre-commit".

### 3.10 `STATUS.md` not in `.gitignore` (v2 — D3)

```
$ git check-ignore -v STATUS.md
(rc=1)
```

Current `.gitignore` has `.sisyphus/handoffs/` for session markers but not `STATUS.md`. Per-agent edits to STATUS.md would dirty the working tree on every session.

**Decision (D3):** add `/STATUS.md` to `.gitignore` AND commit a `STATUS.example.md` template at the repo root as the canonical reference. Active STATUS.md lives locally; new clones copy from the example.

**Required:** Task 1 must commit BOTH files (`.gitignore` modification + `STATUS.example.md` creation) and NOT pre-create `/STATUS.md` (it appears on first agent use).

---

## 4. Risks and unknowns

### 4.1 Sudo requirements for WireGuard check (v2 — D1)

Plan Task 5 says `check_wireguard` uses `sudo wg show wg0`. WireGuard status check needs root on most systems. The deploy scripts on homelab run as `glenn` (per AGENTS.md / memory). Test environment with fake_bin has a `sudo` stub already at `scripts/tests/fixtures/fake_bin/sudo`.

**v2 finding (GLM-5.2 find-3):** on this homelab, `sudo wg show` requires a password in non-interactive shells:

```
$ sudo -n wg show wg0
sudo: a password is required
```

So the precheck, if implemented naively, will fail-closed in any CI/cron context — which is correct behavior, but a first-deploy surprise.

**Decision (D1):** three-part solution documented in precheck header AND SESSION-RITUAL.md operator-setup block:

1. **Default:** fail-closed. Precheck calls `sudo -n wg show wg0` (non-interactive flag fails immediately if no NOPASSWD). On failure → hard fail with setup instructions in the error message.
2. **One-time setup** (operator runs once on homelab):
   ```
   echo "glenn ALL=(root) NOPASSWD: /usr/bin/wg show *" | \
     sudo tee /etc/sudoers.d/flowmanner-deploy && \
     sudo chmod 0440 /etc/sudoers.d/flowmanner-deploy
   ```
   User-specific (not `%flowmanner` group) because no `flowmanner` group exists on this homelab. Or run precheck/deploy as root. Documented in SESSION-RITUAL.md "Operator Setup" section.
3. **Escape hatch:** `WG_CHECK=skip` or `FLOWMANNER_DEPLOY_OVERRIDE_REASON="no-wg-credential"` env var bypasses with audit log entry. Use only in emergencies when sudoers cannot be set up in time.

Test environment with fake_bin `sudo` stub covers this without requiring actual sudo. Real-machine test in F3 (per §5).

### 4.2 `HEALTH_URL` for "last deploy healthy" freshness

Plan says default 24h TTL. There is no existing artifact recording last deploy time. The precheck will need either:

- A new artifact file written by deploy scripts on success (e.g., `/opt/flowmanner/.deploy-state/last-success.json`).
- Or live health-only check (no TTL, just current state).

**Action:** recommend live-only for MVP. If the user wants TTL later, that's a follow-up. Specifying "default 24h" in the plan implies an artifact that doesn't exist yet; if implemented, becomes one more file the deploy scripts need to write. Do not add this in MVP. State the simplification in the implementing task's "What to do" section.

### 4.3 Migration/model path detection

Plan Task 5 says "fail on changed/untracked Alembic version files" and "backend model/schema files". Existing `check_pending_migrations()` at deploy-backend.sh:179-199 already does the alembic part (`backend/alembic/versions/`). For models, the path is implied to be `backend/app/models/` but the plan doesn't say so explicitly.

**v2 finding (GLM-5.2 verification):** `/opt/flowmanner/backend/app/models/` exists with 60 model `.py` files. `/opt/flowmanner/backend/alembic/versions/` exists with 106 migration `.py` files. Both paths are correct as the plan implies.

**Action:** implementation agent must pin both paths explicitly in the precheck config block. Do not hardcode globs that miss new subdirectories.

### 4.4 Bats test for `check_wireguard` will need sudo stub to exist

The fake-bin `sudo` stub already exists (verified in `ls scripts/tests/fixtures/fake_bin/`). Good. But if any new check calls `sudo wg show` without the stub present, tests will silently call the real sudo. Implementation agent must verify the stub is in PATH during every Bats test that exercises WireGuard-related checks.

**v2 finding (GLM-5.2 find-7):** `fake_bin` lacks stubs for `git`, `wg`, `rsync`, `scp` — only `curl, docker, ssh, sudo, md5sum, date, timeout, sleep, deploy-frontend.sh, smoke_flowmanner.sh` are present. Pre-check.sh must invoke wg ONLY via sudo (covered by sudo stub at helpers.bash L271-273). Git checks can use real git in temp dirs (Task 4 already does). No new stubs needed for MVP.

### 4.5 What if `STATUS.md` doesn't exist when precheck runs?

`check_status_file` will be called by precheck. If the file is absent, the check should warn (not fail) — STATUS.md is a coordination tool, not a precondition. The plan does not explicitly say this. **Action:** default behavior must be "absent file → info-level note, not failure." Document in STATUS.md header that the file is created on first use.

### 4.6 Orchestrator summary text references unimplemented flag (v2 — GLM-5.2 find-6)

`scripts/deploy_flowmanner.sh:326-327`:

```
echo "  Rollback:  bash ${PROJECT_ROOT}/deploy-backend.sh --rollback"
echo "             bash ${PROJECT_ROOT}/deploy-frontend.sh --rollback"
```

This user-facing help text advertises `deploy-frontend.sh --rollback` — which Task 6 will implement. Not a bug, but Task 6 acceptance should explicitly require that this summary text reflects the finally-implemented rollback semantics (e.g., "manual revert + redeploy" for frontend).

### 4.7 Manual disaster-recovery path bypasses precheck (v2 — GLM-5.2 find-4)

`RESTORE.md:99` documents a third manual docker build path:

```
docker build -t workflows-backend:restored backend/
```

This is an operator-initiated escape hatch for disaster recovery. Out of MVP scope to gate it. **Action:** add a comment block to `pre-deploy-check.sh` header:

> Manual restore paths (RESTORE.md, `make deploy-backend` direct build) are operator-initiated escape hatches and bypass this gate by design. Out of MVP scope to gate them.

After D2, `make deploy-backend` no longer direct-builds, but RESTORE.md still does — note still applies.

---

## 5. Concrete next steps (ordered, executable)

These match the plan's wave structure but include the corrections from §3 (v1 + v2 additions).

### Pre-Wave 0 (operator, ~15 min — v2 includes sudoers + .gitignore)

Run BEFORE Wave 1 starts:

1. **Orchestrator precheck policy:** orchestrator passes `--skip-precheck` to inner scripts (recommended) OR inner scripts detect an env var set by orchestrators. Pick one. The recommended approach is to add `--skip-precheck` to deploy-frontend.sh and deploy-backend.sh as an internal flag, and have `deploy-all.sh` and `scripts/deploy_flowmanner.sh` set it.
2. **Frontend `--rollback` semantics:** implement as documented "manual revert" no-op + exit 0, with explicit log message. (Confirmed scope expansion — must override plan's "do not add unless already needed by docs" rule because docs DO need it.)
3. **Confirm `STATUS.md` exclusion in SESSION-RITUAL.md** is in-scope for this MVP. (Recommended yes — one-line edit. D3 supersedes with .gitignore + example file.)
4. **D1 — sudoers NOPASSWD setup** (operator runs on homelab as root):
   ```
   echo "glenn ALL=(root) NOPASSWD: /usr/bin/wg show *" | \
     sudo tee /etc/sudoers.d/flowmanner-deploy && \
     sudo chmod 0440 /etc/sudoers.d/flowmanner-deploy
   ```
   User-specific (not `%flowmanner` group) because no `flowmanner` group exists on this homelab — `id glenn` shows only `wheel, docker, ollama, plugdev, adbusers, render, video, bin`. Group-setup is out of MVP scope.
   Verify with `sudo -n wg show wg0` (should print peer table, no password prompt).

### Wave 1 (3 parallel quick tasks + 2 pre-MVP cleanup items from §3.9, §3.10)

- Task 1 (quick): create `STATUS.example.md` template + add `STATUS.md` to `.gitignore` + remove dangling `.pre-commit-config.yaml` symlink (`git rm`).
- Task 2 (unspecified-high): create `pre-deploy-check.sh` skeleton. **Add explicit handling for missing STATUS.md (warn, not fail). Use `sudo -n wg show wg0` per D1. Include `WG_CHECK=skip` escape hatch.**
- Task 3 (quick): update `run_tests.sh` to loop over multiple .bats files. **Do NOT use the symlink-deploy-frontend.sh pattern from deploy_flowmanner.bats; verify the fake-bin path is set up by sourcing helpers.bash.**

Commit 1 after Wave 1: `feat(ops): add agent status protocol and pre-deploy gate skeleton`. Pre-flight: `bash -n scripts/pre-deploy-check.sh`.

### Wave 2 (3 tasks, 2 parallel + 1 serial)

- Task 4 (unspecified-high, after 1+2): status + working-tree checks.
- Task 5 (unspecified-high, after 2): health + migration/model checks. **Use live-only for "last deploy healthy"; do not add a new artifact file. Pin model directory path (`backend/app/models/`) and alembic path (`backend/alembic/versions/`) in the script's config block.**
- Task 6 (unspecified-high, serial after 4+5): wire deploy scripts + add `--rollback` to deploy-frontend.sh + add `--dry-run` to deploy-frontend.sh + fix `save_current_image()` DRY_RUN guard + add `--skip-precheck` and update orchestrators to use it + **change Makefile:163 to `bash $(PROJECT_ROOT)/deploy-backend.sh` (D2)**.

Commits 2 + 3 after Wave 2: `feat(ops): wire pre-deploy gate into deploy scripts` and `test(ops): add pre-deploy Bats coverage`.

### Wave Final (4 parallel reviews)

- F1 oracle: Plan Compliance Audit. **Includes: every `make deploy*` target routes through precheck-wired script (D2).**
- F2 unspecified-high: Code Quality Review.
- F3 unspecified-high: Real Manual QA. **Must include: homelab real `sudo -n wg show wg0` (verifies D1 setup); homelab real curl `/api/health`; `deploy-all.sh --dry-run` end-to-end; `make deploy-backend --dry-run` end-to-end (verifies D2 wiring).**
- F4 deep: Scope Fidelity Check.

**All four must approve. Do not auto-proceed. Wait for user explicit OK.**

---

## 6. Items explicitly out of scope (do not let scope creep)

Reaffirming from the plan's "Must NOT Have":

- No web dashboard.
- No DB-backed coordination.
- No distributed lock daemon.
- No new CI/CD provider.
- No broad deploy redesign.
- No automatic rollback on precheck failure.
- No VPS source edits (homelab edits only — confirm deploy scripts stay on homelab; deploy-frontend-remote.sh on ops/dev triggers them).
- No claim that `--dry-run` is fully side-effect-free unless the implementation actually makes it so.

Additional YAGNI reminders based on §4:

- No "last deploy healthy" artifact file.
- No Sudoers changes to make `wg show` non-passwordless via code (D1 documents it as operator setup, not precheck responsibility).
- No model-path glob auto-discovery (pin the path).
- No `WG_CHECK=advisory` mode — only `WG_CHECK=skip` (binary, audit-logged). Advisory creates noise.
- No web dashboard for STATUS.md view (read it via `cat STATUS.md`).
- No automatic removal of dangling `.pre-commit-config.yaml` — it's a one-line `git rm` in Wave 1.

---

## 7. Open questions for the user (v2 — all resolved)

v1 questions → resolved by §0 Decisions Log:

1. ~~Frontend `--rollback` semantics~~ → **Resolved (v1):** manual revert no-op + exit 0. Implementation in Task 6.
2. ~~Orchestrator precheck policy~~ → **Resolved (v1):** `--skip-precheck` flag passed from orchestrators to inner scripts. Implementation in Task 6.
3. ~~`SESSION-RITUAL.md` edit~~ → **Resolved (v1, expanded v2):** one-line addition about STATUS.md exclusion + new "Operator Setup" block for D1 sudoers.

v2 added questions → resolved by §0 Decisions Log:

4. ~~Makefile deploy-backend bypass~~ → **Resolved (D2):** reroute to `deploy-backend.sh`.
5. ~~Sudo wg password~~ → **Resolved (D1):** fail-closed + operator NOPASSWD setup + `WG_CHECK=skip` override.
6. ~~STATUS.md gitignore policy~~ → **Resolved (D3):** gitignore + commit `STATUS.example.md`.

No remaining open questions. Wave 1 can begin after Pre-Wave 0 setup.

---

## 8. Sign-off

This handoff is a repo-state audit, not an implementation. The plan is good; the corrections in §3 (v1 + v2) are necessary; the risks in §4 are real but manageable; the next-steps in §5 are ready to execute. Implementing agent should start by reading §3 and §5, then this document can be archived or deleted.

**v2 source:** GLM-5.2 deep-dive report at
`.sisyphus/plans/Reply-to-PROMPT-glm52-deepdive-integrated-mvp.md`.
All 3 critical findings integrated as §3.8, §3.9, §3.10. 7 of 9 important
findings noted in §4 (with v2 additions §4.6, §4.7) and §5 (D2
acceptance, F3 verification). 5 minor findings recorded in
`.sisyphus/plans/Reply-to-PROMPT-glm52-deepdive-integrated-mvp.md` —
none blocker, none require handoff changes.

End of handoff.