# Flowmanner — Pre-built Integrations Plan

## TL;DR

> **Quick Summary**: Build OAuth-based pre-built integrations for Slack, GitHub, Notion, Google Drive, and Linear with a connection wizard UI, service-specific action cards in the mission builder, and an adapter-based architecture.
>
> **Deliverables**:
> - OAuth infrastructure (initiate, callback, token management) with user-provided credentials
> - 5 service adapters (Slack, GitHub, Notion, Google Drive, Linear) with 19 total actions
> - Connection wizard UI for linking user accounts
> - Service-specific action cards in the mission builder
> - Integration management page
>
> **Estimated Effort**: Large (5 services × actions + full frontend)
> **Parallel Execution**: YES — 4 waves
> **Critical Path**: OAuth infra → Adapters → Frontend actions

---

## Context

### Original Request
Build pre-built OAuth-based integrations for popular services, building on the HTTP outbound foundation from the previous growth plan.

### Interview Summary
**Key Decisions**:
- Services: Slack, GitHub, Notion, Google Drive, Linear
- Actions: 19 total across all 5 services (4/4/3/4/4)
- OAuth model: User-provided credentials (users enter their own client_id/secret)
- Scope: Per-user (not per-workspace)
- UX depth: Full — Connection Wizard + Action Cards in mission builder
- Tests: YES — include automated tests

**Existing Infrastructure**:
- `integrations/oauth.py`: Provider configs + Fernet token encryption/decryption
- `models/integration_models.py`: HttpIntegrationConfig + HttpIntegrationLog
- `services/http_integration_executor.py`: Generic HTTP outbound executor
- Mission builder frontend at `missions/builder/page.tsx`

---

## Work Objectives

### Core Objective
Enable users to connect their Slack, GitHub, Notion, Google Drive, and Linear accounts and use service-specific actions in missions.

### Concrete Deliverables
- Backend: OAuth service layer + 5 service adapters + action registry
- Backend DB: OAuth app storage + connection storage tables
- Frontend: Connection wizard + integration manager + action cards
- API: OAuth endpoints + integration management + action execution

### Must Have
- Users can register OAuth apps (client_id, client_secret) for each service
- Users can OAuth-connect their accounts to Flowmanner
- Connected accounts persist tokens encrypted
- Each service adapter implements its defined actions
- Actions appear in the mission builder as selectable steps
- Slack: send_message, search_messages, list_channels, create_channel
- GitHub: create_issue, create_pr, search_repos, get_file_contents
- Notion: create_page, query_database, append_block
- Google Drive: list_files, create_doc, search_files, read_file
- Linear: create_issue, update_issue, search_issues, list_projects
- All actions authenticate using stored OAuth tokens
- Token refresh works for services that support it (Google, Slack)

