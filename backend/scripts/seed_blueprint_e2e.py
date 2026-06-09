#!/usr/bin/env python3
"""End-to-end blueprint seed — create → publish → run via V2 API.

Runs against the live backend container with a real DB.
Usage: python3 scripts/seed_blueprint_e2e.py
"""

import json
import sys

import requests

BASE = "http://localhost:8000"
API = f"{BASE}/api/v2"


def get_token(user_id: int = 1) -> str:
    """Generate a JWT token for the given user.

    Must be run inside the backend container where 'app' is importable.
    """
    from app.services.auth_service import create_access_token

    return create_access_token(user_id=user_id)


def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def pretty(label: str, data: dict | list) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print(f"{'─' * 60}")
    print(json.dumps(data, indent=2, default=str)[:2000])


def main() -> int:
    # ── Health check ──────────────────────────────────────────────
    print("🔍 Health check…")
    r = requests.get(f"{BASE}/health", timeout=5)
    if r.status_code != 200:
        print(f"❌ Backend unhealthy ({r.status_code})")
        return 1
    print("✅ Backend healthy")

    # ── Auth token ────────────────────────────────────────────────
    token = get_token(user_id=1)
    h = headers(token)
    print(f"✅ JWT generated for user_id=1")

    # ── 1. Create blueprint ───────────────────────────────────────
    print("\n📦 Step 1: Create blueprint…")
    payload = {
        "title": "Data Processing Pipeline",
        "description": "A sample DAG blueprint that fetches, transforms, and summarizes data.",
        "blueprint_type": "dag",
        "tags": ["demo", "data", "pipeline"],
        "category": "data-engineering",
        "icon": "database",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_url": {
                    "type": "string",
                    "description": "URL to fetch data from",
                },
                "format": {
                    "type": "string",
                    "enum": ["json", "csv"],
                    "default": "json",
                },
            },
            "required": ["source_url"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "row_count": {"type": "integer"},
            },
        },
        "definition": {
            "blueprint_type": "dag",
            "nodes": [
                {
                    "id": "fetch",
                    "type": "llm_call",
                    "title": "Fetch Data",
                    "description": "Retrieve raw data from the source URL",
                    "config": {"prompt": "Fetch data from {{input.source_url}}"},
                    "assigned_model": "deepseek-chat",
                },
                {
                    "id": "transform",
                    "type": "llm_call",
                    "title": "Transform Data",
                    "description": "Clean and structure the raw data",
                    "dependencies": ["fetch"],
                    "config": {
                        "prompt": "Transform the fetched data into {{input.format}} format"
                    },
                    "assigned_model": "deepseek-chat",
                },
                {
                    "id": "summarize",
                    "type": "llm_call",
                    "title": "Summarize",
                    "description": "Generate a summary of the processed data",
                    "dependencies": ["transform"],
                    "config": {"prompt": "Summarize the data and count rows"},
                    "assigned_model": "deepseek-chat",
                },
            ],
            "edges": [
                {"source": "fetch", "target": "transform"},
                {"source": "transform", "target": "summarize"},
            ],
            "budget": {"max_cost_usd": 5.0, "max_wall_time_seconds": 120},
        },
    }

    r = requests.post(f"{API}/blueprints", json=payload, headers=h, timeout=10)
    if r.status_code != 201:
        print(f"❌ Create failed: {r.status_code} — {r.text[:500]}")
        return 1
    bp = r.json()["data"]
    bp_id = bp["id"]
    pretty("Created Blueprint", bp)
    print(
        f"\n✅ Blueprint created: id={bp_id}  status={bp['status']}  version={bp['version']}"
    )

    # ── 2. Get blueprint ──────────────────────────────────────────
    print("\n🔍 Step 2: Get blueprint…")
    r = requests.get(f"{API}/blueprints/{bp_id}", headers=h, timeout=10)
    if r.status_code != 200:
        print(f"❌ Get failed: {r.status_code}")
        return 1
    bp_get = r.json()["data"]
    assert bp_get["id"] == bp_id, "ID mismatch"
    assert bp_get["status"] == "draft", f"Expected draft, got {bp_get['status']}"
    print(f"✅ Fetched blueprint: status={bp_get['status']}  title={bp_get['title']}")

    # ── 3. Update blueprint (add a description tweak) ─────────────
    print("\n✏️  Step 3: Update blueprint…")
    r = requests.patch(
        f"{API}/blueprints/{bp_id}",
        json={"description": "Updated: A sample DAG blueprint — now with better docs!"},
        headers=h,
        timeout=10,
    )
    if r.status_code != 200:
        print(f"❌ Update failed: {r.status_code} — {r.text[:300]}")
        return 1
    bp_upd = r.json()["data"]
    print(
        f"✅ Updated: version={bp_upd['version']}  desc={bp_upd['description'][:60]}…"
    )

    # ── 4. List versions ──────────────────────────────────────────
    print("\n📋 Step 4: List versions…")
    r = requests.get(f"{API}/blueprints/{bp_id}/versions", headers=h, timeout=10)
    if r.status_code != 200:
        print(f"❌ Versions failed: {r.status_code}")
        return 1
    versions = r.json()["data"]
    print(f"✅ Version history: {len(versions)} version(s)")
    for v in versions:
        print(f"   v{v['version']} — created {v.get('created_at', '?')[:19]}")

    # ── 5. Publish blueprint ──────────────────────────────────────
    print("\n🚀 Step 5: Publish blueprint…")
    r = requests.post(f"{API}/blueprints/{bp_id}/publish", headers=h, timeout=10)
    if r.status_code != 200:
        print(f"❌ Publish failed: {r.status_code} — {r.text[:500]}")
        return 1
    bp_pub = r.json()["data"]
    assert (
        bp_pub["status"] == "published"
    ), f"Expected published, got {bp_pub['status']}"
    print(f"✅ Published: status={bp_pub['status']}")

    # ── 6. Run blueprint ──────────────────────────────────────────
    print("\n▶️  Step 6: Run blueprint…")
    run_payload = {
        "input_data": {
            "source_url": "https://api.example.com/data/sales-2026.json",
            "format": "json",
        },
    }
    r = requests.post(
        f"{API}/blueprints/{bp_id}/run", json=run_payload, headers=h, timeout=300
    )
    if r.status_code != 201:
        print(f"❌ Run failed: {r.status_code} — {r.text[:500]}")
        return 1
    run = r.json()["data"]
    run_id = run["id"]
    pretty("Created Run", run)
    print(f"\n✅ Run created: id={run_id}  status={run['status']}")

    # ── 7. Get run ────────────────────────────────────────────────
    print("\n🔍 Step 7: Get run…")
    r = requests.get(f"{API}/runs/{run_id}", headers=h, timeout=10)
    if r.status_code != 200:
        print(f"❌ Get run failed: {r.status_code}")
        return 1
    run_get = r.json()["data"]
    print(
        f"✅ Fetched run: status={run_get['status']}  snapshot_keys={list(run_get.get('snapshot', {}).keys())[:5]}"
    )

    # ── 8. List runs ──────────────────────────────────────────────
    print("\n📋 Step 8: List runs…")
    r = requests.get(f"{API}/runs?blueprint_id={bp_id}", headers=h, timeout=10)
    if r.status_code != 200:
        print(f"❌ List runs failed: {r.status_code}")
        return 1
    runs_page = r.json()
    run_items = runs_page.get("data", {}).get("items", runs_page.get("items", []))
    print(f"✅ Runs for this blueprint: {len(run_items)} run(s)")

    # ── 9. List blueprints ────────────────────────────────────────
    print("\n📋 Step 9: List blueprints…")
    r = requests.get(f"{API}/blueprints?blueprint_type=dag", headers=h, timeout=10)
    if r.status_code != 200:
        print(f"❌ List blueprints failed: {r.status_code}")
        return 1
    bp_page = r.json()
    bp_items = bp_page.get("data", {}).get("items", bp_page.get("items", []))
    print(f"✅ DAG blueprints: {len(bp_items)} blueprint(s)")

    # ── Summary ───────────────────────────────────────────────────
    print(
        f"""
{"═" * 60}
  🎉  END-TO-END SEED COMPLETE
{"═" * 60}
  Blueprint ID : {bp_id}
  Title        : {bp_pub["title"]}
  Type         : {bp_pub["blueprint_type"]}
  Status       : {bp_pub["status"]}
  Version      : {bp_pub["version"]}
  Nodes        : {len(payload["definition"]["nodes"])}

  Run ID       : {run_id}
  Run Status   : {run["status"]}
  Input        : source_url → api.example.com/data/sales-2026.json
{"═" * 60}
"""
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except requests.ConnectionError:
        print("❌ Cannot connect to backend. Is the container running?")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
