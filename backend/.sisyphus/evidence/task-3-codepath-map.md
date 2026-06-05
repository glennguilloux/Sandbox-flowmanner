# Mission Endpoint Code-Path Map

## Router Mounting
- Router prefix: `/missions` (defined in `app/api/v1/mission.py:46`)
- Mounted under `/api` (confirmed in `app/api/v1/__init__.py:45`)
- All paths below are relative to `/api/missions`

## All Routes

| Route | Method | Handler | Lines | Service Call | 404 Source | 500 Source |
|---|---|---|---|---|---|---|
| `/` | GET | list_items | 65-72 | list_missions | — | DB query failure |
| `/` | POST | create_item | 75-89 | create_mission | — | DB insert failure |
| `/{mission_id}` | GET | get_item | 92-100 | get_mission → _require_owner | mission=None or wrong owner (53-55) | DB query failure |
| `/{mission_id}` | PATCH | patch_item | 103-127 | get_mission → _require_owner → update_mission | same + update returns None | DB failure |
| `/{mission_id}` | DELETE | delete_item | 130-139 | get_mission → _require_owner → delete_mission | same | DB failure |
| `/{mission_id}/tasks` | GET | list_tasks | 142-150 | get_mission → _require_owner → get_mission_tasks | same | **get_mission_tasks queries `updated_at` which doesn't exist in DB** |
| `/{mission_id}/tasks` | POST | create_task | 153-173 | get_mission → _require_owner → create_mission_task | same | **same column issue** |
| `/{mission_id}/tasks/{task_id}` | PATCH | update_task | 176-206 | get_mission → _require_owner → direct SQL | same | **same column issue** |
| `/{mission_id}/logs` | GET | list_logs | 209-217 | get_mission → _require_owner → get_mission_logs | same | DB failure |
| `/{mission_id}/logs` | POST | create_log | 220-229 | get_mission → _require_owner → create_mission_log | same | DB failure |
| `/{mission_id}/plan` | POST | plan_mission | 232-254 | get_mission → _require_owner → MissionExecutor → get_mission_tasks | same | **get_mission_tasks updated_at** |
| `/{mission_id}/execute` | POST | execute_mission | 257-281 | get_mission → _require_owner → MissionExecutor → get_mission_tasks | same | **get_mission_tasks updated_at** |
| `/{mission_id}/execute-async` | POST | execute_mission_async | 284-296 | get_mission → _require_owner → Celery | same | Celery failure |
| `/{mission_id}/status/` | GET | get_mission_status | 299-317 | get_mission → _require_owner → get_mission_tasks | same | **get_mission_tasks updated_at** |
| `/{mission_id}/improvements` | GET | list_improvements | 320-329 | get_mission → _require_owner → SelfImprovementEngine | same | Engine failure |
| `/{mission_id}/improvements` | POST | create_improvement | 332-348 | get_mission → _require_owner → SelfImprovementEngine | same | Engine failure |
| `/{mission_id}/improvements/{improvement_id}/apply` | POST | apply_improvement | 351-361 | get_mission → _require_owner → SelfImprovementEngine | same | Engine failure |
| `/{mission_id}/analytics` | GET | get_mission_analytics_endpoint | 364-382 | get_mission → _require_owner → analytics functions | same | Analytics failure |
| `/analytics` | GET | get_global_analytics | 385-390 | get_mission_analytics | — | Analytics failure |

## Missing Routes
- **`/{mission_id}/stream`** — NOT DEFINED anywhere in mission.py or related files. The frontend requests this endpoint but it doesn't exist → always 404.

## _require_owner Behavior (lines 53-55)
```python
def _require_owner(mission, user: User) -> None:
    if mission is None or mission.user_id != user.id:
        raise _not_found()
```
- Returns 404 for BOTH "mission not found" AND "mission owned by another user"
- This is an intentional security pattern (don't leak existence of other users' missions)

## Key Finding: Why List Works But Details Fail
- `list_missions()` only queries the `missions` table, which HAS `updated_at`
- Detail endpoints call `get_mission()` (queries `missions` table — works) then `_require_owner()` (in-memory check — works IF the mission belongs to user_id=60)
- **BUT** the status endpoint and any endpoint that calls `get_mission_tasks()` will hit the `mission_tasks` table which is MISSING `updated_at`
- The SQLAlchemy model `MissionTask` inherits `TimestampMixin` which defines `updated_at`
- SQLAlchemy generates SQL including `mission_tasks.updated_at` which fails with `UndefinedColumnError`