### Must NOT Have (Guardrails)
- NO generic HTTP integration changes (that's already built)
- NO custom authentication flows — OAuth only for these services
- NO workspace-level sharing — per-user only
- NO changes to existing mission executor logic
- NO new npm dependencies unless absolutely necessary
- NO storing unencrypted secrets

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### Test Decision
- **Automated tests**: YES (tests-after)
- **Framework**: pytest (backend), vitest (frontend)

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Backend**: Bash (curl) for API + pytests for adapters
- **Frontend**: Playwright for UI interaction

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (OAuth Foundation — blocks all services):
├── Task 1: OAuth DB models + migration (UserOAuthApp, UserOAuthConnection)
├── Task 2: OAuth endpoints (initiate, callback, list connections, disconnect)
├── Task 3: OAuth frontend — Connection Wizard

Wave 2 (Service Adapters — MAX PARALLEL, 5 tasks):
├── Task 4: Slack adapter (4 actions: send_message, search, list_channels, create_channel)
├── Task 5: GitHub adapter (4 actions: create_issue, create_pr, search_repos, get_file)
├── Task 6: Notion adapter (3 actions: create_page, query_database, append_block)
├── Task 7: Google Drive adapter (4 actions: list_files, create_doc, search, read_file)
└── Task 8: Linear adapter (4 actions: create_issue, update_issue, search, list_projects)

Wave 3 (Frontend Actions — parallel):
├── Task 9: Action registry API + mission builder integration
├── Task 10: Action card components for all 5 services
└── Task 11: Integration management page + tests

Wave FINAL (Verification):
├── Task F1: Plan compliance audit [oracle]
├── Task F2: Code quality + security review [unspecified-high]
├── Task F3: Real manual QA — all 19 actions end-to-end [unspecified-high]
└── Task F4: Scope fidelity check [deep]
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| 1 | — | 2, 3, 4-8 |
| 2 | 1 | 4-8 |
| 3 | 1 | 9-11 |
| 4-8 | 2 | 9 |
| 9 | 4-8 | 10 |
| 10 | 9 | 11 |
| 11 | 3, 10 | F1-F4 |

### Wave 2 — Service Adapters (ALL PARALLEL — 5 tasks)

> Each adapter follows the same pattern:
> - Extends `BaseIntegrationAdapter` with `execute(action, params, connection)` method
> - Uses stored OAuth tokens from `UserOAuthConnection` for auth
> - Returns typed response (content + metadata + success/error)
> - Handles token refresh if 401 received
> - All actions using httpx, NOT the generic HTTP executor

- [ ] 4. Slack adapter — 4 actions

  **What to do**:
  - Create `backend/app/integrations/adapters/base.py` with abstract `BaseIntegrationAdapter` class
  - Create `backend/app/integrations/adapters/slack.py` with:
    - `send_message(channel, text, thread_ts?)` — POST chat.postMessage
    - `search_messages(query, limit?)` — GET search.messages
    - `list_channels(limit?, cursor?)` — GET conversations.list
    - `create_channel(name, is_private?)` — POST conversations.create
  - All use `xoxb-` bot token from OAuth connection
  - Handle Slack API error responses (not_authorized, channel_not_found, etc.)

  **Must NOT do**:
  - Do NOT use Slack Web API without error handling
  - Do NOT store messages or channel data (pass-through only)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 5, 6, 7, 8)
  - **Blocks**: Task 9
  - **Blocked By**: Task 2

  **References**:
  - `backend/app/services/http_integration_executor.py` — HTTP executor (pattern for making requests)
  - `https://api.slack.com/methods` — Slack Web API docs
  - `backend/app/integrations/oauth.py` — decrypt_token() for using stored tokens

  **Acceptance Criteria**:
  - [ ] All 4 actions execute successfully with valid token
  - [ ] Token refresh triggered on 401 response
  - [ ] Errors returned in structured format (not raw API errors)
  - [ ] Pytest tests for all 4 actions (mocked httpx)

  **QA Scenarios**:
  ```
  Scenario: send_message succeeds
    Tool: Bash (pytest)
    Preconditions: Mock httpx to return valid Slack response
    Steps:
      1. Create SlackAdapter with mock connection
      2. Call execute("send_message", {channel: "#general", text: "Hello"})
      3. Assert success=True, response contains ts (timestamp)
    Expected Result: Message sent successfully
    Evidence: .sisyphus/evidence/task-4-slack-send.txt

  Scenario: Slack API error handled
    Tool: Bash (pytest)
    Preconditions: Mock httpx to return Slack error
    Steps:
      1. Call execute("send_message", {channel: "#nonexistent", text: "Hi"})
      2. Assert success=False
      3. Assert error_message contains "channel_not_found"
    Expected Result: Error handled gracefully
    Evidence: .sisyphus/evidence/task-4-slack-error.txt
  ```

  **Commit**: YES (groups with Tasks 5-8)
  - Message: `feat(integrations): add base adapter + Slack adapter with 4 actions`
  - Files: `backend/app/integrations/adapters/__init__.py`, `backend/app/integrations/adapters/base.py`, `backend/app/integrations/adapters/slack.py`

---

