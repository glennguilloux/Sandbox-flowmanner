#!/usr/bin/env python3
"""Load the 4 KG-analysis reports into the Hermes KG MCP.

Run AFTER the 4 deliverables exist at /opt/flowmanner/.kg-analysis/.
Creates:
  - 1 analysis_report entity per report (observations = key findings)
  - domain sub-entities for the NEW coverage areas (services, personas, frontend, infra, product)
  - relations linking them into the existing Flowmanner cluster
"""
import os, re, json, sys

OUT = "/opt/flowmanner/.kg-analysis"
REPORTS = {
    "backend-services-and-personas.md": {
        "entity": "kg_analysis_backend_services_personas",
        "title": "Flowmanner backend services layer + 216-persona platform model",
    },
    "frontend-architecture.md": {
        "entity": "kg_analysis_frontend_architecture",
        "title": "Flowmanner frontend (Next.js) architecture + route->API map",
    },
    "deployment-and-infra.md": {
        "entity": "kg_analysis_deployment_infra",
        "title": "Flowmanner deployment, docker-compose, Celery, observability, 3-host topology",
    },
    "product-positioning.md": {
        "entity": "kg_analysis_product_positioning",
        "title": "Flowmanner product positioning, persona-system-as-product, platform economy, monetization",
    },
}

def extract_findings(path):
    txt = open(path).read()
    m = re.search(r"##\s*\d*\.?\s*KEY FINDINGS(.*?)(?=\n##|\Z)", txt, re.DOTALL | re.IGNORECASE)
    obs = []
    if m:
        for line in m.group(1).splitlines():
            line = line.strip().lstrip("-*").strip()
            if line:
                obs.append(line)
    return obs

def main():
    entities = []
    relations = []

    # 1) Per-report analysis_report entities
    for fname, meta in REPORTS.items():
        fpath = os.path.join(OUT, fname)
        if not os.path.exists(fpath):
            print(f"MISSING: {fname} — abort", file=sys.stderr)
            sys.exit(2)
        findings = extract_findings(fpath)
        obs = [f"[report] {meta['title']}", f"source_file: .kg-analysis/{fname}"]
        obs += [f"key-finding: {f}" for f in findings]
        entities.append({"name": meta["entity"], "entityType": "analysis_report", "observations": obs})
        relations.append({"from": meta["entity"], "to": "Flowmanner", "relationType": "analyzes"})

    # 2) New domain sub-entities (the gaps not previously in KG)
    domain_entities = [
        {
            "name": "flowmanner_services_layer",
            "entityType": "architecture_layer",
            "observations": [
                "Business-logic layer lives in backend/app/services/ (one module per domain).",
                "God services: chat_service.py (2885 ln) and integration_bridge.py (2630 ln) are single points of change.",
                "Other oversized: personal_memory_service.py (1222), mission_planner.py (1010), mission_program_service.py (995), budget_enforcer.py (925).",
                "Auth is half-migrated: auth_service (legacy JWT) coexists with auth_v3_service (workspace/session); v3 routes use only auth_v3_service, v1/v2 import both.",
                "Redundant implementations: 3 web-search modules and 3 cost modules overlap in responsibility.",
                "Report: .kg-analysis/backend-services-and-personas.md (136 file:line anchors).",
            ],
        },
        {
            "name": "flowmanner_persona_platform",
            "entityType": "platform_feature",
            "observations": [
                "216 expert personas across 16 divisions under backend/app/agent_definitions/.",
                "Loaded by backend/app/services/agent_parser.py (load_all_agents/parse_agent_file).",
                "Persona injection seam is DB-backed: llm_executor._resolve_agent_system_prompt reads AgentTemplate by template_id then slug.",
                "The 'invisible personas' gap (31 not seeded) is end-to-end: non-injectable at execution, not just catalog-invisible.",
                "Seeding is idempotent/self-healing: seed_agent_templates upserts by slug at lifespan; fixing agent_parser.py:17 auto-seeds on next startup.",
                "Report: .kg-analysis/backend-services-and-personas.md.",
            ],
        },
        {
            "name": "flowmanner_frontend",
            "entityType": "architecture_layer",
            "observations": [
                "Next.js App Router frontend at /home/glenn/FlowmapperV2-frontend (symlink /home/glenn/f).",
                "Consumes backend via centralized API client; routes map to /api/v1|v2|v3 endpoints.",
                "Key surfaces: chat/agent UI, builder/blueprint editor, marketplace, dashboard, workspace/team management.",
                "Auth via NextAuth talking to /api/auth/* + backend JWT.",
                "Report: .kg-analysis/frontend-architecture.md (104 file:line anchors).",
            ],
        },
        {
            "name": "flowmanner_infra_topology",
            "entityType": "infra_topology",
            "observations": [
                "Three-host topology: VPS (frontend/nginx/SSL) <-> Homelab (backend/DBs/LLM) via WireGuard <-> Ops (deploy trigger).",
                "Services: backend, frontend, postgres, redis, rabbitmq, qdrant, celery-worker.",
                "Background processing: Celery + RabbitMQ broker (backend/app/tasks/celery_app.py).",
                "Observability: OpenTelemetry -> Jaeger, prometheus-client metrics, structlog.",
                "No volume mounts on backend container — code baked into image; deploy via deploy-backend.sh / deploy-frontend.sh.",
                "Report: .kg-analysis/deployment-and-infra.md (69 file:line anchors).",
            ],
        },
        {
            "name": "flowmanner_product_economy",
            "entityType": "platform_feature",
            "observations": [
                "Multi-agent workflow platform: users compose missions/blueprints/workflows orchestrating LLM agents.",
                "Platform economy: marketplace (v2), community, changelog, roadmap modules.",
                "Monetization: tiering + workspace billing (feature_v3_workspace_billing), rate_limit/tier_rate_limit, Stripe OAuth, cost attribution.",
                "Differentiation: 216-persona system, substrate, intent-execution governance, HITL, eval harness.",
                "Report: .kg-analysis/product-positioning.md (34 file:line anchors).",
            ],
        },
    ]
    for e in domain_entities:
        entities.append(e)
        relations.append({"from": e["name"], "to": "Flowmanner", "relationType": "part_of"})

    # 3) Cross-links: services layer serves the feature_analysis modules; personas feed the agents features
    relations += [
        {"from": "flowmanner_services_layer", "to": "kg_analysis_backend_services_personas", "relationType": "documented_in"},
        {"from": "flowmanner_persona_platform", "to": "kg_analysis_backend_services_personas", "relationType": "documented_in"},
        {"from": "flowmanner_frontend", "to": "kg_analysis_frontend_architecture", "relationType": "documented_in"},
        {"from": "flowmanner_infra_topology", "to": "kg_analysis_deployment_infra", "relationType": "documented_in"},
        {"from": "flowmanner_product_economy", "to": "kg_analysis_product_positioning", "relationType": "documented_in"},
        {"from": "flowmanner_persona_platform", "to": "feature_v1_agent_personalities", "relationType": "exposes"},
        {"from": "flowmanner_frontend", "to": "feature_v2_blueprints", "relationType": "consumes"},
        {"from": "flowmanner_infra_topology", "to": "flowmanner_homelab_infra", "relationType": "extends"},
    ]

    payload = {"entities": entities, "relations": relations}
    print(json.dumps(payload, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
