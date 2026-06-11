# Topic Dossiers

Topic dossiers are the working memory for FlowManner backend and feature work. They are shorter than the full system spec and should be updated before serious implementation.

## Catalog

| Number | Topic | Dossier | Status |
|---:|---|---|---|
| 00 | System map | `00-system-map.md` | Ready |
| 01 | Agent runtime | `01-agent-runtime.md` | Draft |
| 02 | Execution substrate | `02-execution-substrate.md` | Draft |
| 03 | Auth and workspaces | `03-auth-workspaces.md` | Draft |
| 04 | Data model and migrations | `04-data-model-migrations.md` | Draft |
| 05 | Sandbox and code execution | `05-sandbox-code-execution.md` | Draft |
| 06 | Marketplace and plugins | `06-marketplace-plugins.md` | Draft |
| 07 | Observability and CI | `07-observability-ci.md` | Draft |
| 08 | Frontend dashboard | `08-frontend-dashboard.md` | Draft |
| 09 | LLM, RAG, memory, eval | `09-llm-rag-memory.md` | Draft |

## How to add a topic

1. Copy `topics/_TEMPLATE.md` to `topics/<number>-<area>.md`.
2. Fill the header with status, owner, and last grounded date.
3. Ground the dossier against current source files.
4. Add exact file paths and line ranges.
5. Add tests and verification commands.
6. Set status to `Grounded` when the next agent can safely start from it.
7. Set status to `Ready` only when the next safe action is explicit.