- [ ] 5. GitHub adapter — 4 actions

  **What to do**:
  - Create `backend/app/integrations/adapters/github.py` with:
    - `create_issue(owner, repo, title, body?, labels?)` — POST /repos/{owner}/{repo}/issues
    - `create_pr(owner, repo, title, head, base, body?)` — POST /repos/{owner}/{repo}/pulls
    - `search_repos(query, sort?, limit?)` — GET /search/repositories
    - `get_file_contents(owner, repo, path, ref?)` — GET /repos/{owner}/{repo}/contents/{path}
  - Use GitHub API v3 (Accept: application/vnd.github.v3+json)
  - Auth via Bearer token (personal access token or OAuth token)

  **Must NOT do**:
  - Do NOT use unauthenticated requests (always use token)
  - Do NOT expose token in error messages

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 4, 6, 7, 8)
  - **Blocks**: Task 9
  - **Blocked By**: Task 2

  **References**:
  - `backend/app/integrations/adapters/base.py` — BaseIntegrationAdapter (from Task 4)
  - `https://docs.github.com/en/rest` — GitHub REST API docs
  - `backend/app/integrations/oauth.py` — token decryption

  **Acceptance Criteria**:
  - [ ] All 4 actions execute with valid GitHub token
  - [ ] create_pr handles merge conflicts in error response
  - [ ] search_repos returns paginated results
  - [ ] Pytest tests for all 4 actions (mocked httpx)

  **QA Scenarios**:
  ```
  Scenario: create_issue succeeds
    Tool: Bash (pytest)
    Preconditions: Mock httpx to return created issue response
    Steps:
      1. Create GitHubAdapter with mock connection
      2. Call execute("create_issue", {owner: "user", repo: "my-repo", title: "Bug found"})
      3. Assert success=True, response contains issue number and URL
    Expected Result: Issue created
    Evidence: .sisyphus/evidence/task-5-github-issue.txt

  Scenario: get_file_contents returns file
    Tool: Bash (pytest)
    Preconditions: Mock httpx with file content response
    Steps:
      1. Call execute("get_file_contents", {owner: "user", repo: "my-repo", path: "README.md"})
      2. Assert success=True, response contains content and encoding
    Expected Result: File contents returned
    Evidence: .sisyphus/evidence/task-5-github-file.txt
  ```

  **Commit**: YES (groups with Tasks 4, 6-8)
  - Message: `feat(integrations): add GitHub adapter with 4 actions`
  - Files: `backend/app/integrations/adapters/github.py`

---

- [ ] 6. Notion adapter — 3 actions

  **What to do**:
  - Create `backend/app/integrations/adapters/notion.py` with:
    - `create_page(parent_page_id, properties, children?)` — POST /v1/pages
    - `query_database(database_id, filter?, sorts?, limit?)` — POST /v1/databases/{id}/query
    - `append_block(block_id, children)` — PATCH /v1/blocks/{id}/children
  - Use Notion API v1
  - Auth via `Bearer` token (Notion integration token)
  - Handle Notion-specific error codes (validation_error, object_not_found)

  **Must NOT do**:
  - Do NOT send empty children arrays (Notion API rejects them)
  - Do NOT create pages without required properties

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 4, 5, 7, 8)
  - **Blocks**: Task 9
  - **Blocked By**: Task 2

  **References**:
  - `backend/app/integrations/adapters/base.py` — BaseIntegrationAdapter
  - `https://developers.notion.com/reference` — Notion API docs
  - `backend/app/integrations/oauth.py` — token decryption

  **Acceptance Criteria**:
  - [ ] All 3 actions execute with valid Notion token
  - [ ] query_database supports filter and sort parameters
  - [ ] append_block handles paginated children
  - [ ] Pytest tests for all 3 actions (mocked httpx)

  **QA Scenarios**:
  ```
  Scenario: create_page succeeds
    Tool: Bash (pytest)
    Preconditions: Mock httpx with page creation response
    Steps:
      1. Create NotionAdapter with mock connection
      2. Call execute("create_page", {parent_page_id: "abc", properties: {title: {title: [{text: {content: "New Page"}}]}}})
      3. Assert success=True, response contains page_id and URL
    Expected Result: Page created
    Evidence: .sisyphus/evidence/task-6-notion-page.txt
  ```

  **Commit**: YES (groups with Tasks 4-5, 7-8)
  - Message: `feat(integrations): add Notion adapter with 3 actions`
  - Files: `backend/app/integrations/adapters/notion.py`

---

