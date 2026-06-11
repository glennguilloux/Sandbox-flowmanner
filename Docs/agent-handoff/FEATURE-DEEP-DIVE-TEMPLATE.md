# Feature Deep-Dive Template

**Status:** Draft  
**Feature:** `<feature name>`  
**Last grounded:** `<date>`  
**Owner:** `<next agent or team>`

## 1. User Story

What the user can do or see after the feature works.

## 2. Current Status

| Layer | Status | Evidence |
|---|---|---|
| Frontend route | Unknown / Working / Broken / Missing |  |
| Backend API | Unknown / Working / Broken / Missing |  |
| Data model | Unknown / Exists / Missing |  |
| Tests | Unknown / Present / Missing |  |
| Docs | Unknown / Present / Missing |  |

## 3. Frontend Map

| File | Purpose | Notes |
|---|---|---|
| `/home/glenn/FlowmannerV2-frontend/src/...` |  |  |

## 4. Backend Map

| File | Purpose | Notes |
|---|---|---|
| `backend/app/api/...` |  |  |
| `backend/app/services/...` |  |  |
| `backend/app/models/...` |  |  |

## 5. API Calls

| Client call | Backend route | Method | Payload | Response |
|---|---|---|---|---|
|  |  |  |  |  |

## 6. State and Data Flow

```text
User action → frontend state → API call → backend mutation → DB/queue → response/stream → UI update
```

## 7. Edge Cases

- Empty state
- Permission/scope failure
- Network/API failure
- Partial success
- Race conditions
- Auth/session expiry

## 8. Tests to Add or Run

- [ ] Backend unit/integration test:
- [ ] Frontend unit/component test:
- [ ] E2E smoke test:

## 9. Verification Commands

Paste actual output before implementation and after implementation.

```bash
# example
cd backend && python -m pytest tests/<test_file>.py -v
```

## 10. Next Safe Change

- [ ] 
- [ ] 
