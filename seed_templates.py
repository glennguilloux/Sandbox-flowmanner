"""
Seed mission templates into the database (async).
Run: docker compose exec -e PYTHONPATH=/app backend python3 /tmp/seed_templates.py
"""
import asyncio
import uuid

from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.models.mission_advanced_models import MissionTemplate


def make_id():
    return uuid.uuid4().hex[:8]


def make_template(name, description, category, icon, priority, flow_steps):
    nodes = []
    edges = []
    for step in flow_steps:
        nodes.append({
            "id": step["id"],
            "type": step["type"],
            "position": step["position"],
            "data": step["data"],
        })
        for eo in step.get("edges_out", []):
            edges.append({
                "id": f"e-{make_id()}",
                "source": step["id"],
                "target": eo["target_id"],
                "type": "smoothstep",
                **({"label": eo["label"]} if eo.get("label") else {}),
            })
    return {
        "name": name,
        "description": description,
        "category": category,
        "icon": icon,
        "is_builtin": True,
        "is_public": True,
        "priority": priority,
        "default_plan": {"nodes": nodes, "edges": edges},
    }


# ── Template definitions ──

TEMPLATES = [
    make_template(
        name="Data Pipeline — Extract, Transform, Load",
        description="Extract data from a source, transform/clean it, then load into a destination. A classic ETL pattern.",
        category="data_pipeline", icon="Database", priority="medium",
        flow_steps=[
            dict(id="start-1", type="start", position={"x": 50, "y": 250}, data={"label": "Start", "nodeType": "start"}, edges_out=[{"target_id": "task-extract-1"}]),
            dict(id="task-extract-1", type="task", position={"x": 250, "y": 250}, data={"label": "Extract Data", "nodeType": "task", "description": "Pull data from source API, database, or file", "agent": "", "timeout": 60, "maxRetries": 2}, edges_out=[{"target_id": "transform-1"}]),
            dict(id="transform-1", type="transform", position={"x": 450, "y": 250}, data={"label": "Clean & Transform", "nodeType": "transform", "description": "Normalize fields, remove duplicates, format for target", "transformType": "jq", "transformExpression": '.data | map(select(.status != "archived"))'}, edges_out=[{"target_id": "task-load-1"}]),
            dict(id="task-load-1", type="task", position={"x": 650, "y": 250}, data={"label": "Load to Destination", "nodeType": "task", "description": "Write transformed data to the target system", "agent": "", "timeout": 120, "maxRetries": 1}, edges_out=[{"target_id": "end-1"}]),
            dict(id="end-1", type="end", position={"x": 850, "y": 250}, data={"label": "End", "nodeType": "end"}, edges_out=[]),
        ],
    ),
    make_template(
        name="Content Review & Approval Pipeline",
        description="Research a topic, generate content draft, route through approval, and publish.",
        category="approval", icon="FileText", priority="medium",
        flow_steps=[
            dict(id="start-2", type="start", position={"x": 50, "y": 250}, data={"label": "Start", "nodeType": "start"}, edges_out=[{"target_id": "task-research-1"}, {"target_id": "task-draft-1"}]),
            dict(id="task-research-1", type="task", position={"x": 250, "y": 200}, data={"label": "Research Topic", "nodeType": "task", "description": "Gather sources, outlines, key points", "agent": "", "timeout": 120, "maxRetries": 1}, edges_out=[{"target_id": "task-draft-1"}]),
            dict(id="task-draft-1", type="task", position={"x": 250, "y": 350}, data={"label": "Generate Draft", "nodeType": "task", "description": "Write full content draft based on research", "agent": "", "timeout": 180, "maxRetries": 1}, edges_out=[{"target_id": "task-polish-1"}]),
            dict(id="task-polish-1", type="task", position={"x": 450, "y": 275}, data={"label": "Polish & Format", "nodeType": "task", "description": "Apply tone, formatting, SEO metadata", "agent": "", "timeout": 60, "maxRetries": 0}, edges_out=[{"target_id": "approval-1"}]),
            dict(id="approval-1", type="approval", position={"x": 650, "y": 275}, data={"label": "Approval Gate", "nodeType": "approval", "description": "Human review before publication", "approverRole": "editor", "approvalTimeout": 48, "escalationPolicy": "escalate"}, edges_out=[{"target_id": "task-publish-1"}]),
            dict(id="task-publish-1", type="task", position={"x": 850, "y": 275}, data={"label": "Publish", "nodeType": "task", "description": "Push to production CMS / blog", "agent": "", "timeout": 30, "maxRetries": 2}, edges_out=[{"target_id": "end-2"}]),
            dict(id="end-2", type="end", position={"x": 1050, "y": 275}, data={"label": "End", "nodeType": "end"}, edges_out=[]),
        ],
    ),
    make_template(
        name="API Health Monitor & Alert",
        description="Periodically check API endpoints, evaluate health, and send alerts when services are down.",
        category="automation", icon="Activity", priority="high",
        flow_steps=[
            dict(id="start-3", type="start", position={"x": 50, "y": 250}, data={"label": "Start", "nodeType": "start"}, edges_out=[{"target_id": "loop-1"}]),
            dict(id="loop-1", type="loop", position={"x": 250, "y": 250}, data={"label": "Monitor Loop", "nodeType": "loop", "description": "Check every 5 minutes", "loopMode": "while", "loopExpression": "true", "maxIterations": 0}, edges_out=[{"target_id": "task-health-1"}, {"target_id": "cond-down-1"}]),
            dict(id="task-health-1", type="task", position={"x": 450, "y": 200}, data={"label": "Health Check", "nodeType": "task", "description": "Ping API /health endpoint, measure latency", "agent": "", "timeout": 15, "maxRetries": 1}, edges_out=[{"target_id": "cond-down-1"}]),
            dict(id="cond-down-1", type="condition", position={"x": 450, "y": 350}, data={"label": "Is Service Down?", "nodeType": "condition", "description": "Check response status and latency threshold", "expression": "result.status != 200 || result.latency > 5000"}, edges_out=[{"target_id": "task-alert-1", "label": "yes (down)"}, {"target_id": "log-1", "label": "no (ok)"}]),
            dict(id="task-alert-1", type="task", position={"x": 650, "y": 350}, data={"label": "Send Alert", "nodeType": "task", "description": "Notify via Slack/email with incident details", "agent": "", "timeout": 15, "maxRetries": 2}, edges_out=[{"target_id": "end-3"}]),
            dict(id="log-1", type="log", position={"x": 650, "y": 200}, data={"label": "Log OK Status", "nodeType": "log", "description": "Record successful health check", "level": "info", "message": "Health check passed"}, edges_out=[{"target_id": "end-3"}]),
            dict(id="end-3", type="end", position={"x": 850, "y": 275}, data={"label": "End", "nodeType": "end"}, edges_out=[]),
        ],
    ),
    make_template(
        name="Webhook API Integration",
        description="Receive incoming webhook data, process and validate it, then respond with the result.",
        category="integration", icon="Link", priority="high",
        flow_steps=[
            dict(id="start-4", type="start", position={"x": 50, "y": 250}, data={"label": "Start", "nodeType": "start"}, edges_out=[{"target_id": "webhook-1"}]),
            dict(id="webhook-1", type="webhook", position={"x": 250, "y": 250}, data={"label": "Receive Webhook", "nodeType": "webhook", "description": "Listen for incoming webhook payload", "url": "", "method": "POST", "authType": "bearer"}, edges_out=[{"target_id": "task-validate-1"}, {"target_id": "cond-valid-1"}]),
            dict(id="task-validate-1", type="task", position={"x": 450, "y": 200}, data={"label": "Validate Payload", "nodeType": "task", "description": "Check signature, schema, and required fields", "agent": "", "timeout": 10, "maxRetries": 0}, edges_out=[{"target_id": "cond-valid-1"}]),
            dict(id="cond-valid-1", type="condition", position={"x": 450, "y": 350}, data={"label": "Is Valid?", "nodeType": "condition", "description": "Check if payload passed validation", "expression": "validation.passed == true"}, edges_out=[{"target_id": "task-process-1", "label": "valid"}, {"target_id": "task-respond-1", "label": "invalid"}]),
            dict(id="task-process-1", type="task", position={"x": 650, "y": 200}, data={"label": "Process Data", "nodeType": "task", "description": "Transform payload, store, trigger downstream actions", "agent": "", "timeout": 30, "maxRetries": 1}, edges_out=[{"target_id": "end-ok-1"}]),
            dict(id="task-respond-1", type="task", position={"x": 650, "y": 350}, data={"label": "Send Error Response", "nodeType": "task", "description": "Return 400 with validation error details", "agent": "", "timeout": 5, "maxRetries": 0}, edges_out=[{"target_id": "end-err-1"}]),
            dict(id="end-ok-1", type="end", position={"x": 850, "y": 200}, data={"label": "End (Success)", "nodeType": "end"}, edges_out=[]),
            dict(id="end-err-1", type="end", position={"x": 850, "y": 350}, data={"label": "End (Error)", "nodeType": "end"}, edges_out=[]),
        ],
    ),
    make_template(
        name="Customer Support Ticket Triage",
        description="Receive support tickets, classify by intent and priority, then route to the appropriate team.",
        category="automation", icon="Headphones", priority="high",
        flow_steps=[
            dict(id="start-5", type="start", position={"x": 50, "y": 250}, data={"label": "Start", "nodeType": "start"}, edges_out=[{"target_id": "webhook-5"}]),
            dict(id="webhook-5", type="webhook", position={"x": 250, "y": 250}, data={"label": "Receive Ticket", "nodeType": "webhook", "description": "Incoming support ticket via webhook", "url": "", "method": "POST", "authType": "bearer"}, edges_out=[{"target_id": "task-classify-5"}]),
            dict(id="task-classify-5", type="task", position={"x": 450, "y": 250}, data={"label": "Classify Ticket", "nodeType": "task", "description": "AI classification: intent, sentiment, category", "agent": "", "timeout": 30, "maxRetries": 1}, edges_out=[{"target_id": "cond-priority-5"}]),
            dict(id="cond-priority-5", type="condition", position={"x": 650, "y": 150}, data={"label": "High Priority?", "nodeType": "condition", "description": "Route by priority level", "expression": "classification.priority == 'high'"}, edges_out=[{"target_id": "task-high-5", "label": "high"}, {"target_id": "task-low-5", "label": "standard"}]),
            dict(id="task-high-5", type="task", position={"x": 850, "y": 150}, data={"label": "Route — High Priority", "nodeType": "task", "description": "Escalate to senior team with SLA tracking", "agent": "", "timeout": 10, "maxRetries": 0}, edges_out=[{"target_id": "end-high-5"}]),
            dict(id="task-low-5", type="task", position={"x": 850, "y": 350}, data={"label": "Route — Standard", "nodeType": "task", "description": "Assign to general support queue", "agent": "", "timeout": 10, "maxRetries": 0}, edges_out=[{"target_id": "end-low-5"}, {"target_id": "log-routed-5"}]),
            dict(id="log-routed-5", type="log", position={"x": 650, "y": 400}, data={"label": "Log Routing", "nodeType": "log", "description": "Record routing decision for analytics", "level": "info", "message": "Ticket routed"}, edges_out=[{"target_id": "end-low-5"}]),
            dict(id="end-high-5", type="end", position={"x": 1050, "y": 150}, data={"label": "End (Escalated)", "nodeType": "end"}, edges_out=[]),
            dict(id="end-low-5", type="end", position={"x": 1050, "y": 350}, data={"label": "End (Routed)", "nodeType": "end"}, edges_out=[]),
        ],
    ),
    make_template(
        name="Multi-Step Parallel Processing",
        description="Kick off multiple parallel tasks simultaneously, then merge results and proceed.",
        category="data_pipeline", icon="GitBranch", priority="medium",
        flow_steps=[
            dict(id="start-6", type="start", position={"x": 50, "y": 250}, data={"label": "Start", "nodeType": "start"}, edges_out=[{"target_id": "task-prep-6"}]),
            dict(id="task-prep-6", type="task", position={"x": 250, "y": 250}, data={"label": "Prepare Input Data", "nodeType": "task", "description": "Load and split input data for parallel processing", "agent": "", "timeout": 30, "maxRetries": 1}, edges_out=[{"target_id": "parallel-6"}]),
            dict(id="parallel-6", type="parallel", position={"x": 450, "y": 250}, data={"label": "Parallel Fork", "nodeType": "parallel", "description": "Execute branches concurrently", "branches": 3, "joinMode": "all"}, edges_out=[{"target_id": "branch-a-6", "label": "branch A"}, {"target_id": "branch-b-6", "label": "branch B"}, {"target_id": "branch-c-6", "label": "branch C"}]),
            dict(id="branch-a-6", type="task", position={"x": 650, "y": 100}, data={"label": "Branch A — Analyze", "nodeType": "task", "description": "Run analysis on data subset A", "agent": "", "timeout": 60, "maxRetries": 1}, edges_out=[{"target_id": "task-merge-6"}]),
            dict(id="branch-b-6", type="task", position={"x": 650, "y": 250}, data={"label": "Branch B — Enrich", "nodeType": "task", "description": "Enrich data with external sources", "agent": "", "timeout": 60, "maxRetries": 1}, edges_out=[{"target_id": "task-merge-6"}]),
            dict(id="branch-c-6", type="task", position={"x": 650, "y": 400}, data={"label": "Branch C — Validate", "nodeType": "task", "description": "Run validation checks on data", "agent": "", "timeout": 30, "maxRetries": 2}, edges_out=[{"target_id": "task-merge-6"}]),
            dict(id="task-merge-6", type="task", position={"x": 850, "y": 250}, data={"label": "Merge Results", "nodeType": "task", "description": "Combine all branch outputs into final result", "agent": "", "timeout": 30, "maxRetries": 1}, edges_out=[{"target_id": "end-6"}]),
            dict(id="end-6", type="end", position={"x": 1050, "y": 250}, data={"label": "End", "nodeType": "end"}, edges_out=[]),
        ],
    ),
]


async def seed():
    async with AsyncSessionLocal() as db:
        # Check if already seeded
        count_q = select(func.count()).select_from(
            select(MissionTemplate).where(MissionTemplate.is_builtin.is_(True)).subquery()
        )
        existing = (await db.execute(count_q)).scalar() or 0
        if existing > 0:
            print(f"⚠️  {existing} built-in templates already exist — skipping seed")
            return

        for tpl in TEMPLATES:
            record = MissionTemplate(
                id=uuid.uuid4(),
                user_id=1,
                name=tpl["name"],
                description=tpl["description"],
                category=tpl["category"],
                icon=tpl["icon"],
                is_public=True,
                is_builtin=True,
                mission_type=None,
                priority=tpl["priority"],
                default_plan=tpl["default_plan"],
                default_tasks=None,
                default_constraints=None,
                tags=None,
                usage_count=0,
            )
            db.add(record)
            print(f"  ✓ {tpl['name']}")

        await db.commit()
        print(f"\n✅ Seeded {len(TEMPLATES)} built-in templates")


if __name__ == "__main__":
    asyncio.run(seed())
