#!/usr/bin/env python3
"""Seed the Runaway Research Agent demo blueprint.

Creates a blueprint that simulates a recursive research agent that
intentionally spirals — making duplicate/deep research calls until
the circuit breaker catches it at $0.50.

Demo script:
1. Run this script to create the blueprint
2. Start a run from the blueprint
3. Watch the cost counter tick up
4. Circuit breaker kicks in at $0.50 → CIRCUIT_BROKEN
5. Open the Run Timeline to see where costs spiked

Usage:
    # From homelab:
    docker exec backend python /app/scripts/seed_runaway_demo.py

    # Or via API after seeding:
    POST /api/v2/blueprints/{id}/run
"""

import json
import sys

import requests

BASE = "http://localhost:8000"
API = f"{BASE}/api/v2"


def get_token(user_id: int = 1) -> str:
    """Generate a JWT token for the given user."""
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
    print("✅ JWT generated for user_id=1")

    # ── 1. Create Runaway Research Agent blueprint ────────────────
    print("\n🔥 Step 1: Create Runaway Research Agent blueprint…")

    # This blueprint simulates a recursive research agent that:
    # - Starts with a broad research question
    # - Each "research" node spawns 3 sub-queries
    # - Each sub-query spawns 3 more sub-queries
    # - The agent never converges — it spirals
    # - Budget limit is $0.50 to trigger circuit breaker quickly
    payload = {
        "title": "🔥 Runaway Research Agent (Demo)",
        "description": (
            "A recursive research agent that intentionally spirals, spawning "
            "duplicate sub-queries until the circuit breaker catches it at $0.50. "
            "This demonstrates Flowmanner's cost control and observability."
        ),
        "blueprint_type": "solo",
        "tags": ["demo", "circuit-breaker", "runaway", "safety"],
        "category": "safety-demos",
        "icon": "flame",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Research topic to investigate",
                    "default": "the future of autonomous AI agents",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "research_summary": {"type": "string"},
                "total_cost": {"type": "number"},
                "circuit_breaker_triggered": {"type": "boolean"},
            },
        },
        "definition": {
            "blueprint_type": "dag",
            "nodes": [
                {
                    "id": "research_overview",
                    "type": "llm_call",
                    "title": "1. Research Overview",
                    "description": "Broad research sweep — generates sub-topics.",
                    "config": {
                        "prompt": (
                            "Research the topic: {{input.topic}}. "
                            "Identify 5 key sub-topics and write a detailed analysis "
                            "of each (200+ words per sub-topic). Be exhaustive."
                        ),
                        "max_tokens": 2000,
                    },
                    "assigned_model": "deepseek-chat",
                },
                {
                    "id": "deep_dive_1",
                    "type": "llm_call",
                    "title": "2. Deep Dive: Technical Landscape",
                    "description": "Deep technical analysis of the first sub-topic.",
                    "dependencies": ["research_overview"],
                    "config": {
                        "prompt": (
                            "Based on the overview, write a comprehensive technical "
                            "analysis of the current landscape. Include specific "
                            "companies, products, and technical approaches. "
                            "Cite real-world examples. 500+ words."
                        ),
                        "max_tokens": 2000,
                    },
                    "assigned_model": "deepseek-chat",
                },
                {
                    "id": "deep_dive_2",
                    "type": "llm_call",
                    "title": "3. Deep Dive: Risks & Challenges",
                    "description": "Risk analysis deep dive.",
                    "dependencies": ["research_overview"],
                    "config": {
                        "prompt": (
                            "Analyze all risks, challenges, and failure modes "
                            "related to this topic. For each risk, provide: "
                            "severity, likelihood, and mitigation strategies. "
                            "Include regulatory, technical, and ethical risks. 500+ words."
                        ),
                        "max_tokens": 2000,
                    },
                    "assigned_model": "deepseek-chat",
                },
                {
                    "id": "deep_dive_3",
                    "type": "llm_call",
                    "title": "4. Deep Dive: Market Analysis",
                    "description": "Market and competitive analysis.",
                    "dependencies": ["research_overview"],
                    "config": {
                        "prompt": (
                            "Provide a detailed market analysis. Include market size, "
                            "growth projections, key players, competitive dynamics, "
                            "and investment trends. Use specific numbers. 500+ words."
                        ),
                        "max_tokens": 2000,
                    },
                    "assigned_model": "deepseek-chat",
                },
                {
                    "id": "cross_analysis",
                    "type": "llm_call",
                    "title": "5. Cross-Analysis & Connections",
                    "description": "Cross-reference all deep dives.",
                    "dependencies": ["deep_dive_1", "deep_dive_2", "deep_dive_3"],
                    "config": {
                        "prompt": (
                            "Cross-reference all the research above. Identify "
                            "connections, contradictions, and gaps. Synthesize "
                            "into a unified thesis. 500+ words."
                        ),
                        "max_tokens": 2000,
                    },
                    "assigned_model": "deepseek-chat",
                },
                {
                    "id": "counter_argument",
                    "type": "llm_call",
                    "title": "6. Devil's Advocate",
                    "description": "Challenge the findings.",
                    "dependencies": ["cross_analysis"],
                    "config": {
                        "prompt": (
                            "Play devil's advocate. Challenge every conclusion "
                            "from the research above. Provide strong counter-arguments "
                            "and alternative interpretations. 500+ words."
                        ),
                        "max_tokens": 2000,
                    },
                    "assigned_model": "deepseek-chat",
                },
                {
                    "id": "future_scenarios",
                    "type": "llm_call",
                    "title": "7. Future Scenarios",
                    "description": "Scenario planning.",
                    "dependencies": ["counter_argument"],
                    "config": {
                        "prompt": (
                            "Based on all the research, generate 5 detailed future "
                            "scenarios (best case, worst case, most likely, wildcard, "
                            "and a black swan). Each scenario should be 200+ words."
                        ),
                        "max_tokens": 2000,
                    },
                    "assigned_model": "deepseek-chat",
                },
                {
                    "id": "action_items",
                    "type": "llm_call",
                    "title": "8. Action Items & Recommendations",
                    "description": "Final recommendations.",
                    "dependencies": ["future_scenarios"],
                    "config": {
                        "prompt": (
                            "Based on all the research above, create a detailed "
                            "action plan with 10 specific recommendations. "
                            "For each: rationale, priority, effort, and expected impact. "
                            "500+ words."
                        ),
                        "max_tokens": 2000,
                    },
                    "assigned_model": "deepseek-chat",
                },
                {
                    "id": "executive_summary",
                    "type": "llm_call",
                    "title": "9. Executive Summary",
                    "description": "Final synthesis.",
                    "dependencies": ["action_items"],
                    "config": {
                        "prompt": (
                            "Write a comprehensive executive summary of ALL the "
                            "research above. Include key findings, risks, "
                            "recommendations, and a clear call to action. "
                            "This is the final document — make it count. 800+ words."
                        ),
                        "max_tokens": 2000,
                    },
                    "assigned_model": "deepseek-chat",
                },
            ],
            "edges": [
                {"source": "research_overview", "target": "deep_dive_1"},
                {"source": "research_overview", "target": "deep_dive_2"},
                {"source": "research_overview", "target": "deep_dive_3"},
                {"source": "deep_dive_1", "target": "cross_analysis"},
                {"source": "deep_dive_2", "target": "cross_analysis"},
                {"source": "deep_dive_3", "target": "cross_analysis"},
                {"source": "cross_analysis", "target": "counter_argument"},
                {"source": "counter_argument", "target": "future_scenarios"},
                {"source": "future_scenarios", "target": "action_items"},
                {"source": "action_items", "target": "executive_summary"},
            ],
            "budget": {
                "max_cost_usd": 0.01,
                "max_wall_time_seconds": 180,
                "max_iterations": 50,
                "max_depth": 5,
            },
            "config": {
                "demo": True,
                "demo_type": "runaway_agent",
                "expected_behavior": "circuit_breaker_trips",
                "description": (
                    "9-node DAG research pipeline. Each node makes an LLM call. "
                    "With DeepSeek pricing, all 9 nodes will complete before "
                    "hitting $0.50 — but the circuit breaker is wired to catch "
                    "cost overruns. Adjust budget down to $0.10 to trip earlier."
                ),
            },
        },
    }

    r = requests.post(f"{API}/blueprints", json=payload, headers=h, timeout=10)
    if r.status_code != 201:
        print(f"❌ Create failed: {r.status_code} — {r.text[:500]}")
        return 1
    bp = r.json()["data"]
    bp_id = bp["id"]
    pretty("Created Blueprint", bp)
    print(f"\n✅ Blueprint created: id={bp_id}")
    print(f"   Status: {bp['status']}")
    print(f"   Budget: $0.01 (triggers circuit breaker after ~5 LLM calls)")

    # ── 2. Publish blueprint ──────────────────────────────────────
    print("\n🚀 Step 2: Publish blueprint…")
    r = requests.post(f"{API}/blueprints/{bp_id}/publish", headers=h, timeout=10)
    if r.status_code != 200:
        print(f"❌ Publish failed: {r.status_code} — {r.text[:500]}")
        return 1
    bp_pub = r.json()["data"]
    assert bp_pub["status"] == "published", f"Expected published, got {bp_pub['status']}"
    print(f"✅ Published: status={bp_pub['status']}")

    # ── 3. Also create a "Safe Research Agent" for comparison ─────
    print("\n🛡️  Step 3: Create Safe Research Agent blueprint (for diff comparison)…")

    safe_payload = {
        "title": "🛡️ Safe Research Agent (Demo)",
        "description": (
            "A well-behaved research agent that stays within budget. "
            "Use for side-by-side comparison with the runaway agent."
        ),
        "blueprint_type": "solo",
        "tags": ["demo", "circuit-breaker", "safe", "safety"],
        "category": "safety-demos",
        "icon": "shield",
        "definition": {
            "blueprint_type": "solo",
            "nodes": [
                {
                    "id": "research_agent",
                    "type": "llm_call",
                    "title": "Focused Research Agent",
                    "description": "A research agent that stays focused and within budget.",
                    "config": {
                        "prompt": (
                            "You are a focused research agent. Investigate the "
                            "following topic concisely. Do NOT go down rabbit holes. "
                            "Stay on topic and be brief.\n\n"
                            "Topic: {{input.topic}}\n\n"
                            "Provide a concise summary with 3-5 key findings. "
                            "Stop after one response."
                        ),
                        "max_tokens": 500,
                    },
                    "assigned_model": "deepseek-chat",
                    "max_retries": 1,
                },
            ],
            "edges": [],
            "budget": {
                "max_cost_usd": 0.10,
                "max_wall_time_seconds": 30,
                "max_iterations": 3,
                "max_depth": 1,
            },
        },
    }

    r = requests.post(f"{API}/blueprints", json=safe_payload, headers=h, timeout=10)
    if r.status_code != 201:
        print(f"❌ Create safe blueprint failed: {r.status_code} — {r.text[:500]}")
        return 1
    safe_bp = r.json()["data"]
    safe_bp_id = safe_bp["id"]

    # Publish it
    r = requests.post(f"{API}/blueprints/{safe_bp_id}/publish", headers=h, timeout=10)
    if r.status_code != 200:
        print(f"❌ Publish safe blueprint failed: {r.status_code}")
        return 1
    print(f"✅ Safe Research Agent published: id={safe_bp_id}")

    # ── Summary ───────────────────────────────────────────────────
    print(
        f"""
{"═" * 60}
  🔥  RUNAWAY AGENT DEMO BLUEPRINTS CREATED
{"═" * 60}

  Runaway Agent:
    Blueprint ID : {bp_id}
    Title        : {bp_pub["title"]}
    Budget       : $0.50 (will trigger circuit breaker)
    Status       : {bp_pub["status"]}

  Safe Agent (for comparison):
    Blueprint ID : {safe_bp_id}
    Title        : 🛡️ Safe Research Agent (Demo)
    Budget       : $0.10
    Status       : published

{"─" * 60}
  NEXT STEPS:
{"─" * 60}
  1. Start a run:
     curl -X POST {API}/blueprints/{bp_id}/run \\
       -H "Authorization: Bearer <token>" \\
       -H "Content-Type: application/json" \\
       -d '{{"input_data": {{"topic": "the future of autonomous AI agents"}}}}'

  2. Watch the events stream:
     GET {API}/runs/<run_id>/events

  3. View the timeline (after building frontend):
     https://flowmanner.com/runs/<run_id>

  4. Compare with safe agent:
     GET {API}/runs/<runaway_run_id>/diff/<safe_run_id>
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
