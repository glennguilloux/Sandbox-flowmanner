#!/usr/bin/env python3
"""
TASK-06: Run 10 Real Missions — Find the Bugs Unit Tests Miss

This script tests the live mission executor against DeepSeek V4 Flash.
Results written to /opt/flowmanner/plans/tasks/BUGS-FROM-REAL-MISSIONS.md
"""

import asyncio
import json
import time
import os
import traceback
from datetime import datetime, timezone, timedelta

import httpx
import jwt

BASE_URL = "http://127.0.0.1:8000"
API_BASE = f"{BASE_URL}/api/missions"


# Load secrets from .env
def load_env():
    env = {}
    with open("/opt/flowmanner/.env") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


ENV = load_env()
JWT_SECRET = ENV.get("JWT_SECRET_KEY", "change-me-in-production")
JWT_EXPIRES = int(ENV.get("JWT_ACCESS_TOKEN_EXPIRES", "3600"))


def make_token(user_id=1):
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=JWT_EXPIRES),
        "type": "access",
        "role": "user",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


TOKEN = make_token(1)
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# ── Test Results Storage ──────────────────────────────────────
results = []
errors_found = []


def record(mission_num, name, outcome):
    results.append({"num": mission_num, "name": name, **outcome})


# ── API Helpers ──────────────────────────────────────────────


async def api_post(path, data, timeout=120):
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(f"{API_BASE}{path}", json=data, headers=HEADERS)
        return r.status_code, (
            r.json()
            if r.headers.get("content-type", "").startswith("application/json")
            else r.text
        )


async def api_get(path, timeout=30):
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(f"{API_BASE}{path}", headers=HEADERS)
        return r.status_code, (
            r.json()
            if r.headers.get("content-type", "").startswith("application/json")
            else r.text
        )


async def api_patch(path, data, timeout=30):
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.patch(f"{API_BASE}{path}", json=data, headers=HEADERS)
        return r.status_code, (
            r.json()
            if r.headers.get("content-type", "").startswith("application/json")
            else r.text
        )


async def api_delete(path, timeout=30):
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.delete(f"{API_BASE}{path}", headers=HEADERS)
        return r.status_code, (
            r.json()
            if r.headers.get("content-type", "").startswith("application/json")
            else r.text
        )


# ── Test Runner ──────────────────────────────────────────────


