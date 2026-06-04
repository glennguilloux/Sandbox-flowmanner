# DEEPSEEK LONG JOB — H4: V1 Polish + Ops Stability Gate

TASK: H4-V1-POLISH
HORIZON: Phase 5 completion (operational debt closure)
PROJECT: FlowManner (homelab + ops machine)
ROOT: /opt/flowmanner

## Objective
Close the V1 operational debt items with hard evidence:
1) container/image hygiene
2) nginx-static health stability
3) failed systemd unit storm cleanup on ops machine
4) fail2ban hardening on homelab

This is an operations hardening horizon. No feature work.

## Verified repo facts (already confirmed)
- Roadmap Phase 5 tasks are defined in: /opt/flowmanner/Docs/FLOWMANNER-ROADMAP.md (P5.1..P5.4)
- Current compose defines static healthcheck at:
  - /opt/flowmanner/docker-compose.yml (service `static`, curl localhost:8080)
- Mission gate script exists:
  - /opt/flowmanner/scripts/mission-gate.sh

## Hard constraints
- English only.
- No VPS source edits/deploy logic.
- Keep changes minimal and reversible.
- No blind destructive cleanup.
- Any destructive action (docker rmi, systemctl disable/mask) must be preceded by a saved audit snapshot.
- If new .sh files are created: chmod 755.
- Every success claim must cite command output.

## Required deliverables

### 1) Docker image/service hygiene (P5.1)
Create baseline + action manifest:
- /opt/flowmanner/Docs/P5-DOCKER-AUDIT.md

Requirements:
- Capture full image list with size and usage status (running container reference vs orphan)
- Categorize each candidate image as KEEP / REMOVE / ACTIVATE with reason
- Remove only clearly orphaned images (no container references, not used by compose)
- Record reclaimed disk space before/after

Evidence commands (required in report):
- docker images --format "{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}"
- docker ps -a --format "{{.Image}} {{.Names}} {{.Status}}"
- docker system df

### 2) nginx-static health hardening (P5.2)
Target file:
- /opt/flowmanner/docker-compose.yml (only if fix is needed)

Requirements:
- Inspect current health status of `workflows-static`
- If unhealthy, fix healthcheck command/path/port mismatch
- Recreate only necessary service(s)
- Verify no unhealthy services remain in compose stack

Evidence commands:
- docker inspect workflows-static | jq '.[0].State.Health'
- docker compose ps

### 3) Ops machine failed-unit storm cleanup (P5.3)
Target host:
- ops machine (172.16.1.2)

Requirements:
- Collect top failing units and root error from journal
- Identify culprit unit(s)
- Stop + disable culprit; mask only if restart loop persists
- Verify failed units drop to normal-noise level (or clearly improved with reason)

Evidence commands:
- ssh glenn@172.16.1.2 "systemctl list-units --state=failed --no-pager"
- ssh glenn@172.16.1.2 "journalctl -p err -b --no-pager | head -50"
- ssh glenn@172.16.1.2 "systemctl status <culprit> --no-pager"

If SSH access is blocked, return BLOCKED with exact error output.

### 4) fail2ban hardening on homelab (P5.4)
Requirements:
- Install/verify fail2ban
- Configure sshd jail in jail.local (maxretry=3, bantime=3600 minimum)
- Enable/start service
- Validate jail is active
- Demonstrate safe ban/unban verification flow

Evidence commands:
- fail2ban-client status
- fail2ban-client status sshd
- systemctl status fail2ban --no-pager

### 5) H4 gate report
Create:
- /opt/flowmanner/Docs/H4-V1-POLISH-REPORT.md

Must include:
1. exact files changed
2. exact commands run
3. before/after state tables
4. reclaimed disk amount (if any)
5. service health summary
6. ops failed-unit summary
7. fail2ban verification output
8. remaining risks
9. final verdict: `H4_READY: YES/NO`

## Allowed file scope
You may edit/create only:
- /opt/flowmanner/docker-compose.yml (if needed)
- /opt/flowmanner/Docs/P5-DOCKER-AUDIT.md (new)
- /opt/flowmanner/Docs/H4-V1-POLISH-REPORT.md (new)
- /opt/flowmanner/scripts/ops/*.sh (new optional helper scripts)

If additional files are required, stop and explain first.

## Execution order (strict)
Step 1 — Capture full baseline snapshots (docker/services/systemd/fail2ban)
Step 2 — Write audit manifest before destructive actions
Step 3 — Apply minimal fix wave (image cleanup, healthcheck fix, systemd culprit mitigation, fail2ban)
Step 4 — Re-run verification commands
Step 5 — Write final H4 report with command-output evidence

## Required final chat output format
Return exactly:
- STATUS: SUCCESS | PARTIAL | BLOCKED
- FILES:
- TESTS:
- EVIDENCE:
- RISKS:
- H4_READY: YES | NO
- NEXT:

No vague claims. Every success statement must be backed by command output evidence.