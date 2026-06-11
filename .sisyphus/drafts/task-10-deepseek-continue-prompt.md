# Task 10 Continuation Prompt for DeepSeek

Hand this to DeepSeek in exec mode with tools enabled, preferably `deepseek exec --auto --model deepseek-v4-pro`.

Recommended command from `/opt/flowmanner`:

```bash
deepseek exec --auto --model deepseek-v4-pro "Read /opt/flowmanner/.sisyphus/drafts/task-10-deepseek-continue-prompt.md and follow it. Save your final report to /opt/flowmanner/.sisyphus/evidence/task-10-deepseek-continuation-report.md"
```

---

## Context

You are continuing Hermes Kanban task `t_9891a7d0`: `Task 10 — final docs-pack QA and drift report` for FlowManner future-architecture documentation.

The previous worker got stuck inside frontend Playwright. I killed the hung Playwright process group and the worker process because run #44 was no longer making progress.

Important: do not rerun the frontend checks as one chained command. The previous hang happened because `npx tsc --noEmit && npx vitest run && npx playwright test` was chained, so the evidence only showed earlier passing output and did not isolate the hung command. Run each frontend check separately and tee each command to its own evidence file.

## Current verified state

From the previous run:

- Docs validation passed:
  - Evidence: `/opt/flowmanner/.sisyphus/evidence/task-10-docs-pack-validation.txt`
  - Output summary: `docs_validated=9`, `validation=pass`

- Backend substrate-critical pytest gate passed:
  - Evidence: `/opt/flowmanner/.sisyphus/evidence/task-10-substrate-critical.txt`
  - Output summary: `139 passed, 1 warning`

- Frontend checks:
  - Evidence: `/opt/flowmanner/.sisyphus/evidence/task-10-frontend-checks.txt`
  - `tsc` appears to have passed because the file begins with Vitest output.
  - Vitest output shows `319 tests passed`.
  - Playwright was then launched and hung for roughly 26 minutes with 0.0% CPU.

- The hung process was killed:
  - Playwright process group command was `npx tsc --noEmit && npx vitest run && npx playwright test`
  - The Playwright node process and npm wrapper were killed.
  - The Hermes worker process was also killed after it became defunct.
  - Verify no Playwright process remains before continuing.

## Required files to read first

Read these before doing anything:

1. `/opt/flowmanner/.sisyphus/plans/future-architecture-paradigm.md`
2. The Task 10 section inside that plan.
3. `/opt/flowmanner/docs/REBUILD-ROADMAP.md`
4. All docs in `/opt/flowmanner/docs/future-architecture/`
5. Existing evidence:
   - `/opt/flowmanner/.sisyphus/evidence/task-10-docs-pack-validation.txt`
   - `/opt/flowmanner/.sisyphus/evidence/task-10-substrate-critical.txt`
   - `/opt/flowmanner/.sisyphus/evidence/task-10-frontend-checks.txt`

## Hard constraints

- Do not deploy.
- Do not modify backend or frontend source code except tests if needed.
- Allowed file scope for fixes:
  - `/opt/flowmanner/docs/future-architecture/**`
  - `/opt/flowmanner/scripts/**`
  - `/home/glenn/FlowmannerV2-frontend/**/__tests__/**`
  - `/home/glenn/FlowmannerV2-frontend/src/test/**`
  - `/opt/flowmanner/.sisyphus/evidence/**`
- If you need to touch anything outside that scope, stop and explain why.
- Do not claim completion unless every required gate passes or the task is explicitly blocked with a concrete reason.
- Do not trust stdout alone. Write evidence files and verify them on disk.

## What to do

1. Reorient
   - Run `hermes kanban show t_9891a7d0`.
   - If the task still says running but no worker PID is alive, treat the previous run as killed/crashed and continue inline.
   - Check `ps`, `pgrep`, and `pstree` to confirm no hung Playwright process remains.

2. Preserve current evidence
   - Read the three existing evidence files listed above.
   - Do not overwrite them unless you intentionally rerun a command.

3. Rerun only what is necessary
   - Docs validation already passed, but you may rerun it if you changed docs.
   - Backend substrate-critical tests already passed, but you may rerun them if you changed backend tests or source.
   - Frontend `tsc` and Vitest already passed in the previous evidence, but rerun them separately if you changed frontend tests or source.
   - Playwright must be isolated and bounded.

4. Run frontend checks safely and separately
   Use separate commands like these, from `/home/glenn/FlowmannerV2-frontend`:

   ```bash
   set -o pipefail
   npx tsc --noEmit 2>&1 | tee /opt/flowmanner/.sisyphus/evidence/task-10-frontend-tsc.txt
   echo "task_10_frontend_tsc_exit=$?" | tee -a /opt/flowmanner/.sisyphus/evidence/task-10-frontend-tsc.txt

   npx vitest run 2>&1 | tee /opt/flowmanner/.sisyphus/evidence/task-10-frontend-vitest.txt
   echo "task_10_frontend_vitest_exit=$?" | tee -a /opt/flowmanner/.sisyphus/evidence/task-10-frontend-vitest.txt

   timeout 180 npx playwright test --workers=1 --timeout=30000 --reporter=line 2>&1 | tee /opt/flowmanner/.sisyphus/evidence/task-10-frontend-playwright.txt
   echo "task_10_frontend_playwright_exit=$?" | tee -a /opt/flowmanner/.sisyphus/evidence/task-10-frontend-playwright.txt
   ```

   If Playwright hangs again, stop the command, capture process state, and block the task with a concrete reason naming the exact command and PID.

5. Produce the drift report
   Create `/opt/flowmanner/.sisyphus/evidence/task-10-drift-report.md` mapping every task in the future-architecture plan to evidence and command output.

   Required report sections:
   - Executive status: pass/fail/blocked
   - Evidence index
   - Per-task drift matrix
   - Docs validation result
   - Backend substrate-critical result
   - Frontend TypeScript result
   - Frontend Vitest result
   - Frontend Playwright result
   - Provider routing unresolved status
   - Changed files / diff summary
   - Risks and open gaps
   - Final recommendation

6. Completion rules
   - If all required checks pass and drift report exists, complete the task with a concise summary and metadata.
   - If Playwright or any other required gate fails/hangs, do not complete. Block the task with a clear reason and include evidence paths.
   - Before completing or blocking, run `git status --short` in both `/opt/flowmanner` and `/home/glenn/FlowmannerV2-frontend`, inspect relevant diffs, and include the summary in the report.

## Output format

Write the final report to:

```text
/opt/flowmanner/.sisyphus/evidence/task-10-deepseek-continuation-report.md
```

Use this exact schema:

```markdown
# Task 10 DeepSeek Continuation Report

## Status
PASS / FAIL / BLOCKED

## Summary
2-5 bullets.

## Evidence Files
- Docs validation: path + result
- Backend substrate-critical: path + result
- Frontend tsc: path + result
- Frontend Vitest: path + result
- Frontend Playwright: path + result
- Drift report: path + result

## Commands Run
List exact commands and exit codes.

## Diff / File Review
Summarize relevant git status and diffs.

## Drift Report Result
State whether `/opt/flowmanner/.sisyphus/evidence/task-10-drift-report.md` was created.

## Block Reason, If Any
If blocked, name the exact failing or hung command, PID/process evidence, and evidence file path.

## Next Action
What a human should do next.
```

Do not give vague claims. Every success statement must be backed by command output or a file path you verified.