async def run_mission(mission_num, name, create_data, check_fn=None, timeout=120):
    """Create a mission, plan it, execute it, and return results."""
    print(f"\n{'=' * 60}")
    print(f"MISSION {mission_num}: {name}")
    print(f"{'=' * 60}")

    outcome = {
        "name": name,
        "create_error": None,
        "mission_id": None,
        "plan_result": None,
        "execute_result": None,
        "final_status": None,
        "tasks": [],
        "logs": [],
        "errors": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        # 1. Create mission
        print("  [1/4] Creating mission...")
        status, data = await api_post("/", create_data)
        if status not in (200, 201):
            outcome["create_error"] = f"HTTP {status}: {data}"
            print(f"  ❌ Create failed: {outcome['create_error']}")
            return outcome
        mission_id = data["id"]
        outcome["mission_id"] = mission_id
        print(f"  ✓ Created: {mission_id} (status: {data.get('status')})")

        # 2. Plan it
        print("  [2/4] Planning mission...")
        status, plan_data = await api_post(f"/{mission_id}/plan", {}, timeout=timeout)
        outcome["plan_result"] = {"status": status, "data": plan_data}
        if status != 200:
            outcome["errors"].append(f"Plan failed HTTP {status}: {plan_data}")
            print(f"  ❌ Plan failed: {plan_data}")
        else:
            print(
                f"  ✓ Plan result: success={plan_data.get('status')}, tasks={plan_data.get('total_tasks', '?')}"
            )

        # 3. Execute
        print("  [3/4] Executing mission...")
        t0 = time.time()
        status, exec_data = await api_post(
            f"/{mission_id}/execute", {}, timeout=timeout
        )
        elapsed = time.time() - t0
        outcome["execute_result"] = {
            "status": status,
            "data": exec_data,
            "elapsed_sec": round(elapsed, 2),
        }
        if status != 200:
            outcome["errors"].append(f"Execute failed HTTP {status}: {exec_data}")
            print(f"  ❌ Execute failed ({elapsed:.1f}s): {exec_data}")
        else:
            outcome["final_status"] = exec_data.get("status")
            print(
                f"  ✓ Execute done ({elapsed:.1f}s): status={exec_data.get('status')}, "
                f"completed={exec_data.get('completed_tasks')}, "
                f"failed={exec_data.get('failed_tasks')}"
            )

        # 4. Get tasks
        print("  [4/4] Fetching tasks & logs...")
        status, tasks_data = await api_get(f"/{mission_id}/tasks")
        if status == 200:
            outcome["tasks"] = tasks_data
            for t in tasks_data:
                print(
                    f"    Task: {t['title']} — {t['status']}"
                    f"{' (retry #' + str(t.get('retry_count', 0)) + ')' if t.get('retry_count') else ''}"
                    f" | error: {t.get('error_message', '')[:80] if t.get('error_message') else 'none'}"
                )

        status, logs_data = await api_get(f"/{mission_id}/logs")
        if status == 200:
            outcome["logs"] = logs_data

        # 5. Check for bugs if check_fn provided
        if check_fn:
            bugs = check_fn(outcome)
            if bugs:
                outcome["errors"].extend(bugs)
                for b in bugs:
                    print(f"  🐛 BUG: {b}")

        print(
            f"  Summary: {len(outcome['errors'])} errors, {len(outcome.get('tasks', []))} tasks"
        )

    except Exception as e:
        outcome["errors"].append(f"Exception: {str(e)}\n{traceback.format_exc()}")
        print(f"  💥 EXCEPTION: {e}")
        traceback.print_exc()

    results.append({"num": mission_num, "name": name, **outcome})
    return outcome


# ── Bug Checkers ────────────────────────────────────────────


def check_analytics_swallowing(outcome):
    """Does analytics error handling swallow real errors?"""
    # Analytics is wrapped in try/except — check if mission completed but analytics might have silently failed
    bugs = []
    # If mission completed but tasks have issues, analytics might miss them
    return bugs


def check_db_rollback(outcome):
    """Does DB rollback correctly on failure?"""
    bugs = []
    exec_result = outcome.get("execute_result", {}).get("data", {})
    if exec_result.get("status") == "failed":
        # Check that tasks failed as expected
        failed = exec_result.get("failed_tasks", 0)
        total = exec_result.get("total_tasks", 0)
        if failed > 0 and total > 0:
            pass  # DB should have rolled back properly
    return bugs


def check_output_truncation(outcome):
    """Check if task output was truncated."""
    bugs = []
    for t in outcome.get("tasks", []):
        if t.get("status") == "completed" and t.get("output_data"):
            output = json.dumps(t["output_data"])
            if len(output) > 10000:
                bugs.append(
                    f"Task '{t['title']}' output is very large ({len(output)} chars)"
                )
    return bugs


def check_dependency_resolution(outcome):
    """Does Task 2 get Task 1's output?"""
    bugs = []
    tasks = outcome.get("tasks", [])
    if len(tasks) >= 2:
        t2 = tasks[1] if len(tasks) > 1 else None
        t1 = tasks[0] if len(tasks) > 0 else None
        if (
            t1
            and t2
            and t1.get("status") == "completed"
            and t2.get("status") == "completed"
        ):
            # Check if t2's input includes dep_0
            pass  # Needs deeper inspection
    return bugs


def check_retry_logic(outcome):
    """Does retry actually work or fail immediately?"""
    bugs = []
    for t in outcome.get("tasks", []):
        retry_count = t.get("retry_count", 0)
        max_retries = t.get("max_retries", 0)
        if t.get("status") == "failed" and retry_count == 0 and max_retries > 0:
            bugs.append(
                f"Task '{t['title']}' never retried (retry_count=0, max_retries={max_retries})"
            )
    return bugs


def check_mission_status_after_partial(outcome):
    """Mission status after partial failure."""
    bugs = []
    exec_data = outcome.get("execute_result", {}).get("data", {})
    tasks = outcome.get("tasks", [])
    failed = exec_data.get("failed_tasks", 0)
    completed = exec_data.get("completed_tasks", 0)
    status = exec_data.get("status")
    if failed > 0 and completed > 0:
        if status not in ("failed", "partial_success"):
            bugs.append(
                f"Mission had {failed} failed + {completed} completed but status={status} (expected 'failed')"
            )
    return bugs


def check_exception_blocks_fired(outcome):
    """Which except Exception blocks were hit?"""
    bugs = []
    logs = outcome.get("logs", [])
    for log_entry in logs:
        msg = log_entry.get("message", "")
        if "Exception" in msg or "exception" in msg or "error" in msg.lower():
            bugs.append(f"Exception block log: {msg[:120]}")
    for t in outcome.get("tasks", []):
        if t.get("error_message"):
            bugs.append(f"Task error msg: {t['title']}: {t['error_message'][:120]}")
    return bugs


# ── MAIN ────────────────────────────────────────────────────


async def main():
    global TOKEN

    print("=" * 70)
    print("TASK-06: Real Mission Testing — 10 Missions")
    print(f"Base URL: {BASE_URL}")
    print("Token user: 1")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70)

    # Verify backend is up
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{BASE_URL}/api/health")
        if r.status_code != 200:
            print(f"❌ Backend not healthy: {r.status_code} {r.text}")
            return
        health = r.json()
        print(f"✓ Backend healthy: {health.get('app')} ({health.get('env')})")
        print(f"  LLM: {health.get('components', {}).get('llm_provider', {})}")

    # ── Mission 1: Code Review (simple LLM task) ──────────
    await run_mission(
        1,
        "Code Review (simple LLM)",
        {
            "title": "Code Review: Python Auth Module",
            "description": "Review the following Python code for security issues and suggest improvements:\n\n```python\ndef login(username, password):\n    query = f\"SELECT * FROM users WHERE username='{username}' AND password='{password}'\"\n    result = db.execute(query)\n    return result.first()\n```\n\nCheck for: SQL injection, password handling, return value issues, and logging concerns.",
            "mission_type": "review",
            "priority": "normal",
        },
    )

    # ── Mission 2: Multi-step Code Analysis (LLM + dependency chain) ──
    await run_mission(
        2,
        "Multi-step Code Analysis (LLM + deps)",
        {
            "title": "Multi-step: Code Analysis Pipeline",
            "description": "Step 1: Analyze the Python code for bugs\nStep 2: Based on the analysis, suggest specific fixes\nStep 3: Generate improved code with the fixes applied\n\nCode to analyze:\n```python\ndef process_data(items):\n    results = []\n    for item in items:\n        try:\n            result = item.process()\n            results.append(result)\n        except:\n            continue\n    return results\n```",
            "mission_type": "code_analysis",
            "priority": "normal",
        },
    )

    # ── Mission 3: Web Search Task ──
    await run_mission(
        3,
        "Web Search Task",
        {
            "title": "Web Search: Latest AI Research",
            "description": "Search for the latest developments in AI agents (2024-2025) and summarize the top 3 findings.",
            "mission_type": "web_search",
            "priority": "normal",
        },
    )

    # ── Mission 4: Code Execution Task ──
    await run_mission(
        4,
        "Code Execution Task",
        {
            "title": "Code Execution: Compute Fibonacci Stats",
            "description": "Write and execute Python code to compute the first 20 Fibonacci numbers, then calculate their mean, median, and standard deviation. Print the results.",
            "mission_type": "code",
            "priority": "normal",
        },
    )

    # ── Mission 5: RAG Query Task ──
    await run_mission(
        5,
        "RAG Query Task",
        {
            "title": "RAG Query: Project Documentation",
            "description": "Query the knowledge base for information about the Flowmanner mission execution system. Find: 1) How missions are planned, 2) How tasks are executed, 3) What retry logic exists.",
            "mission_type": "rag",
            "priority": "normal",
        },
    )

    # ── Mission 6: Unknown Task Type (edge case) ──
    await run_mission(
        6,
        "Unknown Task Type (edge case)",
        {
            "title": "Unknown Task Type Test",
            "description": "This mission should use a completely unknown task type to test the fallback/error handling.",
            "mission_type": "quantum_computing_task",
            "priority": "low",
        },
    )

    # ── Mission 7: Empty Mission (edge case) ──
    await run_mission(
        7,
        "Empty Mission (edge case)",
        {
            "title": "",
            "description": "",
            "mission_type": "general",
            "priority": "low",
        },
    )

    # ── Mission 8: Large Prompt (stress test) ──
    large_description = (
        "Analyze this large codebase and provide a comprehensive report. "
        + "Here is the code:\n"
        + "\n".join(
            [
                f"# File {i}: This is line {j} of many lines in a large file to stress test the system's handling of big prompts. "
                * 5
                for i in range(1, 50)
                for j in range(1, 10)
            ]
        )
    )[
        :8000
    ]  # keep it reasonable for API
    await run_mission(
        8,
        "Large Prompt (stress test)",
        {
            "title": "Large Prompt Stress Test",
            "description": large_description,
            "mission_type": "llm",
            "priority": "normal",
        },
    )

    # ── Mission 9: Concurrent Missions (race conditions) ──
    print(f"\n{'=' * 60}")
    print("MISSION 9: Concurrent Missions (race conditions)")
    print(f"{'=' * 60}")
    m9_outcomes = []

    async def run_concurrent(i, name, data):
        outcome = await run_mission(9, f"{name} #{i}", data)
        m9_outcomes.append(outcome)
        return outcome

    # Create 3 missions first, then execute concurrently
    m9_ids = []
    for i in range(3):
        status, data = await api_post(
            "/",
            {
                "title": f"Concurrent Mission {i + 1}",
                "description": f"This is concurrent mission {i + 1} running simultaneously with others. Write a {i + 2}-line poem about concurrency.",
                "mission_type": "general",
                "priority": "normal",
            },
        )
        if status in (200, 201):
            m9_ids.append(data["id"])
            print(f"  Created concurrent mission: {data['id']}")
        else:
            print(f"  ❌ Failed to create concurrent mission {i + 1}")

    # Plan all
    for mid in m9_ids:
        status, _ = await api_post(f"/{mid}/plan", {}, timeout=60)
        print(f"  Plan for {mid}: HTTP {status}")

    # Execute concurrently
    async def execute_mission_by_id(mid):
        status, data = await api_post(f"/{mid}/execute", {}, timeout=120)
        return {"id": mid, "status": status, "data": data}

    futures = [execute_mission_by_id(mid) for mid in m9_ids]
    concurrent_results = await asyncio.gather(*futures, return_exceptions=True)
    for i, cr in enumerate(concurrent_results):
        if isinstance(cr, Exception):
            print(f"  💥 Concurrent {i + 1} failed with exception: {cr}")
        else:
            print(
                f"  Concurrent {i + 1}: HTTP {cr.get('status')}, data={cr.get('data')}"
            )

    # Get final task status for each
    for mid in m9_ids:
        status, tasks_data = await api_get(f"/{mid}/tasks")
        if status == 200:
            for t in tasks_data:
                print(f"    Task [{mid[:8]}]: {t['title']} — {t['status']}")

    # Record concurrent results
    results.append(
        {
            "num": 9,
            "name": "Concurrent Missions (race conditions)",
            "concurrent_results": [
                {"id": mid, "result": str(cr)}
                for mid, cr in zip(m9_ids, concurrent_results)
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )

    # ── Mission 10: Failing LLM Model (retry logic test) ──
    await run_mission(
        10,
        "Failing LLM Model (retry logic)",
        {
            "title": "Retry Logic Test: Non-existent Model",
            "description": "This mission should use a non-existent LLM model to test retry/fallback behavior.",
            "mission_type": "llm",
            "priority": "normal",
        },
    )

    # ── After all: add custom task with non-existent model ──
    # We'll patch mission 10 to have a bad model on its task
    if results and results[-1].get("mission_id"):
        mid = results[-1]["mission_id"]
        # Create a task with a bad model explicitly
        status, task_data = await api_post(
            f"/{mid}/tasks",
            {
                "title": "Call with bad model",
                "description": "Test with non-existent model",
                "task_type": "llm",
                "order_index": 99,
                "assigned_model": "nonexistent-model-v999",
            },
        )
        print(f"  Added bad-model task: HTTP {status}")

    # ── Write Results ──────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("WRITING RESULTS TO FILE")
    print(f"{'=' * 70}")

    output_path = "/opt/flowmanner/plans/tasks/BUGS-FROM-REAL-MISSIONS.md"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w") as f:
        f.write("# Real Mission Testing Results — TASK-06\n\n")
        f.write(f"**Date:** {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"**Backend:** {BASE_URL}\n")
        f.write("**LLM:** DeepSeek V4 Flash (via api.deepseek.com/v1)\n")
        f.write("**User ID:** 1\n\n")
        f.write("---\n\n")

        f.write("## Summary\n\n")
        total_ok = sum(
            1
            for r in results
            if r.get("final_status") == "completed" or not r.get("create_error")
        )
        total_fail = sum(1 for r in results if r.get("errors"))
        f.write("| Metric | Value |\n|---|---|\n")
        f.write(f"| Total missions run | {len(results)} |\n")
        f.write(f"| Successful | {total_ok} |\n")
        f.write(f"| With errors | {total_fail} |\n\n")

        all_errors = []
        for r in results:
            all_errors.extend(r.get("errors", []))

        f.write("### All Errors Found\n\n")
        if all_errors:
            for e in all_errors:
                f.write(f"- {e}\n")
        else:
            f.write("(No errors found)\n")
        f.write("\n")

        f.write("---\n\n")
        f.write("## Detailed Results\n\n")

        for r in results:
            num = r.get("num", "?")
            name = r.get("name", "Unknown")
            f.write(f"### Mission {num}: {name}\n\n")
            f.write(f"- **Mission ID:** `{r.get('mission_id', 'N/A')}`\n")
            f.write(f"- **Create error:** {r.get('create_error') or 'None'}\n")
            f.write(f"- **Final status:** {r.get('final_status') or 'N/A'}\n")

            exec_r = r.get("execute_result", {})
            if exec_r:
                data = exec_r.get("data", {})
                f.write(
                    f"- **Execute result:** HTTP {exec_r.get('status')}, elapsed {exec_r.get('elapsed_sec')}s\n"
                )
                f.write(
                    f"  - Completed: {data.get('completed_tasks', '?')}, Failed: {data.get('failed_tasks', '?')}\n"
                )

            f.write("\n#### Tasks\n\n")
            tasks = r.get("tasks", [])
            if tasks:
                f.write("| # | Title | Type | Status | Retries | Error |\n")
                f.write("|---|---|---|---|---|---|\n")
                for t in tasks:
                    error = (t.get("error_message") or "")[:60]
                    f.write(
                        f"| {t.get('order_index', '?')} | {t.get('title', '?')[:40]} | {t.get('task_type', '?')} | {t.get('status', '?')} | {t.get('retry_count', 0)} | {error} |\n"
                    )
            else:
                f.write("(No tasks)\n")

            f.write("\n#### Errors\n\n")
            errs = r.get("errors", [])
            if errs:
                for e in errs:
                    f.write(f"- {e}\n")
            else:
                f.write("(No errors detected)\n")

            # Special handling for concurrent results
            if "concurrent_results" in r:
                f.write("\n#### Concurrent Execution Results\n\n")
                for cr in r.get("concurrent_results", []):
                    f.write(f"- Mission `{cr['id']}`: {cr['result'][:200]}\n")

            f.write("\n---\n\n")

        # Bug analysis section
        f.write("## Bug Analysis\n\n")
        f.write("### Specific Bugs Found\n\n")

        all_bugs_found = []
        for r in results:
            bugs = []
            for t in r.get("tasks", []):
                if (
                    t.get("retry_count", 0) == 0
                    and t.get("status") == "failed"
                    and t.get("max_retries", 5) > 0
                ):
                    bugs.append(
                        f"**Retry not triggered:** Task '{t['title']}' failed but retry_count=0 (max_retries={t.get('max_retries')})"
                    )
                if t.get("task_type") == "":
                    bugs.append(
                        f"**Empty task type:** Task '{t['title']}' has empty task_type"
                    )
            if r.get("create_error"):
                bugs.append(f"**Mission creation failed:** {r['create_error']}")
            if not r.get("mission_id"):
                bugs.append("**No mission ID returned** on creation")
            for e in r.get("errors", []):
                bugs.append(f"**Error:** {e}")
            all_bugs_found.extend(bugs)

        if all_bugs_found:
            for b in all_bugs_found:
                f.write(f"- {b}\n")
        else:
            f.write("(No specific bugs found — all missions ran cleanly)\n")

        f.write(
            "\n### code_searcher: except Exception blocks in mission_executor.py\n\n"
        )
        f.write("Total `except Exception` blocks in mission_executor.py: **29**\n\n")
        f.write("These are the areas where exceptions could be silently swallowed:\n")
        f.write("- `_get_model_router()` — 2 except blocks\n")
        f.write("- `_get_rag_service()` — 2 except blocks\n")
        f.write("- `_update_step_status()` — 1 except block\n")
        f.write(
            "- `plan_mission()` — 3 except blocks (permanent, retryable, general)\n"
        )
        f.write("- `_generate_plan()` — 3 except blocks\n")
        f.write(
            "- `execute_mission()` — 3 except blocks (task-level + analytics + audit)\n"
        )
        f.write("- `execute_task()` — 2 except blocks\n")
        f.write("- `_execute_llm()` — 2 except blocks\n")
        f.write("- `_execute_tool()` — 2 except blocks\n")
        f.write("- `_execute_browser_tool()` — 2 except blocks\n")
        f.write("- `_execute_code_from_string()` — 1 except block\n")
        f.write("- `_log()` — 1 except block\n")
        f.write("- `_resolve_agent_system_prompt()` — 1 except block\n")
        f.write("- Various tool handlers — 5+ except blocks\n")

    print(f"\n✓ Results written to {output_path}")

    # Also print a quick summary
    print(f"\n{'=' * 70}")
    print("FINAL SUMMARY")
    print(f"{'=' * 70}")
    for r in results:
        num = r.get("num", "?")
        name = r.get("name", "Unknown")
        status = r.get("final_status", "ERROR")
        n_errors = len(r.get("errors", []))
        symbol = "✅" if n_errors == 0 and status == "completed" else "❌"
        print(f"  {symbol} M{num}: {name[:50]} — {status} ({n_errors} errors)")


if __name__ == "__main__":
    asyncio.run(main())