- [ ] 7. Google Drive adapter — 4 actions

  **What to do**:
  - Create `backend/app/integrations/adapters/google_drive.py` with:
    - `list_files(query?, page_size?)` — GET /drive/v3/files
    - `create_doc(title, folder_id?, content?)` — POST /drive/v3/files (with Google Docs format)
    - `search_files(query, page_size?)` — GET /drive/v3/files with q parameter
    - `read_file(file_id)` — GET /drive/v3/files/{id} with alt=media
  - Use Google Drive API v3
  - Auth via OAuth 2.0 access token
  - Handle token refresh using refresh_token

  **Must NOT do**:
  - Do NOT download files larger than 10MB
  - Do NOT use service account auth (user OAuth only)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 4, 5, 6, 8)
  - **Blocks**: Task 9
  - **Blocked By**: Task 2

  **References**:
  - `backend/app/integrations/adapters/base.py` — BaseIntegrationAdapter
  - `https://developers.google.com/drive/api/v3/reference` — Google Drive API docs
  - `backend/app/integrations/oauth.py` — token decryption + refresh

  **Acceptance Criteria**:
  - [ ] All 4 actions execute with valid access token
  - [ ] Token refresh works when access token expired (401 response)
  - [ ] list_files supports MIME type filtering
  - [ ] read_file returns file content with metadata
  - [ ] Pytest tests for all 4 actions

  **QA Scenarios**:
  ```
  Scenario: list_files returns file list
    Tool: Bash (pytest)
    Preconditions: Mock httpx with file list response
    Steps:
      1. Create GoogleDriveAdapter with mock connection
      2. Call execute("list_files", {page_size: 10})
      3. Assert success=True, response has files array with id, name, mimeType
    Expected Result: Files listed
    Evidence: .sisyphus/evidence/task-7-drive-list.txt
  ```

  **Commit**: YES (groups with Tasks 4-6, 8)
  - Message: `feat(integrations): add Google Drive adapter with 4 actions`
  - Files: `backend/app/integrations/adapters/google_drive.py`

---

- [ ] 8. Linear adapter — 4 actions

  **What to do**:
  - Create `backend/app/integrations/adapters/linear.py` with:
    - `create_issue(team_id, title, description?, priority?, assignee_id?)` — GraphQL mutation
    - `update_issue(issue_id, title?, description?, status?, priority?)` — GraphQL mutation
    - `search_issues(query, limit?)` — GraphQL query (search)
    - `list_projects(team_id?, limit?)` — GraphQL query
  - Linear uses GraphQL API — use httpx with POST to https://api.linear.dev/graphql
  - Auth via personal API key or OAuth token
  - Build GraphQL queries as string templates

  **Must NOT do**:
  - Do NOT use Linear REST API (doesn't exist — GraphQL only)
  - Do NOT hardcode GraphQL queries without variables

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 4, 5, 6, 7)
  - **Blocks**: Task 9
  - **Blocked By**: Task 2

  **References**:
  - `backend/app/integrations/adapters/base.py` — BaseIntegrationAdapter
  - `https://developers.linear.app/docs/graphql/working-with-the-graphql-api` — Linear GraphQL API docs
  - `backend/app/integrations/oauth.py` — token decryption

  **Acceptance Criteria**:
  - [ ] All 4 actions execute with valid Linear token
  - [ ] GraphQL queries are parameterized (no injection)
  - [ ] create_issue returns issue ID and URL
  - [ ] search_issues returns paginated results
  - [ ] Pytest tests for all 4 actions (mocked httpx)

  **QA Scenarios**:
  ```
  Scenario: create_issue succeeds
    Tool: Bash (pytest)
    Preconditions: Mock httpx with GraphQL issue creation response
    Steps:
      1. Create LinearAdapter with mock connection
      2. Call execute("create_issue", {team_id: "team-1", title: "Bug: login fails"})
      3. Assert success=True, response contains issue id, identifier (e.g., "TEAM-123")
    Expected Result: Issue created
    Evidence: .sisyphus/evidence/task-8-linear-issue.txt
  ```

  **Commit**: YES (groups with Tasks 4-7)
  - Message: `feat(integrations): add Linear adapter with 4 GraphQL actions`
  - Files: `backend/app/integrations/adapters/linear.py`

---

