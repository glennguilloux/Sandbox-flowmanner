# Sandbox Test Cases

This catalog stores sandbox-domain behavior contracts per test automation strategy doc §6.

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

### TC-SAND-001 — Sandbox preview accepts UUID-format refresh token cookie

- **Priority:** P0
- **Preconditions:** Sandbox preview endpoint reachable; refresh token row exists; cookie value is the token UUID, not a JWT.
- **Steps:**
  1. Create a sandbox preview request with a UUID-format refresh token cookie.
  2. Submit the request to the sandbox preview flow.
  3. Verify the auth chain resolves the refresh token and proceeds.
- **Expected:** Sandbox preview succeeds instead of returning 401.
- **Owner:** Backend / sandbox
- **Last run:** Not run yet
- **Linked bugs:** 4d8e04d fixed UUID-vs-JWT handling by adding `_is_jwt()` and DB lookup support.
