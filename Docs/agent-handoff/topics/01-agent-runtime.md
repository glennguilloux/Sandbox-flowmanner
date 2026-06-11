# 01 — Agent Runtime, Domain Agents, Tools, and Capabilities

**Status:** Draft  
**Last grounded:** 2026-06-11  
**Purpose:** Orient future agents before changing agent runtime, domain agents, tools, capabilities, or registry behavior.

## 1. Why this matters

Agents are first-class FlowManner entities with identity, personality, capabilities, templates, tools, and domain-specific implementations. Serious backend changes should not assume all agent code paths are wired the same way.

## 2. Files to read first

| Layer | Path | Notes |
|---|---|---|
| Agent service | `backend/app/services/agent_service.py` | Main persisted agent-template/catalog path to verify. |
| Registry service | `backend/app/services/agent_registry_service.py` | Capability matching registry; verify whether it is runtime executor or matcher only. |
| Capability engine | `backend/app/services/capability_engine.py` | Capability composition/enforcement. |
| Domain base | `backend/app/services/domain_agents/base_domain_agent.py` | Base class for domain agents. |
| Domain agents | `backend/app/services/domain_agents/*/agent.py` | Lightweight domain-specific wrappers. |
| Tool registry | `backend/app/services/unified_tools/tool_registry.py` | Tool registration and resolution. |
| Agent models | `backend/app/models/agent.py`, `backend/app/models/capability_models.py`, `backend/app/models/tool_catalog_models.py`, `backend/app/models/tool_models.py` | Persistent agent/tool/capability schema. |
| Tool implementations | `backend/app/tools/` | Agent/browser/web/search/code tools. |
| Agent definitions | `backend/agent_definitions/` | Markdown/Python agent definitions and built-in domain catalog. |

## 3. Current known risks

- Domain agents may be standalone wrappers rather than DB-registered runtime executors.
- Agent registry/capability registry may be a matcher/projection, not the mission execution path.
- Tools can live in multiple registries/adapters; do not assume one registry controls all execution.
- Agent definitions in `backend/agent_definitions/` may be used for import/bootstrap, marketplace display, or both.

## 4. Deep-dive checklist

- [ ] Count agent definitions by domain and source type.
- [ ] Verify which agent definitions are imported into DB tables.
- [ ] Trace one agent from definition → model → API → execution path.
- [ ] Trace one tool from registry → agent capability → execution result.
- [ ] Check whether domain agents are invoked by missions, substrate, or only standalone.
- [ ] Identify tests covering agent definitions, registry hydration, capability matching, and tool execution.

## 5. API contracts to verify

| Method | Route | Notes |
|---|---|---|
| `GET` | `/api/agents/*` | Verify v1 legacy agent routes. |
| `GET` | `/api/v2/agents/*` | Verify v2 agent routes and envelope. |
| `POST` | agent execute/delegate routes if present | Verify runtime path before changing. |

## 6. Tests to inspect

| Test area | File | Status |
|---|---|---|
| Agent service | `backend/tests/` | Unknown |
| Capability engine | `backend/tests/` | Unknown |
| Tool registry | `backend/tests/` | Unknown |
| Domain agents | `backend/tests/` | Unknown |

## 7. Next safe action

- [ ] Run a source-grounding pass on the files above and update this dossier with exact line ranges.
- [ ] Trace one end-to-end agent execution path before modifying any registry or domain agent code.