- [ ] 1. OAuth DB models + migration

  **What to do**:
  - Create `UserOAuthApp` model: user_id, provider (slack/github/notion/gdrive/linear), encrypted_client_id, encrypted_client_secret, scopes (JSON), is_active, created_at, updated_at
  - Create `UserOAuthConnection` model: user_id, provider, app_id (FK), encrypted_access_token, encrypted_refresh_token, token_type, expires_at, provider_account_id, provider_account_name (e.g., workspace name), scopes, status (active/expired/revoked), created_at, updated_at
  - Create Alembic migration
  - Store client secrets encrypted using `integrations/oauth.py` Fernet encryption
  - Use existing `Base` and `TimestampMixin` from common models

  **Must NOT do**:
  - Do NOT store secrets in plaintext
  - Do NOT use the old HttpIntegrationConfig tables — these are separate

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 2, 3, 4-8
  - **Blocked By**: None

  **References**:
  - `backend/app/models/integration_models.py` — existing integration models (pattern)
  - `backend/app/models/webhook_models.py` — model patterns (Base, TimestampMixin usage)
  - `backend/app/integrations/oauth.py` — encrypt_token(), decrypt_token(), Fernet setup
  - `backend/app/models/byok_models.py` — UserAPIKey (encrypted storage pattern)

  **Acceptance Criteria**:
  - [ ] Models created with all required fields
  - [ ] Migration applies: `alembic upgrade head`
  - [ ] Migration rolls back: `alembic downgrade -1`
  - [ ] Encrypted fields are actually encrypted (verify by DB query shows ciphertext)

  **QA Scenarios**:
  ```
  Scenario: Migration applies cleanly
    Tool: Bash
    Preconditions: Clean test DB
    Steps:
      1. Run `alembic upgrade head`
      2. Assert `alembic current` shows new revision
      3. Verify tables exist: `user_oauth_apps`, `user_oauth_connections`
    Expected Result: Tables created
    Evidence: .sisyphus/evidence/task-1-migration.txt

  Scenario: Secrets encrypted at rest
    Tool: Bash
    Preconditions: Migration applied
    Steps:
      1. Insert a row with known client_secret via model
      2. Query raw DB: `SELECT encrypted_client_secret FROM user_oauth_apps`
      3. Assert value is NOT the plaintext secret (ciphertext differs)
    Expected Result: Secrets encrypted
    Evidence: .sisyphus/evidence/task-1-encryption.txt
  ```

  **Commit**: YES
  - Message: `feat(integrations): add OAuth models for user-provided apps and connections`
  - Files: `backend/app/models/integration_models.py`, `backend/alembic/versions/xxx.py`

---

- [ ] 2. OAuth endpoints (initiate, callback, list, disconnect)

  **What to do**:
  - Create `POST /api/v2/integrations/oauth/initiate` — takes provider and stored app_id, returns authorization URL
  - Create `GET /api/v2/integrations/oauth/callback` — receives OAuth code, exchanges for tokens, stores encrypted
  - Create `GET /api/v2/integrations/oauth/connections` — list user's connected accounts
  - Create `DELETE /api/v2/integrations/oauth/connections/{id}` — disconnect (remove tokens)
  - Create `POST /api/v2/integrations/oauth/apps` — register a new OAuth app (store client_id/secret)
  - Create `GET /api/v2/integrations/oauth/apps` — list user's registered apps
  - Create `PUT /api/v2/integrations/oauth/apps/{id}` — update app credentials
  - Create `DELETE /api/v2/integrations/oauth/apps/{id}` — delete app
  - Use httpx for token exchange requests
  - Store tokens with Fernet encryption

  **Must NOT do**:
  - Do NOT expose tokens in API responses
  - Do NOT redirect to external URLs without validation

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 1 (after Task 1)
  - **Blocks**: Tasks 4-8
  - **Blocked By**: Task 1

  **References**:
  - `backend/app/integrations/oauth.py` — OAUTH_PROVIDERS, encrypt_token(), decrypt_token()
  - `backend/app/models/integration_models.py` — UserOAuthApp, UserOAuthConnection (from Task 1)
  - `backend/app/api/deps.py` — get_current_user dependency
  - `backend/app/routers/integrations_v2.py` — existing integration router (pattern)

  **Acceptance Criteria**:
  - [ ] Register app endpoint stores encrypted client_id/secret
  - [ ] Initiate endpoint returns valid authorization URL for each provider
  - [ ] Callback endpoint exchanges code for tokens and stores them
  - [ ] List connections returns user's connected accounts
  - [ ] Disconnect removes tokens from DB
  - [ ] All endpoints require authentication

  **QA Scenarios**:
  ```
  Scenario: Register OAuth app
    Tool: Bash (curl)
    Preconditions: User authenticated
    Steps:
      1. POST /api/v2/integrations/oauth/apps with provider=slack, client_id=xxx, client_secret=yyy
      2. Assert 201 response with app_id
      3. GET /api/v2/integrations/oauth/apps
      4. Assert response includes the app (client_secret NOT in response)
    Expected Result: App registered securely
    Evidence: .sisyphus/evidence/task-2-register-app.txt

  Scenario: Initiate redirects to correct OAuth URL
    Tool: Bash (curl)
    Preconditions: App registered
    Steps:
      1. POST /api/v2/integrations/oauth/initiate with provider=github, app_id=xxx
      2. Assert 200 response with authorization_url
      3. Verify URL starts with https://github.com/login/oauth/authorize
      4. Verify URL includes redirect_uri and state param
    Expected Result: Valid OAuth initiation URL
    Evidence: .sisyphus/evidence/task-2-initiate.txt
  ```

  **Commit**: YES
  - Message: `feat(integrations): add OAuth endpoints for app registration and connection flow`
  - Files: `backend/app/routers/integrations_v2.py`, `backend/app/schemas/integration_v2.py`

