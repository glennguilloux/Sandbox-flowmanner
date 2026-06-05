# Mission API Mock-ups

Realistic JSON fixtures matching the v2 envelope contract for frontend development,
QA testing, and API documentation reference.

## Envelope Contract

Every response follows one of these shapes:

```json
// Success
{ "data": <payload>, "meta": { "request_id": "...", "timestamp": "..." }, "error": null }

// Paginated
{ "data": { "items": [...], "total": N, "page": N, "per_page": N, "pages": N }, "meta": {...}, "error": null }

// Error
{ "data": null, "error": { "code": "...", "message": "...", "details": {...} }, "meta": {...} }
```

## Fixtures

| File | Endpoint | Description |
|------|----------|-------------|
| `mission_list_page1.json` | `GET /api/v2/missions?page=1&per_page=20` | Paginated list with mixed statuses (running, completed, failed, queued) |
| `mission_active.json` | `GET /api/v2/missions/active` | Active missions only (running + queued) |
| `mission_detail_running.json` | `GET /api/v2/missions/{id}` | Running mission with progress=62% and ETA |
| `mission_detail_completed.json` | `GET /api/v2/missions/{id}` | Completed mission with results and 100% progress |
| `mission_detail_failed.json` | `GET /api/v2/missions/{id}` | Failed mission with error_message and partial progress |
| `mission_tasks.json` | `GET /api/v2/missions/{id}/tasks` | 3 tasks: completed, running, pending — with dependencies |
| `mission_logs.json` | `GET /api/v2/missions/{id}/logs` | 5 log entries: info and warning levels |
| `mission_analytics.json` | `GET /api/v2/missions/analytics?days=30` | Global analytics: summary, over-time, token breakdown, failure analysis |

## Usage

- **Frontend**: Drop these into your mock API server or swap with real endpoints during development
- **QA**: Use as expected-response baselines for endpoint contract tests
- **Docs**: Reference alongside the OpenAPI spec for example response shapes

## Conventions

- All UUIDs are valid v4
- Timestamps are ISO 8601 with `Z` suffix
- Status values match `MissionStatus` enum
- Cost fields are USD floats
- Progress is 0–100 integer percentage
- ETA is nullable ISO 8601 datetime
