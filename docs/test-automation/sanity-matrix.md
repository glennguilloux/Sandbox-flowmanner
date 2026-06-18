# Sanity Matrix

## Purpose

`docs/test-automation/sanity-matrix.md` is the human-readable form of the
path-to-marker mapping for sanity-test selection per test automation strategy
doc §4.3. The runtime selection lives in `scripts/select-sanity.py`.

## Path-to-marker mapping

The table below mirrors the `PATH_MARKERS` and `FRONTEND_PLAYWRIGHT` dicts in
`scripts/select-sanity.py` exactly. Matching is **prefix-based**: a path
matches if it equals the prefix or starts with `prefix + "/"`. There are no
glob wildcards.

| Path prefix | Marker | Owner |
|---|---|---|
| `backend/app/api/v1/auth` | `sanity_auth` | `backend/auth` |
| `backend/app/services/chat` | `sanity_chat` | `backend/chat` |
| `backend/app/services/mission` | `sanity_missions` | `backend/missions` |
| `backend/app/api/v1/byok` | `sanity_byok` | `backend/byok` |
| `backend/app/websocket` | `sanity_websocket` | `backend/websocket` |
| `frontend/src/app/dashboard` | `@sanity_dashboard` (Playwright tag) | `frontend` |

> **Source of truth:** `scripts/select-sanity.py` (`PATH_MARKERS` and
> `FRONTEND_PLAYWRIGHT` dicts) is the runtime authority. This table is the
> human-readable form of the same mapping. If the two diverge, the **script
> wins** — please update this table in the same PR. See §4.3 for the
> original placeholder note.

> **Note on `@sanity_dashboard`:** the `@` prefix and "(Playwright tag)"
> suffix flag that this entry is consumed by Playwright (via `--grep`), not
> by `pytest -m`. The script writes the Playwright invocation to stderr and
> the pytest marker set to stdout. See `scripts/select-sanity.py` for the
> dispatch logic.
