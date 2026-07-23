#!/usr/bin/env python3
"""Live-substrate smoke harness for the TODO-03 blueprints.

Pushes each new blueprint to the dev backend, runs it with safe inputs, and
records the terminal state. HITL blueprints are paused at approval/human_review
nodes; the harness auto-resolves those inbox items and resumes the runs.

Run from the repo root:
    python3 scripts/live_test_blueprints.py

Requirements:
- Backend dev stack is up (http://127.0.0.1:8000)
- flowmanner CLI is already logged in (~/.flowmanner/config.json has a token)

Notes:
- A local HTTP sinkhole is started on a random port to receive webhooks.
- Each pushed blueprint is soft-deleted after its run is recorded.
- HITL runs are paused, the created inbox items are approved, and the run is
  resumed through the v2 /runs/{id}/resume endpoint.
"""

from __future__ import annotations

import http.server
import json
import os
import socketserver
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
import yaml

BASE_URL = "http://127.0.0.1:8000"
CREDS_PATH = Path.home() / ".flowmanner" / "config.json"
REPO_ROOT = Path(__file__).resolve().parents[1]

POLL_INTERVAL = 2.0
MAX_POLL_SECONDS = 300.0
INBOX_LOOKUP_RETRIES = 5
INBOX_LOOKUP_DELAY = 1.0


class _SinkholeHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: D401, N802
        # Drain the request body to keep the client happy regardless of headers.
        try:
            self.rfile.read()
        except Exception:
            pass
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):  # noqa: D401, A002
        pass


def start_sinkhole() -> tuple[str, socketserver.TCPServer, threading.Thread]:
    """Start a local HTTP sinkhole that returns 200 to every POST."""
    server = socketserver.TCPServer(("127.0.0.1", 0), _SinkholeHandler)
    server.allow_reuse_address = True
    _, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{port}/null", server, thread


@dataclass
class RunResult:
    file: str
    name: str
    blueprint_id: str | None = None
    run_id: str | None = None
    status: str | None = None
    terminal: bool = False
    paused_at: float | None = None
    resumed: bool = False
    error: str | None = None
    cost_usd: float = 0.0
    tokens: int = 0
    events: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "completed" and self.terminal


TEST_USER_EMAIL = os.environ.get("FLOWMANNER_TEST_EMAIL", "live-test@flowmanner.local")
TEST_USER_PASSWORD = os.environ.get("FLOWMANNER_TEST_PASSWORD")
TEST_USER_FULL_NAME = os.environ.get("FLOWMANNER_TEST_FULL_NAME", "Live Test")
TEST_USER_USERNAME = os.environ.get("FLOWMANNER_TEST_USERNAME", "livetest")


def _login(email: str, password: str) -> str | None:
    try:
        resp = requests.post(
            f"{BASE_URL}/api/v2/auth/login",
            json={"email": email, "password": password},
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=10,
        )
        if not resp.ok:
            return None
        data = resp.json()
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        return data.get("access_token")
    except Exception:
        return None


def _register(email: str, password: str, full_name: str, username: str) -> bool:
    try:
        resp = requests.post(
            f"{BASE_URL}/api/v2/auth/register",
            json={
                "email": email,
                "password": password,
                "full_name": full_name,
                "username": username,
            },
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=10,
        )
        return resp.ok
    except Exception:
        return False


def ensure_token() -> str:
    if not TEST_USER_PASSWORD:
        raise SystemExit(
            "Set FLOWMANNER_TEST_PASSWORD to a strong dev-only password "
            "before running live-substrate tests."
        )
    # Prefer the CLI token if still valid
    token: str | None = None
    if CREDS_PATH.exists():
        creds = json.loads(CREDS_PATH.read_text())
        token = creds.get("token")
        if token:
            try:
                me = requests.get(
                    f"{BASE_URL}/api/v2/auth/me",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                    },
                    timeout=10,
                )
                if me.ok:
                    return token
            except Exception:
                pass

    # Try to log in the live-test user; if missing, create it
    token = _login(TEST_USER_EMAIL, TEST_USER_PASSWORD)
    if token:
        return token

    if _register(
        TEST_USER_EMAIL, TEST_USER_PASSWORD, TEST_USER_FULL_NAME, TEST_USER_USERNAME
    ):
        token = _login(TEST_USER_EMAIL, TEST_USER_PASSWORD)

    if token:
        return token
    raise SystemExit(
        "Unable to obtain a valid auth token. Check the backend and credentials."
    )


