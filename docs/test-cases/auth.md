# Auth Test Cases

This catalog stores auth-domain behavior contracts per test automation strategy doc §6.

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

### TC-AUTH-001 — Signup → login → refresh-token flow works

- **Priority:** P0
- **Preconditions:** Fresh test user; auth API reachable.
- **Steps:**
  1. Create a new user through signup.
  2. Log in with the new user.
  3. Use the returned refresh token to obtain a fresh access token.
  4. Call `/me` with the fresh access token.
- **Expected:** Signup and login succeed; refresh-token exchange succeeds; `/me` returns 200 for the authenticated user.
- **Owner:** Backend / auth
- **Last run:** Not run yet
- **Linked bugs:** Auth happy path baseline
