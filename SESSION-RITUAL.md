# SESSION RITUAL — End-of-Session Exit Audit & Handoff

**Read this at the END of every session where you (or another agent) changed
code. Copy this checklist into the audit. Don't summarize — paste command output.**

---

## Why this exists

Agents (DeepSeek, me, any other LLM) finish a session, say "looks good",
and stop. Nothing is actually saved. Next session you find uncommitted
code, untracked migrations, and broken deploys.

**This file fixes that.** It turns "I think we're done" into "git status
is clean and origin/main is up to date."

---

## The ritual — paste this prompt at end of session

```
Write an exit audit. Use the format below. Run every command and
PASTE THE OUTPUT — do not summarize. Then commit (one clear one-line
message) and push to origin. Do NOT deploy.

=== EXIT AUDIT ===

WHAT CHANGED (one bullet per file, what + why):
  - file.py: short reason
  - other.py: short reason

WHAT DID NOT CHANGE BUT WAS TOUCHED:
  - (list files that were edited but reverted, or "none")

TESTS RUN + RESULT (paste pytest tail):
  pytest tests/... -v → "127 passed"

=== STATUS (run these and paste the output, do not paraphrase) ===

□ git status
  (paste the actual output)

□ git fetch origin && git log --oneline origin/main..main
  (paste the actual output, should be empty if pushed)

□ docker compose exec backend alembic current
  (paste the actual output, e.g. "head_001 (head)")

□ docker compose exec backend bash -c "pytest -q" 2>&1 | tail -20
  (paste the actual output)

=== NEXT SESSION HANDOFF ===

> [One paragraph: where we are, what's done, what's the next thing to
>  do. Include any gotchas the next agent needs to know.]

=== FILES THIS AGENT DID NOT TOUCH BUT EXIST ===

- Untracked files: (list from git status — DO NOT delete or commit
  these unless explicitly told to)
- Deleted files: (list from git status — DO NOT restore unless told to)

=== END ===
```

---

## Rules the agent must follow

1. **No paraphrasing.** Paste raw command output. If the agent "summarizes"
   `git status`, the audit is broken.
2. **One commit, one message.** Don't bundle 14 fixes into one commit. If
   there are 3 logical changes, make 3 commits.
3. **`git fetch origin` before `git push`.** Other agents force-push this
   remote silently. Fetching first prevents "rejected non-fast-forward".
4. **Never `git reset --hard`, `git push --force`, or `git restore`.**
   Those destroy work. If something looks wrong, stop and ask.
5. **Untracked files are NOT to be committed** unless the agent knows
   what they are. The "FILES THIS AGENT DID NOT TOUCH" section exists
   for this — paste the list so Glenn can decide.
6. **Alembic migrations must be in the same commit as the model change.**
   Never deploy a model change without its migration. Never deploy a
   migration without a model change that needs it.
7. **Do not deploy.** Glenn reviews the audit, then deploys manually.

---

## The 3 commands Glenn needs to remember

After the agent says "exit audit done":

```
# 1. Read the audit
cat .hermes/sessions/last-audit.md  # or wherever the agent put it

# 2. If it looks good, deploy
bash /opt/flowmanner/deploy-backend.sh    # for backend changes
bash /opt/flowmanner/deploy-frontend.sh   # for frontend changes

# 3. If the deploy failed, the agent's audit missed something.
#    Rollback: bash /opt/flowmanner/deploy-backend.sh --rollback
```

---

## What "done" actually means

A session is **done** when ALL of these are true:

- [ ] Code is committed locally
- [ ] Code is pushed to origin (so it's backed up to GitHub)
- [ ] `git status` is clean
- [ ] `alembic current` is at head
- [ ] `pytest` exits 0
- [ ] Handoff paragraph is written for the next session
- [ ] Deploy has NOT been run (Glenn does that)

If any box is unchecked, the session is **not done** — keep working.