def load_token() -> str:
    return ensure_token()


def health_check() -> None:
    try:
        resp = requests.get(f"{BASE_URL}/api/health", timeout=5)
        resp.raise_for_status()
    except Exception as exc:
        raise SystemExit(f"Backend is not reachable at {BASE_URL}: {exc}")


def api(
    token: str, method: str, path: str, payload: Any = None, *, v2: bool = True
) -> Any:
    url = f"{BASE_URL}/api/{'v2' if v2 else 'v1'}{path}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    response = requests.request(method, url, headers=headers, json=payload, timeout=30)
    try:
        data = response.json() if response.text else {}
    except Exception:
        data = {"raw": response.text}
    if not response.ok:
        raise RuntimeError(f"{method} {path} -> {response.status_code}: {data}")
    # v2 envelope
    if isinstance(data, dict) and "data" in data:
        return data["data"]
    return data


def push_blueprint(token: str, file_path: Path) -> dict:
    raw = yaml.safe_load(file_path.read_text())
    payload = {
        "title": raw["name"],
        "description": raw.get("description", ""),
        "blueprint_type": raw["blueprint_type"],
        "definition": {
            "blueprint_type": raw["definition"].get(
                "blueprint_type", raw["blueprint_type"]
            ),
            "nodes": raw["definition"].get("nodes", []),
            "edges": raw["definition"].get("edges", []),
            "budget": raw["definition"].get("budget", {}),
            "config": raw["definition"].get("config", {}),
        },
        "input_schema": raw.get("inputs") if raw.get("inputs") else None,
        "output_schema": raw.get("outputs") if raw.get("outputs") else None,
    }
    return api(token, "POST", "/blueprints/", payload)


def delete_blueprint(token: str, blueprint_id: str) -> None:
    try:
        api(token, "DELETE", f"/blueprints/{blueprint_id}")
    except Exception as exc:
        print(f"  [warn] failed to delete blueprint {blueprint_id}: {exc}")


def run_blueprint(token: str, blueprint_id: str, inputs: dict, budget: dict) -> dict:
    return api(
        token,
        "POST",
        f"/blueprints/{blueprint_id}/run",
        {
            "input_data": inputs,
            "budget_override": budget,
        },
    )


def get_run(token: str, run_id: str) -> dict:
    return api(token, "GET", f"/runs/{run_id}")


def _extract_items(response: Any) -> list[dict]:
    if isinstance(response, list):
        return response
    if isinstance(response, dict):
        return (
            response.get("data")
            or response.get("items")
            or response.get("results")
            or []
        )
    return []


def list_inbox_for_mission(token: str, mission_id: str) -> list[dict]:
    """List inbox items for a mission, retrying if the item is not yet created."""
    for attempt in range(INBOX_LOOKUP_RETRIES):
        try:
            response = api(token, "GET", f"/inbox/by-mission/{mission_id}", v2=False)
            items = _extract_items(response)
            pending = [it for it in items if it.get("status") == "pending"]
            if pending:
                return pending
            # No pending items yet; wait and retry if we still have attempts left
            if attempt < INBOX_LOOKUP_RETRIES - 1:
                time.sleep(INBOX_LOOKUP_DELAY)
        except Exception as exc:
            if attempt == INBOX_LOOKUP_RETRIES - 1:
                print(f"  [warn] could not list inbox for {mission_id}: {exc}")
                break
            time.sleep(INBOX_LOOKUP_DELAY)
    return []


def approve_inbox(token: str, item_id: str) -> None:
    api(token, "POST", f"/inbox/{item_id}/approve", {}, v2=False)


def resume_run(token: str, run_id: str) -> dict:
    return api(token, "POST", f"/runs/{run_id}/resume", {})


def get_run_events(token: str, run_id: str) -> list[dict]:
    try:
        data = api(token, "GET", f"/runs/{run_id}/events")
        return data.get("events", []) if isinstance(data, dict) else []
    except Exception as exc:
        print(f"  [warn] could not fetch events for {run_id}: {exc}")
        return []


