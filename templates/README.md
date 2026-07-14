# FlowManner Mission Templates
A curated library of **47 built-in mission templates** shipped via
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
| Type | Role |
|------|------|
| `start` | Entry point |
| `task` | LLM / tool execution step |
| `transform` | Data reshape (jq / text) between steps |
| `condition` | Branch on an expression — divergent path |
| `approval` | Human-in-the-loop gate |
| `log` | Record a step / audit entry |
| `loop` | Recurring cadence (e.g. while, daily/weekly) |
| `webhook` | External trigger / inbound event |
| `parallel` | Fan-out to concurrent branches → NodeType.FAN_OUT |
| `rag_query` | Retrieval-augmented lookup against a collection |
| `end` | Terminal node |

> `parallel` maps to `NodeType.FAN_OUT` in the adapter. Under the graph/dag
> strategies the fanned-out branches run **concurrently** and the downstream
> node joins on in-degree — no explicit `FAN_IN` node is required.

## Categories
The library spans 6 categories: `Research & Analysis` (5), `Software Engineering` (6), `approval` (6), `automation` (13), `data_pipeline` (9), `integration` (8).

---

## Catalog
### Research & Analysis (5)
| Template | Icon | Priority | Nodes | Node types |
|----------|------|----------|-------|------------|
| Research Report | BookOpen | high | 7 | approval, end, start, task |
| Stale Documentation Detector | BookCopy | low | 9 | approval, condition, end, log, loop, start, task, transform |
| Churn Risk Auto-Intervention | UserMinus | high | 9 | condition, end, log, rag_query, start, task, transform, webhook |
| Feature Request De-duplicator | Layers | medium | 9 | condition, end, log, rag_query, start, task, webhook |
| Market Research Synthesis | Sparkles | medium | 11 | end, parallel, rag_query, start, task, transform, webhook |

### Software Engineering (6)
| Template | Icon | Priority | Nodes | Node types |
|----------|------|----------|-------|------------|
| Code Review Agent | GitPullRequest | high | 6 | approval, end, start, task |
| CI/CD Deploy Gate | Rocket | high | 10 | approval, condition, end, log, start, task, webhook |
| P0 Bug Triage Router | Bug | high | 8 | condition, end, log, start, task, webhook |
| Dependency Vulnerability Patch Pipeline | ShieldCheck | high | 8 | approval, condition, end, log, loop, start, task |
| Code Review & Auto-Remediation | Bug | medium | 10 | approval, condition, end, log, rag_query, start, task, transform, webhook |
| Vulnerability Patch Orchestration | ShieldCheck | high | 13 | approval, condition, end, parallel, rag_query, start, task, transform, webhook |

### approval (6)
| Template | Icon | Priority | Nodes | Node types |
|----------|------|----------|-------|------------|
| Content Review & Approval Pipeline | FileText | medium | 7 | approval, end, start, task |
| Invoice Processing & Approval | Receipt | high | 9 | approval, condition, end, log, start, task, webhook |
| Non-Standard Contract Flagging | FileSignature | high | 8 | approval, condition, end, log, start, task, webhook |
| GDPR Data Erasure Processor | Eraser | high | 11 | approval, condition, end, log, parallel, start, task, webhook |
| Financial Wire Transfer Approval | Scale | high | 10 | approval, condition, end, log, rag_query, start, task, transform, webhook |
| Contract Compliance Review | Receipt | high | 11 | approval, condition, end, rag_query, start, task, transform, webhook |

### automation (13)
| Template | Icon | Priority | Nodes | Node types |
|----------|------|----------|-------|------------|
| API Health Monitor & Alert | Activity | high | 7 | condition, end, log, loop, start, task |
| Customer Support Ticket Triage | Headphones | high | 9 | condition, end, log, start, task, webhook |
| Social Post Generator & Scheduler | Megaphone | medium | 7 | approval, end, start, task, transform |
| Weekly Competitor Pulse | Radar | medium | 7 | approval, end, loop, start, task, transform |
| Incident Response Runbook | Siren | high | 9 | approval, condition, end, start, task, webhook |
| Meeting Notes → Action Items | CalendarCheck | medium | 8 | approval, end, start, task, webhook |
| Customer Feedback Tagger | MessageSquareHeart | medium | 8 | condition, end, log, start, task, webhook |
| Anomalous Login Responder | ShieldAlert | high | 8 | approval, condition, end, log, start, task, webhook |
| Cloud Cost Spike Investigator | DollarSign | high | 10 | approval, condition, end, log, start, task, transform, webhook |
| Stale PR Auto-Nagger | MessageCircle | low | 8 | condition, end, log, loop, start, task, transform |
| Security Incident Response | ShieldCheck | high | 12 | condition, end, log, parallel, rag_query, start, task, transform, webhook |
| SaaS Provisioning & Access Control | KeyRound | medium | 11 | condition, end, parallel, start, task, transform, webhook |
| Critical Infrastructure Breach Response | Network | high | 17 | approval, condition, end, log, loop, parallel, rag_query, start, task, transform, webhook |

### data_pipeline (9)
| Template | Icon | Priority | Nodes | Node types |
|----------|------|----------|-------|------------|
| Data Pipeline — Extract, Transform, Load | Database | medium | 5 | end, start, task, transform |
| Multi-Step Parallel Processing | GitBranch | medium | 8 | end, parallel, start, task |
| Scheduled DB Backup & Integrity Check | Database | medium | 8 | condition, end, log, loop, start, task |
| Data Quality Monitor | Gauge | medium | 7 | condition, end, log, loop, start, task |
| Top Performer Content Booster | Megaphone | medium | 10 | approval, condition, end, log, loop, start, task, transform |
| API Ingestion & Deduplication | Database | medium | 8 | condition, end, log, loop, start, task, transform |
| A/B Test Auto-Evaluator | GitBranch | medium | 7 | condition, end, log, loop, start, task |
| Customer Onboarding KYC | Users | high | 12 | approval, condition, end, parallel, start, task, transform, webhook |
| AI Model Drift Retraining | Gauge | medium | 11 | approval, condition, end, log, loop, rag_query, start, task |

### integration (8)
| Template | Icon | Priority | Nodes | Node types |
|----------|------|----------|-------|------------|
| Webhook API Integration | Link | high | 8 | condition, end, start, task, webhook |
| Inbound Lead Enrichment | UserPlus | medium | 8 | condition, end, log, start, task, webhook |
| New Hire Onboarding Orchestrator | UserCheck | high | 11 | approval, condition, end, log, parallel, start, task, webhook |
| Tier-1 Knowledge Base Auto-Reply | LifeBuoy | medium | 9 | condition, end, log, rag_query, start, task, transform, webhook |
| Renewal Risk Synthesizer | CalendarClock | high | 9 | condition, end, log, loop, rag_query, start, task, transform |
| Multi-Channel Content Syndicator | Share2 | medium | 9 | end, log, parallel, start, task, transform, webhook |
| Multi-Source Data Sync | Share2 | medium | 11 | condition, end, log, loop, parallel, start, task, transform |
| Daily Compliance Control Check | Clock | medium | 11 | condition, end, log, loop, parallel, start, task, transform |

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
