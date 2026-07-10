# Topic Dossier Template

**Status:** Draft
**Area:** `<backend/domain/infrastructure area>`
**Last grounded:** `<date>`
**Owner:** `<next agent or team>`

## 1. Purpose

One paragraph: what this dossier helps another agent understand before changing code.

## 2. Current Status

| Question | Answer |
|---|---|
| Is this area production-used? | Unknown / Yes / No / Partial |
| Is the code complete? | Unknown / Complete / Partial / Stubbed |
| Are tests present? | Unknown / Yes / No / Partial |
| Is deployment involved? | Unknown / Yes / No |

## 3. Source Map

| Layer | File(s) | Line(s) | Notes |
|---|---|---:|---|
| API route / CQRS | `backend/app/...` |  |  |
| Service | `backend/app/services/...` |  |  |
| Model | `backend/app/models/...` |  |  |
| Schema | `backend/app/schemas/...` |  |  |
| Tests | `backend/tests/...` |  |  |

## 4. Runtime Path

Describe the request/execution path:

```text
User/UI/API call → route/CQRS → service → model/queue/cache → response/event
```

Include auth/scope expectations if known.

## 5. API Contract

| Method | Route | Response | Auth/scope | Notes |
|---|---|---|---|---|
| `GET` | `/api/...` |  |  |  |

## 6. Data Model and Migrations

| Concept | Table/model | Migration | Notes |
|---|---|---|---|
|  |  |  |  |

## 7. Existing Tests

| Test | Covers | Status |
|---|---|---|
| `backend/tests/...` |  | Pass / Fail / Unknown |

## 8. Known Weaknesses

-
-
-

## 9. Grounding Commands Run

Paste commands and output here. Do not summarize.

```bash
# example
git status --short && git branch --show-current && git rev-parse --short HEAD
```

## 10. Next Safe Action

- [ ]
- [ ]

## 11. Open Questions

-