def poll_run(
    token: str,
    result: RunResult,
    *,
    expect_hitl: bool,
) -> None:
    run_id = result.run_id
    assert run_id
    deadline = time.time() + MAX_POLL_SECONDS
    while time.time() < deadline:
        run = get_run(token, run_id)
        result.status = run.get("status")
        result.cost_usd = float(run.get("total_cost_usd") or 0.0)
        result.tokens = int(run.get("total_tokens") or 0)

        if result.status in {"completed", "failed", "aborted"}:
            result.terminal = True
            return

        if result.status == "paused":
            result.paused_at = time.time()
            if not expect_hitl:
                result.notes.append("run paused unexpectedly (no HITL expected)")
            return

        time.sleep(POLL_INTERVAL)

    result.notes.append(f"polling timed out after {MAX_POLL_SECONDS}s")
    result.status = "timeout"


def handle_hitl(token: str, result: RunResult, mission_id: str) -> None:
    result.notes.append("run paused; attempting HITL auto-approval")
    items = list_inbox_for_mission(token, mission_id)
    if not items:
        result.notes.append("no pending inbox items found; cannot resume")
        return
    for item in items:
        approve_inbox(token, item["id"])
        result.notes.append(f"approved inbox item {item['id']}")
    resumed = resume_run(token, result.run_id)
    result.resumed = resumed.get("status") == "executing"