---

- [ ] 3. OAuth Frontend — Connection Wizard

  **What to do**:
  - Create `frontend/src/app/[locale]/(dashboard)/integrations/page.tsx` — integration management page
  - Create connection wizard component: Select service → Register app → Connect account → Done
  - Steps:
    1. Service selection grid (Slack, GitHub, Notion, Google Drive, Linear with icons)
    2. App registration form (client_id, client_secret fields)
    3. "Connect" button that opens OAuth popup
    4. Success confirmation with connected account name
  - Show connected accounts with status (active/expired)
  - Show disconnect button per account

  **Must NOT do**:
  - Do NOT store tokens on frontend (never expose them)
  - Do NOT use custom icon assets — use simple SVG or emoji icons

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`flowmanner`, `frontend-design`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 1 (after Task 1)
  - **Blocks**: Task 11
  - **Blocked By**: Task 1

  **References**:
  - `frontend/src/components/ui/` — existing UI components
  - `frontend/src/app/[locale]/(dashboard)/settings/page.tsx` — settings page pattern
  - `frontend/src/app/[locale]/(dashboard)/settings/api-keys/page.tsx` — API key management pattern

  **Acceptance Criteria**:
  - [ ] Page shows all 5 service options with icons
  - [ ] App registration form validates required fields
  - [ ] OAuth popup opens on "Connect" click
  - [ ] Connected accounts displayed with service icon and account name
  - [ ] Disconnect removes account from list
  - [ ] Expired connections show warning badge

  **QA Scenarios**:
  ```
  Scenario: Connection wizard renders
    Tool: Playwright
    Preconditions: Authenticated user
    Steps:
      1. Navigate to /integrations
      2. Assert 5 service cards visible
      3. Click Slack card
      4. Assert app registration form visible with client_id, client_secret fields
    Expected Result: Wizard renders correctly
    Evidence: .sisyphus/evidence/task-3-wizard-render.png

  Scenario: Connected account shown
    Tool: Playwright
    Preconditions: User has at least one connected account
    Steps:
      1. Navigate to /integrations
      2. Assert "Connected" badge visible for the integration
      3. Assert account name displayed
      4. Assert "Disconnect" button visible
    Expected Result: Connected account shown
    Evidence: .sisyphus/evidence/task-3-connected-account.png
  ```

  **Commit**: YES
  - Message: `feat(integrations): add OAuth connection wizard UI with service selection and account management`
  - Files: `frontend/src/app/[locale]/(dashboard)/integrations/page.tsx`, `frontend/src/components/integrations/ConnectionWizard.tsx`

### Wave 3 — Frontend Actions + Integration

> Action cards appear in the mission builder as selectable task types.
> Each card renders input fields for its action's parameters and shows the output preview.

