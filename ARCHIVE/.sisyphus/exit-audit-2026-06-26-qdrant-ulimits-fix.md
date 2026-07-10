# Exit Audit — 2026-06-26 — fix(qdrant): nofile ulimit hardening

> Session goal: diagnose homelab instability after hard reboot, fix Qdrant
> container restart loop caused by container-level file descriptor exhaustion.

## WHAT CHANGED
- `docker-compose.yml` — added `ulimits: { nofile: { soft: 65536, hard: 65536 } }`
  under the `qdrant` service (matching Qdrant's published production
  recommendation). Soft=hard chosen so container cannot exceed even if
  dockerd raises limits. Includes a comment explaining root cause
  (actix "Too many open files" panic → 134x restart loop after reboot).

## WHAT DID NOT CHANGE BUT WAS TOUCHED
- None.

## TESTS RUN + RESULT
- `docker compose config qdrant` → exit 0 (compose syntax valid)
- `docker compose up -d qdrant` → exit 0 (container recreated clean)
- `docker compose ps qdrant` → `(healthy)`, `Up 28 seconds`
- `docker exec workflow-qdrant sh -c 'ulimit -Hn; ulimit -Sn'` → `65536 / 65536`
- `curl http://127.0.0.1:8000/api/health` → HTTP 200, all deps `ok`
- `curl http://localhost:11434/health` → `{"status":"ok"}`
- `systemctl status llama-server` → `active (running)` since 4m33s after reboot
- `sudo wg show` → wg0 active; VPS peer (74.208.115.142) handshake 1m35s ago
- `git fetch origin && git log origin/main..main` → empty (no diverged commits)

## CODE REVIEW
- `code-reviewer-minimax-m3` → **APPROVE** (with optional nudge to consider
  `131072` for additional headroom, and to harden sibling services in a
  separate commit).
- Skip `thinker-with-files-gemini`: routine single-block edit, no novel
  architecture decision.

## ROOT CAUSE NOTES
- Qdrant actix actor pool was exhausting the per-container nofile limit
  (~1024 default in Docker, ~4096 hard). Errno 24 "Too many open files"
  triggered a panic → `restart: unless-stopped` loop → 134 attempts.
- No OOM-killer involvement (`journalctl -b -p err` shows no OOM entries).
- Host fd ceiling is 524288 / `fs.file-max` is effectively unlimited — this
  was strictly a container-level limit.
- The pre-freeze `journalctl` is lost (wiped by reboot), so we cannot prove
  Qdrant *caused* the freeze vs *coincided* with it. The pattern is
  sufficient justification for hardening.

## FILES THIS AGENT DID NOT COMMIT
- `.sisyphus/exit-audit-2026-06-26-qdrant-ulimits-fix.md` — this audit; left
  untracked per AGENTS.md ("per-session exit audits at .sisyphus/ are gitignored").

## NEXT SESSION HANDOFF
> Homelab is healthy after the Qdrant ulimit fix + recreation. Backend / LLM /
> DBs / WireGuard-to-VPS are all OK. Backend image unchanged; `backend`
> container is still on the pre-reboot image (`workflows-backend:restored`),
> so any in-flight backend rebuild from a prior session was preserved.
>
> **Open items for next session:**
> 1. Consider bumping Qdrant `nofile` to 131072 once stable (per code-reviewer
>    optional nudge) — separate commit.
> 2. Harden sibling services (backend, postgres, redis, rabbitmq, celery-worker,
>    celery-beat) with the same `ulimits: { nofile: { soft: hard: } }` pattern —
>    they all currently inherit Docker's default nofile limit. Separate commit.
> 3. **Glens:** run `deploy-backend.sh` if any backend change is needed —
>    this commit does NOT require a backend rebuild (compose-only change),
>    and `up -d qdrant` was already executed locally to recreate the
>    container, so Qdrant is live with the new ulimit. Deploy guard is
>    satisfied as long as this commit lands.
> 4. Investigate why the host froze — the kernel/syslog forensic trail was
>    wiped by the reboot. Consider enabling persistent journal (`/var/log/journal`)
>    or `netconsole` so future freezes leave evidence.