def _event_type_counts(events: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ev in events:
        counts[ev.get("type", "unknown")] = counts.get(ev.get("type", "unknown"), 0) + 1
    return counts


def test_blueprint(
    token: str,
    file_path: Path,
    inputs: dict,
    expect_hitl: bool,
    budget: dict,
) -> RunResult:
    raw = yaml.safe_load(file_path.read_text())
    name = raw["name"]
    result = RunResult(file=str(file_path), name=name)

    print(f"\n▶ {name}")
    try:
        bp = push_blueprint(token, file_path)
        result.blueprint_id = bp.get("id")
        print(f"  pushed -> {result.blueprint_id}")
    except Exception as exc:
        result.error = f"push failed: {exc}"
        result.status = "push_failed"
        return result

    try:
        run = run_blueprint(token, result.blueprint_id, inputs, budget)
        result.run_id = run.get("id")
        result.status = run.get("status")
        print(f"  run    -> {result.run_id} (status {result.status})")
    except Exception as exc:
        result.error = f"run failed: {exc}"
        result.status = "run_failed"
        return result

    poll_run(token, result, expect_hitl=expect_hitl)

    # Resolve HITL if the run paused and we expected it
    if result.status == "paused" and expect_hitl:
        run = get_run(token, result.run_id)
        mission_id = run.get("mission_id") or run.get("id")
        handle_hitl(token, result, mission_id)
        if result.resumed:
            poll_run(token, result, expect_hitl=False)

    run = get_run(token, result.run_id)
    result.events = get_run_events(token, result.run_id)
    result.cost_usd = float(run.get("total_cost_usd") or 0.0)
    result.tokens = int(run.get("total_tokens") or 0)

    if result.terminal and result.status == "completed":
        print(f"  completed (${result.cost_usd:.4f}, {result.tokens} tokens)")
    elif result.terminal and result.status == "failed":
        result.error = run.get("error_message") or "failed"
        print(f"  failed: {result.error}")
    else:
        result.notes.append(f"ended in status {result.status}")
        print(f"  ended: {result.status}")

    return result


def generate_report(results: list[RunResult]) -> str:
    lines = [
        "# TODO-03 Blueprint Live Substrate Report\n\n",
        f"- Base URL: {BASE_URL}\n",
        f"- Tested: {len(results)} blueprints\n",
        "\n## Summary\n\n",
        "| Blueprint | Status | Cost | Tokens | Notes |\n",
        "|-----------|--------|------|--------|-------|\n",
    ]
    for r in results:
        notes = "; ".join(r.notes) if r.notes else ""
        lines.append(
            f"| {r.name} | {r.status} | ${r.cost_usd:.4f} | {r.tokens} | {notes} |\n"
        )

    lines.append("\n## Details\n")
    for r in results:
        lines.append(f"\n### {r.name}\n")
        lines.append(f"- File: `{r.file}`\n")
        lines.append(f"- Blueprint ID: `{r.blueprint_id}`\n")
        lines.append(f"- Run ID: `{r.run_id}`\n")
        lines.append(f"- Terminal status: `{r.status}`\n")
        lines.append(f"- Cost: ${r.cost_usd:.4f}\n")
        lines.append(f"- Tokens: {r.tokens}\n")
        if r.error:
            lines.append(f"- Error: `{r.error}`\n")
        if r.notes:
            lines.append(f"- Notes: {', '.join(r.notes)}\n")
        if r.events:
            counts = _event_type_counts(r.events)
            lines.append(
                "- Event types: "
                + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
                + "\n"
            )

    return "".join(lines)


def main() -> None:
    health_check()
    token = load_token()
    sinkhole_url, sinkhole_server, _sinkhole_thread = start_sinkhole()
    print(f"Webhook sinkhole listening on {sinkhole_url}")

    # (file, inputs, expect_hitl, budget_override)
    specs: list[tuple[str, dict[str, Any], bool, dict[str, Any]]] = [
        (
            "backend/flowmanner-web-recon-batch.yaml",
            {"urls": ["http://example.com"], "model": ""},
            False,
            {"max_cost_usd": 2.0, "max_wall_time_seconds": 180, "max_iterations": 10},
        ),
        (
            "backend/flowmanner-support-agent.yaml",
            {"ticket_text": "Live-test ticket: customer cannot log in.", "model": ""},
            False,
            {"max_cost_usd": 2.0, "max_wall_time_seconds": 180},
        ),
        (
            "backend/flowmanner-budget-governor.yaml",
            {
                "task_prompt": "Summarize the following sentence in one word.",
                "budget_ceiling": 1.0,
                "model": "",
            },
            False,
            {"max_cost_usd": 1.0, "max_wall_time_seconds": 120},
        ),
        (
            "backend/flowmanner-spend-anomaly-sentinel.yaml",
            {"alert_webhook_url": sinkhole_url, "spend_threshold": 1000.0},
            False,
            {"max_cost_usd": 1.0, "max_wall_time_seconds": 120},
        ),
        (
            "backend/flowmanner-shadow-rollout.yaml",
            {
                "task_prompt": "Return the word 'hello'.",
                "current_model": "",
                "candidate_model": "",
            },
            False,
            {"max_cost_usd": 2.0, "max_wall_time_seconds": 180},
        ),
        (
            "backend/flowmanner-dry-run-preview.yaml",
            {
                "webhook_url": sinkhole_url,
                "payload_template": "Hello {{ context_data }}",
                "context_data": "world",
            },
            True,
            {"max_cost_usd": 1.0, "max_wall_time_seconds": 120},
        ),
        (
            "backend/flowmanner-chaos-drill.yaml",
            {"chaos_mode": "off"},
            False,
            {"max_cost_usd": 1.0, "max_wall_time_seconds": 120},
        ),
        (
            "backend/flowmanner-audit-log.yaml",
            {"audit_topic": "live-test", "collection": "flowmanner_live_test"},
            False,
            {"max_cost_usd": 1.0, "max_wall_time_seconds": 120},
        ),
        (
            "backend/flowmanner-retention-enforcer.yaml",
            {
                "collection": "flowmanner_live_test",
                "retention_days": 999,
                "alert_webhook_url": sinkhole_url,
            },
            True,
            {"max_cost_usd": 1.0, "max_wall_time_seconds": 120},
        ),
    ]

    results: list[RunResult] = []
    try:
        for rel_path, inputs, expect_hitl, budget in specs:
            file_path = REPO_ROOT / rel_path
            if not file_path.exists():
                print(f"Skipping missing file: {file_path}")
                continue
            result = test_blueprint(token, file_path, inputs, expect_hitl, budget)
            results.append(result)
    finally:
        # Clean up pushed blueprints
        for result in results:
            if result.blueprint_id:
                delete_blueprint(token, result.blueprint_id)
        sinkhole_server.shutdown()

    report = generate_report(results)
    report_path = (
        REPO_ROOT / "scripts" / "live-test-reports" / "TODO-03-live-substrate-report.md"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)
    print(f"\nReport written to {report_path}\n")

    failed = [r for r in results if not r.ok]
    if failed:
        print(f"FAILED ({len(failed)}): " + ", ".join(r.name for r in failed))
        sys.exit(1)
    print("ALL BLUEPRINTS COMPLETED")


if __name__ == "__main__":
    main()