- [ ] 9. Action registry API + mission builder integration

  **What to do**:
  - Create action registry at `backend/app/services/action_registry.py`:
    - `get_available_actions(user_id)` — returns all actions user's connections enable
    - `execute_action(user_id, connection_id, action_name, params)` — dispatches to adapter
    - Auto-discovers adapters from `integrations/adapters/` directory
  - Create `POST /api/v2/integrations/actions/execute` — execute an action
  - Create `GET /api/v2/integrations/actions/available` — list user's available actions
  - Wire action type into the mission task system (new task_type: "integration_action")
  - Modify mission executor to handle "integration_action" task type

  **Must NOT do**:
  - Do NOT modify existing task types (create new handler, don't change old ones)
  - Do NOT allow arbitrary code execution

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (before Tasks 10, 11)
  - **Blocks**: Tasks 10, 11
  - **Blocked By**: Tasks 4, 5, 6, 7, 8

  **References**:
  - `backend/app/services/task_executor.py` — task dispatch (add "integration_action" handler)
  - `backend/app/services/mission_executor.py` — main executor loop
  - `backend/app/models/mission_models.py` — MissionTask.task_type field

  **Acceptance Criteria**:
  - [ ] Action registry returns available actions based on user's connections
  - [ ] Action execution dispatches to correct adapter
  - [ ] Missions with "integration_action" tasks execute correctly
  - [ ] Unknown action names return clear error
  - [ ] Pytest tests for registry and execution

  **QA Scenarios**:
  ```
  Scenario: Available actions returned for user with connections
    Tool: Bash (curl)
    Preconditions: User has Slack and GitHub connections
    Steps:
      1. GET /api/v2/integrations/actions/available
      2. Assert response has actions from both Slack and GitHub
      3. Assert each action has: name, description, input_schema, provider
    Expected Result: Correct actions listed
    Evidence: .sisyphus/evidence/task-9-available-actions.txt

  Scenario: Execute action with valid params
    Tool: Bash (curl)
    Preconditions: User has Slack connection
    Steps:
      1. POST /api/v2/integrations/actions/execute with connection_id, action=send_message
      2. Assert success=True, response contains action output
    Expected Result: Action executed
    Evidence: .sisyphus/evidence/task-9-execute-action.txt
  ```

  **Commit**: YES
  - Message: `feat(integrations): add action registry with mission executor integration`
  - Files: `backend/app/services/action_registry.py`, `backend/app/routers/integrations_v2.py`

---

- [ ] 10. Action card components for all 5 services

  **What to do**:
  - Create `frontend/src/components/integrations/actions/` with:
    - `ActionCard.tsx` — generic action card wrapper (inputs + execute + outputs)
    - `SlackActions.tsx` — cards for send_message, search, list_channels, create_channel
    - `GitHubActions.tsx` — cards for create_issue, create_pr, search_repos, get_file
    - `NotionActions.tsx` — cards for create_page, query_database, append_block
    - `GoogleDriveActions.tsx` — cards for list_files, create_doc, search, read_file
    - `LinearActions.tsx` — cards for create_issue, update_issue, search, list_projects
  - Each card: selects connected account, renders action-specific form, shows result preview
  - Wire into mission builder at `missions/builder/page.tsx` as new task type option

  **Must NOT do**:
  - Do NOT duplicate form validation (use shared)
  - Do NOT hardcode connection IDs

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`flowmanner`, `frontend-design`]

  **Parallelization**:
  - **Can Run In Parallel**: NO (cards share patterns)
  - **Parallel Group**: Wave 3 (after Task 9)
  - **Blocks**: Task 11
  - **Blocked By**: Task 9

  **References**:
  - `frontend/src/app/[locale]/(dashboard)/missions/builder/page.tsx` — mission builder
  - `frontend/src/components/mission-builder/` — existing builder components
  - `frontend/src/components/ui/` — UI component library

  **Acceptance Criteria**:
  - [ ] 5 services × action cards render in mission builder
  - [ ] Each card shows connection selector + action-specific form
  - [ ] Form validation works (required fields marked)
  - [ ] Cards load dynamic data (e.g., channel list for Slack)
  - [ ] Actions can be saved as mission task

  **QA Scenarios**:
  ```
  Scenario: Slack action card renders in mission builder
    Tool: Playwright
    Preconditions: User has Slack connection, on mission builder page
    Steps:
      1. Click "Add Integration Action" button
      2. Select Slack from provider list
      3. Select "send_message" action
      4. Assert form shows: channel selector, message field
    Expected Result: Slack action card rendered
    Evidence: .sisyphus/evidence/task-10-slack-card.png

  Scenario: Action saves as mission task
    Tool: Playwright
    Preconditions: Mission builder with action configured
    Steps:
      1. Fill action form with valid data
      2. Click "Save Task"
      3. Assert task appears in mission plan
      4. Assert task type shows "Slack: Send Message"
    Expected Result: Action saved as task
    Evidence: .sisyphus/evidence/task-10-save-task.png
  ```

  **Commit**: YES
  - Message: `feat(integrations): add action card components for all 5 services in mission builder`
  - Files: `frontend/src/components/integrations/actions/*.tsx`

