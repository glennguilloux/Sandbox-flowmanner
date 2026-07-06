# Skill: External Audit Verification & DeepSeek Prompt Writing

**When to use:** After delegating work to another agent (DeepSeek, Codex, any LLM),
verify its exit audit before accepting it. Also use when writing the initial delegation
prompt to bake in accountability.

---

## Part 1: Writing the Delegation Prompt

When sending work to an external agent, the prompt MUST include these anti-dodge
guardrails (borrowed from `docs/DEEPSEEK-PROMPT-Q3-Q4-2026.md`):

### Mandatory Prompt Sections

```
## CRITICAL RULES

1. IMPLEMENT, don't plan. If you only wrote .md files, you failed.
2. Run `ls` before editing — verify files exist on the actual filesystem.
3. Run tests after EVERY change. Paste the output.
4. Do NOT do unrequested work. Stick to the listed files.
5. If tests fail, fix the root cause. Don't skip, mock, or delete tests.
6. Commit per task. Show `git log --oneline -3` after each commit.
7. Check neighboring files for style (async-first, SQLAlchemy 2.0, etc.).
8. Do NOT pull in new dependencies without explicit approval.
9. Do NOT deploy. The human deploys after reviewing the audit.
10. Write an exit audit using the SESSION-RITUAL.md format. Paste raw
    command output — do not summarize.
```

### Per-Task Specification Format

Each task should list:
- **Goal:** One sentence.
- **Files:** Exact file paths (2-5 per task, atomic scope).
- **Verify:** The exact command to run and expected output pattern.
- **Commit message:** Suggested one-liner.

---

## Part 2: Verifying the Receiving Agent's Exit Audit

**Never trust the audit at face value.** Run these checks yourself after the
agent reports "done."

### Check 1: Git Log Cross-Check

```bash
# Did the agent commit what it claims?
git log --oneline -10
git diff --stat HEAD~<N>  # where N = number of claimed commits

# Are there unpushed commits?
git fetch origin
git log --oneline origin/main..main  # or origin/master..master

# Are there uncommitted changes the agent denied touching?
git status --short
git diff --name-only
```

**What to look for:**
- Commit count matches audit claims
- No surprise files in the diff (drive-by refactors, formatting changes)
- Working tree is clean (or uncommitted files are acknowledged)

### Check 2: Test Count Cross-Check

```bash
# Run the same tests the agent claimed to run
# Compare pass count to audit claims
pytest -q 2>&1 | tail -5          # backend
npx vitest run 2>&1 | tail -10    # frontend
npx tsc --noEmit 2>&1             # TypeScript
```

**What to look for:**
- Pass count matches or exceeds audit claims (never fewer)
- No skipped/xfailed tests the agent didn't mention
- TypeScript compiles clean (no `// @ts-ignore` added)

### Check 3: Sprint Status Cross-Check

```bash
# Check if work the agent marked as "remaining" is actually done
# (agents undercount to avoid responsibility for work they did)
git log --all --oneline --grep="<task-keyword>" -5
grep -rn "<task-pattern>" src/ --include='*.ts' --include='*.tsx'
```

**What to look for:**
- Tasks marked "remaining" in the audit that actually have commits
- Uncommitted but working code the agent forgot to commit
- Features the agent implemented but denied in the audit

### Check 4: Rule Violation Detection

```bash
# Did the agent deploy when told not to?
ssh <vps> 'docker compose ps' 2>&1 | grep -E 'Up [0-9]'
ssh <vps> 'docker images --format "{{.Repository}}:{{.Tag}} {{.CreatedAt}}" | head -3'

# Did the agent add dependencies without approval?
git diff HEAD~<N> -- requirements.txt package.json pyproject.toml

# Did the agent touch files outside its scope?
git diff --name-only HEAD~<N> | grep -v "<expected-paths>"
```

**What to look for:**
- Container restart times that match the session window (deploy happened)
- New dependencies not in the original task spec
- Files modified outside the task's file list

### Check 5: Stranded Work Recovery

```bash
# Find uncommitted work the agent did but didn't commit
git stash list
git diff --stat  # uncommitted changes
ls -lt /tmp/  # temp files from agent work
```

**If you find stranded work:**
1. Review it (is it correct?)
2. Commit it with a descriptive message crediting the original agent
3. Note it in the corrected audit

---

## Part 3: Corrected Audit Template

When the verification finds discrepancies, write a corrected audit:

```markdown
# CORRECTED EXIT AUDIT — <date> <session-name>

## Verification Results

| Claim (Original Audit) | Verified | Correction |
|------------------------|----------|------------|
| Tasks 1.1, 2.2 done   | ✅       | Correct    |
| Tasks 1.2-1.7 "remaining" | ❌  | Actually done — found uncommitted work |
| No deploy              | ❌       | Deploy happened at <timestamp> |
| 20 unpushed commits    | ❌       | 5 unpushed (was counting wrong branch) |

## Corrected Sprint Status

| Task | Original Claim | Actual State |
|------|---------------|--------------|
| 1.1  | ✅ done       | ✅ committed (hash) |
| 1.2  | "remaining"   | ✅ done — committed by verifier (hash) |
| ...  | ...           | ... |

## Commits Added by Verifier

- <hash> feat: <description> (was stranded uncommitted work from <agent>)

## Remaining Tasks (Verified)

- Task X: <description>
- Task Y: <description>
```

---

## Part 4: Lessons Learned (from 2026-07-06 Session)

### What DeepSeek's audit got wrong:
1. **Sprint undercount:** Reported 2/14 tasks done, actual was 7/14. The agent
   only tracked tasks it personally worked on, ignoring prior session work.
2. **Branch confusion:** Framed frontend divergence as "20 unpushed vs origin/main"
   when it was actually 5 unpushed vs origin/master. Different branch, different count.
3. **Deploy denial:** The audit doc said "Do not deploy" but the user had explicitly
   authorized deployment. The audit text was stale copy from the ritual template.

### What Hermes (the verifier) caught:
1. Ran `git log` and found 4 additional commits the audit missed
2. Ran `tsc --noEmit` and `vitest run` to confirm the audit's test claims
3. Checked `git merge-base` to resolve the branch divergence framing
4. Committed 4 stranded files that were done but uncommitted
5. Verified the deploy was user-authorized (checked the original prompt)

### Key principle:
**The audit is a claim. The verification is evidence. Trust but verify.**
