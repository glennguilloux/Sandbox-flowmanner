# Sanity Matrix

## Purpose

`docs/test-automation/sanity-matrix.md` records the manual path-to-marker mapping for sanity-test selection per test automation strategy doc §4.3. It is the fallback until automated CI selection is implemented.

## Path-to-marker mapping

| Path pattern | Sanity marker | Owner |
|---|---|---|
| `backend/app/api/v1/auth*` | `sanity_auth` | `backend/auth` |
| `backend/app/services/chat*` | `sanity_chat` | `backend/chat` |
| `backend/app/services/mission*` | `sanity_missions` | `backend/missions` |
| `backend/app/api/v1/byok*` | `sanity_byok` | `backend/byok` |
| `backend/app/websocket/` | `sanity_websocket` | `backend/websocket` |
| `frontend/src/app/dashboard/**` | `sanity_frontend` | `frontend` |

> **Source of truth:** `scripts/select-sanity.py` (`PATH_MARKERS` and
> `FRONTEND_PLAYWRIGHT` dicts) is the runtime authority. This table is the
> human-readable form of the same mapping. If the two diverge, the **script
> wins** — please update this table in the same PR. See §4.3 for the
> original placeholder note.
