# FlowManner Mission Templates

A curated library of **35 built-in mission templates** shipped via
`backend/seed_templates.py`. Each template is a ready-to-run workflow DAG you
can instantiate from the canvas — they are the starting point for a new
mission, not the finished product, so treat them as scaffolds to customize.

## How templates become workflows

- `seed_templates.py` registers each template as a `MissionTemplate`
  (`is_builtin=True`). Seeding is **idempotent**: if built-in templates
  already exist it skips, so a re-run won't duplicate them.
- When a mission is created from a template, the adapter
  (`backend/app/services/substrate/adapters.py`) converts the template's
  `default_plan` nodes/edges into a substrate `Workflow` and the chosen
  strategy executes it.

## Node types used

Templates are authored exclusively with these canvas node types:

| Type | Role |
|------|------|
| `start` | Entry point |
| `task` | LLM / tool execution step |
| `transform` | Data reshape (`jq` / `text`) between steps |
| `condition` | Branch on an expression — divergent path |
| `approval` | Human-in-the-loop gate |
| `log` | Record a step / audit entry |
| `loop` | Recurring cadence (e.g. `while`, daily/weekly) |
| `webhook` | External trigger / inbound event |
| `parallel` | Fan-out to concurrent branches → `NodeType.FAN_OUT` |
| `rag_query` | Retrieval-augmented lookup against a collection |
| `end` | Terminal node |

> `parallel` maps to `NodeType.FAN_OUT` in the adapter. Under the graph/dag
> strategies the fanned-out branches run **concurrently** and the downstream
> node joins on in-degree — no explicit `FAN_IN` node is required.

## Categories

The library spans 6 categories: `automation` (10), `data_pipeline` (7),
`integration` (6), `Research & Analysis` (4), `Software Engineering` (4),
`approval` (4).

---

## Catalog

### automation (10)

| Template | Icon | Priority | Nodes | Node types |
|----------|------|----------|-------|------------|
| API Health Monitor & Alert | Activity | high | 7 | loop, task, condition, log, start, end |
| Customer Support Ticket Triage | Headphones | high | 9 | webhook, task, condition, log, start, end |
| Social Post Generator & Scheduler | Megaphone | medium | 7 | task, transform, approval, start, end |
| Weekly Competitor Pulse | Radar | medium | 7 | loop, task, transform, approval, start, end |
| Incident Response Runbook | Siren | high | 9 | webhook, task, condition, approval, start, end |
| Meeting Notes → Action Items | CalendarCheck | medium | 8 | webhook, task, approval, start, end |
| Customer Feedback Tagger | MessageSquareHeart | medium | 8 | webhook, task, condition, log, start, end |
| Anomalous Login Responder | ShieldAlert | high | 8 | webhook, task, condition, approval, log, start, end |
| Cloud Cost Spike Investigator | DollarSign | high | 10 | webhook, task, transform, condition, approval, log, start, end |
| Stale PR Auto-Nagger | MessageCircle | low | 8 | loop, task, transform, condition, log, start, end |

### data_pipeline (7)

| Template | Icon | Priority | Nodes | Node types |
|----------|------|----------|-------|------------|
| Data Pipeline — Extract, Transform, Load | Database | medium | 5 | task, transform, start, end |
| Multi-Step Parallel Processing | GitBranch | medium | 8 | parallel, task, start, end |
| Scheduled DB Backup & Integrity Check | Database | medium | 8 | loop, task, condition, log, start, end |
| Data Quality Monitor | Gauge | medium | 7 | loop, task, condition, log, start, end |
| Top Performer Content Booster | Megaphone | medium | 10 | loop, task, transform, condition, approval, log, start, end |
| API Ingestion & Deduplication | Database | medium | 8 | loop, task, transform, condition, log, start, end |
| A/B Test Auto-Evaluator | GitBranch | medium | 7 | loop, task, condition, log, start, end |

### integration (6)

| Template | Icon | Priority | Nodes | Node types |
|----------|------|----------|-------|------------|
| Webhook API Integration | Link | high | 8 | webhook, task, condition, start, end |
| Inbound Lead Enrichment | UserPlus | medium | 8 | webhook, task, condition, log, start, end |
| New Hire Onboarding Orchestrator | UserCheck | high | 11 | webhook, task, parallel, condition, approval, log, start, end |
| Tier-1 Knowledge Base Auto-Reply | LifeBuoy | medium | 9 | webhook, task, transform, rag_query, condition, log, start, end |
| Renewal Risk Synthesizer | CalendarClock | high | 9 | loop, task, rag_query, transform, condition, log, start, end |
| Multi-Channel Content Syndicator | Share2 | medium | 9 | webhook, transform, parallel, task, log, start, end |

### Research & Analysis (4)

| Template | Icon | Priority | Nodes | Node types |
|----------|------|----------|-------|------------|
| Research Report | BookOpen | high | 7 | task, approval, start, end |
| Stale Documentation Detector | BookCopy | low | 9 | loop, task, transform, condition, approval, log, start, end |
| Churn Risk Auto-Intervention | UserMinus | high | 9 | webhook, task, rag_query, transform, condition, log, start, end |
| Feature Request De-duplicator | Layers | medium | 9 | webhook, task, rag_query, condition, log, start, end |

### Software Engineering (4)

| Template | Icon | Priority | Nodes | Node types |
|----------|------|----------|-------|------------|
| Code Review Agent | GitPullRequest | high | 6 | task, approval, start, end |
| CI/CD Deploy Gate | Rocket | high | 10 | webhook, task, condition, approval, log, start, end |
| P0 Bug Triage Router | Bug | high | 8 | webhook, task, condition, log, start, end |
| Dependency Vulnerability Patch Pipeline | ShieldCheck | high | 8 | loop, task, condition, approval, log, start, end |

### approval (4)

| Template | Icon | Priority | Nodes | Node types |
|----------|------|----------|-------|------------|
| Content Review & Approval Pipeline | FileText | medium | 7 | task, approval, start, end |
| Invoice Processing & Approval | Receipt | high | 9 | webhook, task, condition, approval, log, start, end |
| Non-Standard Contract Flagging | FileSignature | high | 8 | webhook, task, condition, approval, log, start, end |
| GDPR Data Erasure Processor | Eraser | high | 11 | webhook, task, condition, parallel, approval, log, start, end |

---

## Adding a template

Append a `make_template(...)` call to `TEMPLATES` in `backend/seed_templates.py`.
Each node needs a unique `id`, a `type`, a `position` (for the canvas), a
`data` dict with `label` + `nodeType`, and `edges_out` (a list of
`{"target_id": ...}` with an optional `label`). Keep node types to the set
above and reuse an existing `category` so the gallery groups them correctly.

Validate locally before committing:

```bash
python3 -c "import ast; ast.parse(open('seed_templates.py').read())"
```

The seeder is idempotent, so to load changes into an existing database you
must clear built-ins first (or seed against a fresh DB).
