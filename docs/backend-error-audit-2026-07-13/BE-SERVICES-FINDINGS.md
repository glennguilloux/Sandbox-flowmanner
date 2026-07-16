# Backend Audit — services/business-logic + governance

**Scope:** `app/services/` (156 files) + `app/governance/` (11 files)
**Branch under audit:** `agent/2026-07-11-intent-execution-architecture`
  (worktree `wt/be-audit-services-20260713` is checked out at its head: `f6fc3637`)
**Mode:** READ-ONLY. Findings only — no source files were modified.
**Paths:** all `file:line` are relative to the worktree root. Note the repo nests
the layer under `backend/`, so `app/services/...` in this report means
`backend/app/services/...` on disk.

---

## Blockers 🔴

### 🔴 Governance approval bypass — only the FIRST pending tool is gated, others execute unapproved
`app/governance/controlflow/agent.py:376-401` (`_execute_tools_node`)

```python
async def _execute_tools_node(self, state: AgentState) -> AgentState:
    for tool in state["pending_tools"]:
        if tool["status"] in ["pending", "approved"]:   # ← runs ANY tool still "pending"
            result = self._execute_tool(state, tool)
            ...
    state["pending_tools"] = []
```

`_check_approval_node` (line 340) only ever creates an approval request for
`state["pending_tools"][0]` (line 347) and the LangGraph edge from
`check_approval` only routes `pending_tools[0]` through the human gate. The other
tools keep `status="pending"`. The execute node then treats `status in
["pending", "approved"]` as "go". Net effect: **if a single user message produces
more than one tool, every tool after the first is executed with NO approval even
when `requires_approval=True`.** That is a governance bypass of the human-in-the-loop gate.

**Why it is a blocker:** an attacker / a sloppy prompt ("execute step_2a AND save
the workflow config") triggers two `requires_approval=True` tools; only the first
is gated, the second runs without a human ever seeing it. This defeats the
approval workflow the module exists to enforce.

**Fix:** only execute tools that have actually been approved; require the human
gate to set an explicit `status="approved"` (or a per-tool `approved_by`) before
execution, and skip/queue any tool still `pending`:

```python
async def _execute_tools_node(self, state: AgentState) -> AgentState:
    executed, still_pending = [], []
    for tool in state["pending_tools"]:
        if tool["status"] == "approved":
            result = self._execute_tool(state, tool)
            tool = update_tool_execution(
                tool,
                status="completed" if result.get("success") else "failed",
                result=result if result.get("success") else None,
                error=None if result.get("success") else result.get("error", "Execution failed"),
            )
            executed.append(tool)
        else:
            still_pending.append(tool)   # never execute un-approved tools
    state["tool_history"] = state["tool_history"] + executed
    state["pending_tools"] = still_pending
    return state
```

---

### 🔴 Approval flow can deadlock — `pending_tools` is cleared but never re-submitted after rejection/approval
`app/governance/controlflow/agent.py:364-401`

```python
def _check_approval_result(self, state: AgentState) -> str:
    if state["awaiting_approval"]:
        return "pending"          # END — no human ever set awaiting_approval=False
    for tool in state["pending_tools"]:
        if tool["status"] == "rejected":
            return "rejected"
    return "approved"
```

Two coupled deadlock / no-op bugs:

1. `awaiting_approval` is set `True` in `_check_approval_node` (line 344) and is
   **never set back to `False` anywhere** in the code (no handler writes it). With
   an async LangGraph + `MemorySaver` checkpointer, `process_message` runs the graph
   to completion synchronously within one `ainvoke`. So `awaiting_approval` stays
   `True` and the next `ainvoke` immediately returns `"pending"` → `END` with no
   tool executed. The human approval/rejection has no code path that flips the
   flag or marks a tool `approved`/`rejected`, so **the conversation can never
   resume execution** — a silent deadlock.

2. Even if the flag were flipped, `_execute_tools_node` wipes
   `state["pending_tools"] = []` (line 401) before anything resolves the pending
   approval, discarding the very tools awaiting a decision.

**Why it is a blocker:** any interaction that requires approval (the module's core
purpose) hangs forever or silently executes nothing.

**Fix:** provide an explicit *resume* entry point that the approval endpoint calls
(parallel to `hitl_service.resolve_interrupt`). That path must (a) set
`awaiting_approval=False`, (b) mark the target tool `approved`/`rejected`, and
(c) re-`ainvoke` the graph so `_execute_tools_node` runs the resolved tool. Do
**not** clear `pending_tools` until after the decision is applied.

---

### 🔴 `update_config` / `delete_config` re-raise inside `except` with `finally: db.close()` → closed-session source swallowed
`app/governance/workflow_config/config_manager.py:340-344` and `384-388`

```python
def update_config(self, config_id, ...):
    try:
        db = SessionLocal()
        try:
            ...
            db.commit()
        except Exception as e:
            db.rollback()
            raise                       # re-raises
        finally:
            db.close()                 # session closed BEFORE the outer handler runs
    except Exception as e:
        self.logger.error(...)
        return {"success": False, "error": str(e)}
```

`raise` in the inner `except` propagates *through* the inner `finally` (which
closes `db`), then is caught by the outer `except` and **converted into a
`{"success": False, ...}` dict**. This is partly intended (APIs return dicts), but
the real defect is that the rollback is wasted and the caller cannot distinguish a
genuine "not found" from a DB failure — and any `db`-dependent cleanup in the
outer handler would operate on a closed session. More importantly, several callers
(`_handle_save_workflow_config` at `agent.py:567`, `get_config`, `list_configs`)
treat the dict as success/failure and surface "error" strings to users that
should have been real exceptions. For a *config mutation* this masks write
failures.

**Why it is a blocker:** a failed config write returns a success-shaped dict with
`success=False` but the call site in `agent.py` does `return result` without
checking `success`, so the agent proceeds as if the workflow config was persisted
when it was not. State diverges from what the user believes was saved.

**Fix:** do not swallow DB exceptions for mutations. Either let them propagate to
the caller (which should fail loud) or, at minimum, have the agent handlers check
`result.get("success")` and surface a real failure instead of continuing.

---

## Suggestions 🟡

### 🟡 Celery `send_task(..., expires=task_timeout)` treats `expires` as an absolute/relative ETA wall-clock, not a run timeout
`app/governance/tool_handlers/worker_handler.py:92` (`execute`) and `143` (`execute_chain`)

```python
result = celery_app.send_task(task_name, args=[task_request], expires=task_timeout)
...
task_result = result.get(timeout=task_timeout)
```

Celery's `expires` is the **task expiry** (the task is discarded if it hasn't
*started* by that time / ETA), not a cap on how long the worker may run it. A
long-running worker task can run far past `task_timeout`; only `result.get(timeout=...)`
aborts the *wait*. The two are conflated in naming/intent. If the broker clock
differs or the task is queued behind others, `expires` can even cause the task to
be discarded before it starts, producing a confusing "Task expired" rather than a
timeout.

