# Missions Test Cases

This catalog stores mission-domain behavior contracts per test automation strategy doc §6.

## Case record format

| Field | Value |
|---|---|
| ID | |
| Title | |
| Preconditions | |
| Steps | |
| Expected | |
| Priority | |
| Owner | |
| Last run | |
| Linked bugs | |

## P0 cases

### TC-MISS-001 — A mission with model_preference runs to completion (≥1 token)

- **Priority:** P0
- **Preconditions:** Authed user; mission service reachable; model_preference points to an available model.
- **Steps:**
  1. Create a mission with `model_preference`.
  2. Run the mission executor.
  3. Wait for the mission to reach a terminal state.
- **Expected:** Mission completes successfully; `output_data` is non-empty; `tokens_used` is at least 1.
- **Owner:** Backend / missions
- **Last run:** Not run yet
- **Linked bugs:** Silent mocker / empty output regression