---

- [ ] 11. Integration management page polish + comprehensive tests

  **What to do**:
  - Polish integration management page with full CRUD, status badges
  - Add "Reconnect" button for expired connections
  - Add connection health check (verify token still valid)
  - Write comprehensive backend tests:
    - All OAuth endpoints (register app, initiate, callback mocked)
    - All adapter actions (all 19 actions across 5 services)
    - Action registry dispatch
    - Mission execution with integration_action tasks
  - Frontend vitest tests for action card components

  **Must NOT do**:
  - Do NOT test third-party API behavior (mock httpx)
  - Do NOT skip security tests (unauthenticated access, token exposure)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`flowmanner`, `write-tests`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3
  - **Blocks**: F1-F4
  - **Blocked By**: Tasks 3, 10

  **References**:
  - `backend/app/tests/test_integrations_v2.py` — existing integration tests
  - `frontend/src/components/integrations/` — integration components (from Tasks 3, 10)

  **Acceptance Criteria**:
  - [ ] Integration page shows connection health status
  - [ ] Reconnect flow works for expired connections
  - [ ] All backend tests pass: `pytest app/tests/ -v`
  - [ ] All adapter actions tested (19+ tests)
  - [ ] Frontend tests pass

  **QA Scenarios**:
  ```
  Scenario: All integration tests pass
    Tool: Bash
    Preconditions: All code changes applied, DB migrated
    Steps:
      1. Run `pytest app/tests/test_integrations_v2.py -v`
      2. Assert all tests pass
      3. Run `npm run test` in frontend
      4. Assert all frontend tests pass
    Expected Result: All tests pass
    Evidence: .sisyphus/evidence/task-11-all-tests.txt
  ```

  **Commit**: YES
  - Message: `test: add comprehensive tests for all integration adapters and OAuth flow`
  - Files: `backend/app/tests/test_integrations_v2.py`, `frontend/src/components/integrations/**/*.test.tsx`

---

## Final Verification Wave

> 4 review agents run in PARALLEL. ALL must APPROVE.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists. For each "Must NOT Have": search for forbidden patterns. Check evidence files. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality + Security Review** — `unspecified-high`
  Run `ruff check`, pytest. Security focus: encrypted secrets verified, no token exposure, OAuth callback validates state, no hardcoded secrets.
  Output: `Lint [PASS/FAIL] | Tests [N pass/N fail] | Security [N checks] | VERDICT`

- [ ] F3. **Real Manual QA** — end-to-end — `unspecified-high`
  Execute every QA scenario from every task. Verify each adapter's actions. Test OAuth flow with mock token exchange. Test mission execution with integration_action tasks.
  Output: `Scenarios [N/N pass] | Integration [N/N] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1. Check "Must NOT do" compliance. Detect cross-task contamination.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

- **Wave 1**: 3 commits (models, endpoints, frontend wizard)
- **Wave 2**: 1 squash commit for all 5 adapters (+ base adapter)
- **Wave 3**: 3 commits (registry, action cards, tests)
- **Final**: Fixes from verification

> **Total**: ~10 commits across 3 waves

---

## Success Criteria

### Verification Commands
```bash
# Backend tests
cd /opt/flowmanner/backend && pytest app/tests/test_integrations_v2.py -v
# Expected: All tests pass

# Frontend build
cd /home/glenn/FlowmannerV2-frontend && npm run build
# Expected: No build errors

# API health
curl http://127.0.0.1:8000/api/health
# Expected: healthy
```

### Final Checklist
- [ ] All 5 services have OAuth connection working end-to-end
- [ ] All 19 actions execute successfully
- [ ] Integration management page shows connections with health status
- [ ] Action cards appear in mission builder for connected services
- [ ] Missions with integration_action tasks execute correctly
- [ ] All tokens encrypted at rest
- [ ] All tests pass — zero regressions
- [ ] Zero secrets exposed in code or logs