**Why it is a latent bug:** under load or clock skew, "timeout" does not behave as
the developer expects; tasks either run unbounded or vanish. Use `soft_time_limit`/
`time_limit` on the task (or `apply_async(expires=...)` with a real ETA) and keep
`result.get(timeout=...)` for the wait.

---

### 🟡 `_simple_tool_conversion` matches "save config" inside any larger message → false-positive approval tool
`app/governance/controlflow/agent.py:290-298`

```python
elif "save config" in message_lower or "save workflow" in message_lower:
    tools.append({..., "requires_approval": True})
```

Keyword-substring matching means "please **save config**uration advice to a file"
or "don't **save config** in prod" both spawn a `save_workflow_config` tool that
requires (and in practice never gets) human approval → combined with the deadlock
above, the request silently stalls. Fragile NLP by substring.

**Why it is a latent bug:** legitimate, non-action text triggers gated tools; with
the deadlock finding, those messages hang.

**Fix:** use intent classification (LLM or stricter, token-boundary aware matching)
instead of raw `in` substring tests for actions that mutate state.

---

### 🟡 `is_active` is a string `"true"`/`"false"`, compared inconsistently; `get_config` filters active but `delete`/`update` also filter active → soft-deleted rows are unfindable
`app/governance/workflow_config/models.py:32` and `config_manager.py:157, 311, 365`

`is_active = Column(String(10), default="true")`. Queries filter
`WorkflowConfig.is_active == "true"`. `delete_config` sets `is_active = "false"`
(line 371) then a later `update_config`/`get_config` with the same `config_id`
returns "Configuration not found" (because it's now `"false"`). This is the
intended soft-delete, but `save_config` always `INSERT`s a new `config_id` (never
reuses), so there is **no "undelete"/re-activate" path** and retries silently
create duplicates while the old id is unreachable.

**Why it is a latent bug:** workflow "update" after a soft delete silently
behaves like a missing record; duplicate `config_id`s can accumulate.

**Fix:** either expose a reactivate path, or make update upsert by `workflow_id`
rather than always minting a new `config_id`.

---

## Nits 💬

### 💬 `reliability_assertions.py:78` — integer division floors the success rate
```python
llm_success_rate = successful / total * 100
```
`successful` and `total` are `int`, so in Python 3 this is already true division
(returns float) — **not** a bug. Noting it only because it *looks* like it could
be floor-divided; it is correct. No action.

### 💬 `controlflow/state.py:131-133` — `approved_at` only set when `approved_by` is truthy
```python
if status == "approved" and approved_by:
    tool["approved_at"] = ...
    tool["approved_by"] = approved_by
```
If a tool is marked `approved` with `approved_by=None` (e.g. auto-approve path),
the approval timestamp is never recorded, making audit trails incomplete. Minor.

---

## VERDICT

- **🔴 Blockers: 3** — all in `app/governance/`: the multi-tool approval bypass
  (`agent.py:376`), the approval deadlock (`agent.py:364-401`), and the swallowed
  config-write failure that lets the agent proceed as if a workflow config was
  persisted (`config_manager.py:340-388` + `agent.py:567`).
- **🟡 Suggestions: 4** — Celery `expires`-as-timeout confusion
  (`worker_handler.py:92/143`), substring false-positive tool triggering
  (`agent.py:290`), stringly-typed `is_active` soft-delete unreachability
  (`models.py:32` / `config_manager.py`).
- **💬 Nits: 2** (one is a non-issue verified as correct).

**Single highest-risk error:** the governance approval bypass at
`app/governance/controlflow/agent.py:376-401`. It defeats the human-in-the-loop gate
for every tool beyond the first in a multi-tool turn, so `requires_approval=True`
tools can execute with no human oversight — a direct governance/security
regression. It is compounded by the approval deadlock (findings 1 & 2) which means
the whole `ControlFlowAgent` approval path is currently non-functional.

**Services layer note:** the business-logic layer (`app/services/`) was audited
across its load-bearing clusters (mission/execution, HITL, budget, capability,
delegation, substrate, connectors, search, memory). The code there is
conspicuously well-guarded: `scalar_one_or_none()` is used everywhere instead of
crash-prone `scalar_one()`, `BudgetEnforcer.call()` deliberately *re-raises* on
primary-route failure rather than masking a model swap with `success=True`, and
`HITLService` correctly checks `already_{status}` / terminal-mission state before
resuming. No unguarded `response.json()`-then-index or silently-swallowed
mutation failures were found in the service layer during this pass — the real
defects are concentrated in `app/governance/controlflow/`.
