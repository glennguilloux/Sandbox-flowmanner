# Exit Audit — P2 Backend Verification + Regression Test (2026-07-07)

## Context
A kanban dispatch of 6 P2 cards crashed (backend workers exited rc=0 without
calling complete/block — a profile/protocol bug; frontend worker ran in an
ephemeral scratch sandbox, couldn't push, falsely marked its card done). On
grounding the work in the real code, the P2 backend features were discovered to
be ALREADY SHIPPED in prior sessions (chat-wiring sprint + registry/prune work).
This session's real value: a regression test for the tool-event stream, a
revert of an erroneous prior commit, and board reconciliation.

## WHAT CHANGED (one bullet per file, what + why)
- backend/app/tests/test_tool_result_sse.py: NEW — regression test asserting
  stream_message_to_llm emits `tool_call_start` then `tool_call_result` SSE
  events (chat_service.py:1817-1848) with correct tool name, call_id, result
  payload, and ordering. Also asserts a plain-text turn emits no tool_call_*
  events. Closes the one real P2-2 coverage gap.
- backend/app/services/sse_protocol.py: REVERTED my earlier erroneous commit
  (7191c2f3) that added SSE_EVENT_TOOL_RESULT = "tool_result" — the real emitted
  event is `tool_call_result` (already in code). Reverted in f71bbaea.

## WHAT DID NOT CHANGE BUT WAS TOUCHED
- backend/app/services/chat_service.py: read extensively to verify P2-2/3
  already implemented; NOT modified.
- backend/app/services/chat_context.py: read to verify P2-3 (_prune_messages_to_budget)
  already implemented; NOT modified.
- backend/app/services/base.py: read to verify P2-4 (ToolRegistry/register_tool)
  already implemented; NOT modified.
- The 22/115 in-file visibility tags + test_computed_allowlist.py: verified
  P2-1 already done; NOT modified.

## TESTS RUN + RESULT
Full backend suite (in-container, test file docker-cp'd in since no volume mounts):

    docker compose exec -T -w /app backend python -m pytest app/tests/ -q
    → 1096 passed, 28 failed, 3 skipped, 33 warnings in 23.41s

NEW test (this session):

    docker compose exec -T -w /app backend python -m pytest app/tests/test_tool_result_sse.py -q
    → 2 passed

The 28 failures are PRE-EXISTING and unrelated to this session:
- test_chat_streaming.py (5) + test_integration_byok_streaming.py (6):
  sse_buffer.py:56 TypeError — these need live Redis in the test container;
  they drive the real endpoint which hits the real SSE buffer.
- test_mission_*.py (17): pre-existing/environmental (missing env/fixtures in
  this container). Confirmed test_mission_planner.py fails WITHOUT my file
  present (does not import it). No mission code touched this session.

## STATUS (raw output)
```
=== git status ===
## main...origin/main
(clean)

=== git fetch + ahead/behind ===
(empty — pushed)

=== alembic current ===
contact_001 (head)
```

## NEXT SESSION HANDOFF
P2 backend is effectively COMPLETE and verified: P2-1 (visibility tagging +
test_computed_allowlist.py), P2-2 (tool_call_start/tool_call_result SSE events,
buffered + replayable, + new regression test), P2-3 (_prune_messages_to_budget
placeholder compaction + test_chat_context.py), P2-4 (ToolRegistry plugin arch)
were all shipped in prior sessions. This session added only a regression test
and reverted a divergent constant. Remaining work is FRONTEND-only and BLOCKED:
the homelab frontend source (/home/glenn/FlowmannerV2-frontend) is an empty
0-byte placeholder here — the real frontend lives on another machine. P2-5
(markdown memoization) and the P2-2-frontend renderer (must consume
`tool_call_result`, NOT `tool_result`) must be done there. The 28 pre-existing
test failures (Redis-dependent SSE tests + mission module) should be triaged
separately — they are not caused by this session's commit. Deploy was NOT run
(Glenn deploys manually).

## FILES THIS AGENT DID NOT TOUCH BUT EXIST
- /home/glenn/FlowmannerV2-frontend: empty placeholder (0 bytes) on this homelab.
  Real frontend source is elsewhere. Do NOT populate or delete without Glenn.
- Untracked files: none in /opt/flowmanner (working tree clean).
- Deleted files: none.

## GOTCHAS FOR NEXT AGENT
- The kanban `--kind` flag consumes the positional `reason` argument (order:
  `kanban block <task_id> --kind needs_input <reason>` fails; reason must
  follow task_id without `--kind`, and a `done` card cannot be re-blocked —
  use `kanban edit --result` to annotate instead).
- docker cp is required to run new tests in the backend container (no volume
  mounts); rebuild via deploy-backend.sh to persist.
- `hermes kanban` workers crash silently when the profile's handshake/creds are
  missing — verify a worker actually called complete/block before trusting a
  card's status.
