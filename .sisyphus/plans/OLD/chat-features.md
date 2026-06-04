# Chat Feature Implementation: Image Upload, File Upload, Internet Search Toggle

## TL;DR

> **Quick Summary**: Add image upload/paste, file upload, and web search toggle to the SSEChat input bar. Frontend gets attachment controls + preview chips; backend stream schema gets `attachments` and `web_search` fields with processing logic.
>
> **Deliverables**:
> - Image upload button + clipboard paste handler with inline thumbnail preview
> - File upload button with file chip/badge display
> - Web search toggle button with active state indicator
> - Extended ChatMessage type with `attachments` field
> - Extended ChatMessageCreate backend schema with `attachments` + `web_search`
> - Backend attachment processing (images as multimodal, files as context injection)
> - Backend web search integration before LLM call
> - Updated MessageList to render attachments in messages
>
> **Estimated Effort**: Large
> **Parallel Execution**: YES - 4 waves
> **Critical Path**: Task 1 (types) → Task 3 (backend schema) → Task 4 (attachment processing) → Task 7 (web search integration) → Task 10 (input bar UI) → Task 12 (message rendering) → Final

---

## Context

### Original Request
Add three capabilities to the Flowmanner chat input bar: (1) Image upload/paste with inline thumbnail, (2) File upload with file chip display, (3) Internet search toggle that triggers backend web search before LLM response.

### Interview Summary
**Key Discussions**:
- Must use existing design tokens (btn-clay, input-glass, glass-card, text-charcoal)
- Must use lucide-react icons already in the project
- react-dropzone already installed — reuse for drag-and-drop
- Extend existing SSE stream body schema, not replace
- Frontend file-api.ts already has `uploadFile()` — reuse this pattern

**Research Findings**:
- `POST /api/files/upload` EXISTS — returns `{id, filename, content_type, size, user_id, created_at}`
- Chat stream `POST /api/chat/threads/{id}/chat/stream` accepts `ChatMessageCreate {content, role, model, model_id, system_prompt}` — NO attachment support yet
- Web search service EXISTS at `POST /api/web-search/search` with SearXNG/Tavily/Exa/DDG providers
- `stream_message_to_llm()` builds OpenAI-format messages from thread history — no multimodal or web search injection
- `ChatMessage` frontend type has NO `attachments` field
- llama.cpp local model (Qwen3.6-27B) is TEXT-ONLY — multimodal requires vision-capable external model

### Gap Analysis (Self-Review)
**Identified Gaps** (addressed):
- llama.cpp is text-only: When model is `llamacpp/*`, images are sent as `[Image: filename]` text description instead of multimodal content array
- Max attachments per message: 5 (hard limit)
- Max file sizes: 10MB images, 20MB documents
- Mobile companion: Attachments gracefully degraded (not supported in mobile mode initially)
- Abort during upload: XHR abort controller must be cleaned up on Stop

---

## Work Objectives

### Core Objective
Extend the chat input bar to support image/file uploads and web search toggle, with full backend integration for processing attachments and injecting search results into LLM context.

### Concrete Deliverables
- `src/lib/chat-types.ts` — Extended `ChatMessage` with `Attachment` type, extended `SSEEvent` with attachment events
- `src/components/chat/AttachmentPreview.tsx` — New component for thumbnail/chip preview in input bar
- `src/components/chat/SSEChat.tsx` — Modified with upload buttons, paste handler, drag-drop, web search toggle, attachment state
- `src/components/chat/MessageList.tsx` — Modified to render attachments in messages
- `backend/app/schemas/chat.py` — Extended `ChatMessageCreate` with `attachments` and `web_search` fields
- `backend/app/services/chat_service.py` — Extended `stream_message_to_llm` with attachment processing + web search injection
- `backend/app/api/v1/chat.py` — Updated stream endpoint to pass new fields through

### Definition of Done
- [ ] User can click image button, select image, see thumbnail, send it
- [ ] User can paste image from clipboard, see thumbnail, send it
- [ ] User can click file button, select document, see file chip, send it
- [ ] User can toggle web search, see active indicator, and LLM response includes search results
- [ ] Attachments render correctly in sent messages (both user and assistant side)
- [ ] All existing chat functionality unchanged (text messages, slash commands, streaming, branching)
- [ ] Backend rebuilds cleanly and all existing API tests pass

### Must Have
- Image upload via button click
- Image upload via clipboard paste (Ctrl+V)
- File upload via button click
- Inline thumbnail preview for images before send
- File chip/badge preview for documents before send
- Web search toggle with visual active state
- Backend processes attachments correctly
- Backend injects web search results into LLM context
- Remove attachment with X button before sending
- Loading state during upload

### Must NOT Have (Guardrails)
- NO new npm packages (react-dropzone and lucide-react already installed)
- NO changes to /attach slash command behavior
- NO changes to mobile companion (MobileCompanion.tsx) — can be future work
- NO drag-and-drop on message area — only on input area
- NO changes to existing auth flow (getAuthToken, apiClient)
- NO modification to thread branching, message editing, or message deletion
- NO AI slop: no excessive comments, no premature abstractions, no generic names
- NO breaking changes to existing chat stream body — new fields are optional

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### Test Decision
- **Infrastructure exists**: YES (Vitest + Playwright configured)
- **Automated tests**: YES (tests-after — implementation first, then tests)
- **Framework**: Vitest (unit), Playwright (E2E)

### QA Policy
Every task includes agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Frontend/UI**: Use Playwright — navigate, interact, assert DOM, screenshot
- **API/Backend**: Use Bash (curl) — send requests, assert status + response fields
- **Component**: Use Bash (vitest) — run unit tests

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — foundation types + backend schema):
├── Task 1: Frontend Attachment types + ChatMessage extension [quick]
├── Task 2: Attachment preview component [visual-engineering]
├── Task 3: Backend ChatMessageCreate schema extension [quick]
└── Task 4: Web search toggle state hook [quick]

Wave 2 (After Wave 1 — backend processing + frontend integration):
├── Task 5: Backend attachment processing in stream_message_to_llm (depends: 3) [deep]
├── Task 6: Backend web search injection in stream (depends: 3) [unspecified-high]
├── Task 7: Image upload + paste handler in SSEChat (depends: 1, 2) [unspecified-high]
├── Task 8: File upload handler in SSEChat (depends: 1, 2) [quick]

Wave 3 (After Wave 2 — UI integration + rendering):
├── Task 9: Web search toggle UI in input bar (depends: 4) [visual-engineering]
├── Task 10: Attachment rendering in MessageList (depends: 1) [visual-engineering]
├── Task 11: SSEChat input bar integration — wire everything together (depends: 7, 8, 9) [deep]

Wave 4 (After Wave 3 — polish + testing):
├── Task 12: Edge cases + error handling polish (depends: 11) [unspecified-high]
└── Task 13: E2E smoke test (depends: 12) [quick]

Wave FINAL (After ALL tasks — 4 parallel reviews):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
-> Present results -> Get explicit user okay

Critical Path: T1 → T3 → T5 → T11 → T12 → T13 → F1-F4
Parallel Speedup: ~60% faster than sequential
Max Concurrent: 4 (Wave 1)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 7, 8, 10 | 1 |
| 2 | — | 7, 8 | 1 |
| 3 | — | 5, 6 | 1 |
| 4 | — | 9 | 1 |
| 5 | 3 | 11 | 2 |
| 6 | 3 | 11 | 2 |
| 7 | 1, 2 | 11 | 2 |
| 8 | 1, 2 | 11 | 2 |
| 9 | 4 | 11 | 2 |
| 10 | 1 | 12 | 3 |
| 11 | 7, 8, 9 | 12 | 3 |
| 12 | 11 | 13 | 4 |
| 13 | 12 | F1-F4 | 4 |

### Agent Dispatch Summary

- **Wave 1**: 4 tasks — T1 `quick`, T2 `visual-engineering`, T3 `quick`, T4 `quick`
- **Wave 2**: 5 tasks — T5 `deep`, T6 `unspecified-high`, T7 `unspecified-high`, T8 `quick`
- **Wave 3**: 3 tasks — T9 `visual-engineering`, T10 `visual-engineering`, T11 `deep`
- **Wave 4**: 2 tasks — T12 `unspecified-high`, T13 `quick`
- **FINAL**: 4 — F1 `oracle`, F2 `unspecified-high`, F3 `unspecified-high`, F4 `deep`

---

## TODOs

- [ ] 1. Frontend Attachment Types + ChatMessage Extension

  **What to do**:
  - Add `Attachment` type to `src/lib/chat-types.ts`:
    ```typescript
    export type AttachmentType = "image" | "file";

    export interface Attachment {
      id: string;            // Frontend-generated UUID for temp tracking
      file_id?: string;      // Backend file ID after upload
      type: AttachmentType;
      filename: string;
      content_type: string;
      size: number;
      url?: string;          // Object URL for local preview (blob:)
      status: "pending" | "uploading" | "ready" | "error";
      error?: string;
    }
    ```
  - Extend `ChatMessage` interface with `attachments?: Attachment[]`
  - Export `MAX_ATTACHMENTS = 5`, `MAX_IMAGE_SIZE = 10 * 1024 * 1024`, `MAX_FILE_SIZE = 20 * 1024 * 1024` constants

  **Must NOT do**:
  - Do NOT modify any existing types or interfaces
  - Do NOT change ChatMessage fields that already exist

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 4)
  - **Blocks**: Tasks 7, 8, 10
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `src/lib/chat-types.ts:17-27` — Current `ChatMessage` interface — extend with optional `attachments` field
  - `src/lib/chat-types.ts:97-98` — `ToolType` pattern for union type definitions

  **Acceptance Criteria**:
  - [ ] `Attachment`, `AttachmentType` types exported from `src/lib/chat-types.ts`
  - [ ] `ChatMessage` has optional `attachments?: Attachment[]` field
  - [ ] Size constants exported
  - [ ] `npm run build` succeeds with no type errors

  **QA Scenarios**:
  ```
  Scenario: Types are importable and correct
    Tool: Bash
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend && npx tsc --noEmit src/lib/chat-types.ts
    Expected Result: Exit code 0, no errors
    Evidence: .sisyphus/evidence/task-1-typecheck.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(chat): add attachment types to chat-types`
  - Files: `src/lib/chat-types.ts`

- [ ] 2. Attachment Preview Component (AttachmentPreview.tsx)

  **What to do**:
  - Create `src/components/chat/AttachmentPreview.tsx`
  - Two rendering modes based on `attachment.type`:
    - **Image**: Show `<img>` thumbnail (80x80, object-cover, rounded-lg) with X remove button
    - **File**: Show file chip badge with icon (FileText/PDF icon based on content_type), filename truncated, size, X remove button
  - Props: `{ attachments: Attachment[], onRemove: (id: string) => void }`
  - Container: `flex flex-wrap gap-2 py-2` — goes above textarea in the input area
  - Each item: `glass-card` style, `rounded-lg`, X button uses `X` icon from lucide-react
  - Image thumbnails: `w-20 h-20 object-cover rounded-lg border border-white/[0.08]`
  - File chips: `flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/[0.06] text-xs text-charcoal`
  - Upload spinner: Show `Loader2` with `animate-spin` when `status === "uploading"`
  - Error state: Red border + error text when `status === "error"`
  - Size display: Format bytes as KB/MB (helper function)

  **Must NOT do**:
  - Do NOT use any component library beyond what's installed
  - Do NOT create a separate CSS file — use Tailwind classes only

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3, 4)
  - **Blocks**: Tasks 7, 8
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `src/components/chat/SSEChat.tsx:497-527` — Input area layout — the preview row goes between the slash command popup (line 473) and the flex row (line 497)
  - `src/components/rag/DocumentUploader.tsx:98-150` — Dropzone UI patterns with `glass-card`, `border-dashed`, `UploadCloud` icon
  - `src/components/chat/MessageList.tsx:342-346` — User message styling: `bg-clay/15 text-charcoal rounded-2xl`

  **Icon References**:
  - `X` from lucide-react — remove button (already used in MessageList)
  - `Loader2` from lucide-react — upload spinner (already used in MessageList)
  - `FileText` from lucide-react — file icon (already used in ChatHeader)
  - `ImageIcon` from lucide-react — image icon (standard lucide)
  - `Paperclip` from lucide-react — generic file icon

  **Acceptance Criteria**:
  - [ ] Component renders image thumbnails correctly
  - [ ] Component renders file chips correctly
  - [ ] Remove button calls `onRemove` with correct attachment id
  - [ ] Upload spinner shown for "uploading" status
  - [ ] `npm run build` succeeds

  **QA Scenarios**:
  ```
  Scenario: Component renders without errors
    Tool: Bash
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend && npm run build 2>&1 | tail -5
    Expected Result: Build succeeds, no errors
    Evidence: .sisyphus/evidence/task-2-build.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(chat): add attachment preview component`
  - Files: `src/components/chat/AttachmentPreview.tsx`

- [ ] 3. Backend ChatMessageCreate Schema Extension

  **What to do**:
  - In `/opt/flowmanner/backend/app/schemas/chat.py`, extend `ChatMessageCreate`:
    ```python
    class AttachmentPayload(BaseModel):
        file_id: str
        type: str  # "image" | "file"
        filename: str
        content_type: str
        size: int

    class ChatMessageCreate(BaseModel):
        content: str
        role: str = "user"
        model: Optional[str] = None
        model_id: Optional[str] = None
        system_prompt: Optional[str] = None
        attachments: Optional[List[AttachmentPayload]] = None  # NEW
        web_search: Optional[bool] = None  # NEW
    ```
  - In `/opt/flowmanner/backend/app/api/v1/chat.py`, update `chat_with_llm_stream` to pass `payload.attachments` and `payload.web_search` to `stream_message_to_llm`
  - Update `stream_message_to_llm` signature to accept these new parameters

  **Must NOT do**:
  - Do NOT remove or rename any existing fields
  - Do NOT change existing endpoint paths
  - Do NOT modify non-chat routes

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 4)
  - **Blocks**: Tasks 5, 6
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `/opt/flowmanner/backend/app/schemas/chat.py:50-55` — Current `ChatMessageCreate` — add `attachments` and `web_search` fields
  - `/opt/flowmanner/backend/app/api/v1/chat.py:427-458` — `chat_with_llm_stream` endpoint — pass new fields to `stream_message_to_llm`
  - `/opt/flowmanner/backend/app/services/chat_service.py:569-578` — `stream_message_to_llm` signature — add `attachments` and `web_search` params

  **API References**:
  - `/opt/flowmanner/backend/app/api/v1/file.py:49-78` — File upload handler — need to read files from disk by `file_id`
  - `/opt/flowmanner/backend/app/api/v1/file.py:116-134` — `get_file` handler — shows how to look up file by ID from DB

  **Acceptance Criteria**:
  - [ ] `AttachmentPayload` model defined in chat schema
  - [ ] `ChatMessageCreate` has `attachments` and `web_search` optional fields
  - [ ] `stream_message_to_llm` signature accepts new params
  - [ ] Stream endpoint passes new fields through
  - [ ] Backend Docker build succeeds: `docker build -t workflows-backend:restored /opt/flowmanner/backend/`

  **QA Scenarios**:
  ```
  Scenario: Backend builds with new schema
    Tool: Bash
    Steps:
      1. docker build -t workflows-backend:restored /opt/flowmanner/backend/ 2>&1 | tail -5
    Expected Result: Successfully built / tagged
    Evidence: .sisyphus/evidence/task-3-backend-build.txt

  Scenario: Schema accepts new fields without error
    Tool: Bash
    Steps:
      1. docker compose exec backend python -c "from app.schemas.chat import ChatMessageCreate; m = ChatMessageCreate(content='test', web_search=True, attachments=[{'file_id':'x','type':'file','filename':'a.txt','content_type':'text/plain','size':100}]); print(m.model_dump_json())"
    Expected Result: Valid JSON output with all fields
    Evidence: .sisyphus/evidence/task-3-schema-test.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(chat): extend ChatMessageCreate schema with attachments and web_search`
  - Files: `backend/app/schemas/chat.py`, `backend/app/api/v1/chat.py`, `backend/app/services/chat_service.py`

- [ ] 4. Web Search Toggle State Hook

  **What to do**:
  - Create `src/components/chat/useWebSearchToggle.ts` — a simple hook that manages the web search toggle state
  - Returns `{ enabled: boolean, toggle: () => void }`
  - Persists toggle state to localStorage key `"fm_web_search_toggle"` so it persists across thread changes
  - Default: `false`

  **Must NOT do**:
  - Do NOT create a full context provider — this is a simple boolean state
  - Do NOT tie this to any backend logic — it's purely frontend state

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3)
  - **Blocks**: Task 9
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `src/app/[locale]/(dashboard)/chat/page-client.tsx:34` — `SETTINGS_STORAGE_KEY` pattern for localStorage persistence
  - `src/app/[locale]/(dashboard)/chat/page-client.tsx:36-48` — `loadThreadSettings` / `saveThreadSettings` pattern

  **Acceptance Criteria**:
  - [ ] Hook exports `useWebSearchToggle`
  - [ ] Returns `{ enabled: boolean, toggle: () => void }`
  - [ ] State persists in localStorage
  - [ ] `npm run build` succeeds

  **QA Scenarios**:
  ```
  Scenario: Hook builds without error
    Tool: Bash
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend && npm run build 2>&1 | tail -5
    Expected Result: Build succeeds
    Evidence: .sisyphus/evidence/task-4-build.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(chat): add web search toggle state hook`
  - Files: `src/components/chat/useWebSearchToggle.ts`

- [ ] 5. Backend Attachment Processing in stream_message_to_llm

  **What to do**:
  - In `stream_message_to_llm` (chat_service.py), after building `messages_for_llm`, process attachments:
  - For each attachment with `type === "image"`:
    - Read file from disk using file_id (query `UserFile` table)
    - Check if model supports vision: if `raw_model.startswith("llamacpp/")`, skip image content, add `[Image: {filename}]` text to user message instead
    - For vision-capable models: Convert the last user message's `content` from string to OpenAI multimodal format:
      ```python
      [{"type": "text", "text": original_content}, {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{b64_data}"}}]
      ```
  - For each attachment with `type === "file"`:
    - Read file content from disk
    - Prepend a system-like message: `[Attached file: {filename}]\n{file_content[:3000]}\n[End of attached file]`
  - Import `UserFile` model from `app.models.phase4_models` and `select` from SQLAlchemy

  **Must NOT do**:
  - Do NOT modify the SSE streaming protocol
  - Do NOT change how tokens are yielded
  - Do NOT break the existing BYOK key resolution logic

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6, 7, 8)
  - **Blocks**: Task 11
  - **Blocked By**: Task 3

  **References**:
  **Pattern References**:
  - `/opt/flowmanner/backend/app/services/chat_service.py:569-648` — `stream_message_to_llm` full implementation
  - `/opt/flowmanner/backend/app/services/chat_service.py:629` — `_build_chat_messages(db, thread_id)` — this is where messages are assembled, right before the LLM call at line 630
  - `/opt/flowmanner/backend/app/api/v1/file.py:116-134` — Pattern for querying `UserFile` by ID from DB
  - `/opt/flowmanner/backend/app/api/v1/file.py:173-177` — Pattern for reading file content from disk (`Path(file.storage_path).read_bytes()`)

  **API References**:
  - OpenAI multimodal format: `content` can be a list of `[{type: "text", text: "..."}, {type: "image_url", image_url: {url: "data:image/png;base64,..."}}]`

  **Acceptance Criteria**:
  - [ ] Function accepts `attachments` parameter
  - [ ] Image attachments: Read from disk, base64 encode, convert user message to multimodal format for vision models
  - [ ] Image attachments: For llamacpp models, add `[Image: filename]` text instead
  - [ ] File attachments: Read text content, prepend as context message
  - [ ] Backend builds and starts: `docker build -t workflows-backend:restored /opt/flowmanner/backend/ && docker compose up -d --no-deps --force-recreate backend`
  - [ ] Existing chat streaming still works (no regressions)

  **QA Scenarios**:
  ```
  Scenario: Backend rebuilds and starts cleanly
    Tool: Bash
    Steps:
      1. docker build -t workflows-backend:restored /opt/flowmanner/backend/ 2>&1 | tail -3
      2. docker compose up -d --no-deps --force-recreate backend
      3. sleep 5 && curl -s http://127.0.0.1:8000/api/health
    Expected Result: Health check returns 200 OK
    Evidence: .sisyphus/evidence/task-5-health.txt

  Scenario: Existing text-only streaming still works
    Tool: Bash
    Steps:
      1. curl -s -X POST http://127.0.0.1:8000/api/chat/threads/1/chat/stream -H "Content-Type: application/json" -d '{"content":"hello"}' | head -5
    Expected Result: SSE stream starts with data: lines (may 401/404 if no auth/thread — but no 500)
    Evidence: .sisyphus/evidence/task-5-stream-test.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(chat): implement backend attachment processing for images and files`
  - Files: `backend/app/services/chat_service.py`, `backend/app/api/v1/chat.py`
  - Pre-commit: `docker build -t workflows-backend:restored /opt/flowmanner/backend/`

- [ ] 6. Backend Web Search Injection in Stream

  **What to do**:
  - In `stream_message_to_llm`, when `web_search=True`:
    1. Import and call `EnhancedWebSearchService` from `app.services.web_search.service_enhanced`
    2. Run `await service.search(query=content, max_results=5)` before the LLM call
    3. Format results as a context message prepended to the messages array:
       ```
       [Web search results for "{query}":]
       1. {title} - {url}
          {snippet}
       2. ...
       [End of search results]
       ```
    4. Insert this as a system message before the user message
    5. If search fails or returns no results, log warning but proceed without results (don't block the LLM call)
  - Create `SearchConfig` with `duckduckgo_enabled=True` (free, no API key needed) and `searxng_enabled=True` (self-hosted)

  **Must NOT do**:
  - Do NOT make web search blocking — if it fails, still send to LLM
  - Do NOT add search results to the database — they're ephemeral context
  - Do NOT modify the web search service itself

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`flowmanner`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 5, 7, 8)
  - **Blocks**: Task 11
  - **Blocked By**: Task 3

  **References**:
  **Pattern References**:
  - `/opt/flowmanner/backend/app/services/web_search/web_search_routes_enhanced.py:18-28` — `get_search_service()` factory pattern for creating the service
  - `/opt/flowmanner/backend/app/services/web_search/web_search_routes_enhanced.py:66-82` — Search call pattern: `service.search(query=..., max_results=..., providers=...)`
  - `/opt/flowmanner/backend/app/services/web_search/models.py` — `SearchConfig` and `SearchResponse` models
  - `/opt/flowmanner/backend/app/services/chat_service.py:629` — Where messages_for_llm is built — search results get prepended here

  **Acceptance Criteria**:
  - [ ] `web_search=True` in stream body triggers web search before LLM call
  - [ ] Search results formatted and injected as context message
  - [ ] Search failure does not break the stream (graceful fallback)
  - [ ] Backend builds and starts
  - [ ] `curl http://127.0.0.1:8000/api/web-search/health` returns OK

  **QA Scenarios**:
  ```
  Scenario: Web search service is healthy
    Tool: Bash
    Steps:
      1. curl -s http://127.0.0.1:8000/api/web-search/health
    Expected Result: JSON response with status info
    Evidence: .sisyphus/evidence/task-6-search-health.txt

  Scenario: Backend rebuilds with web search integration
    Tool: Bash
    Steps:
      1. docker build -t workflows-backend:restored /opt/flowmanner/backend/ 2>&1 | tail -3
      2. docker compose up -d --no-deps --force-recreate backend
      3. sleep 5 && curl -s http://127.0.0.1:8000/api/health
    Expected Result: Health check 200 OK
    Evidence: .sisyphus/evidence/task-6-rebuild.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(chat): integrate web search into chat streaming pipeline`
  - Files: `backend/app/services/chat_service.py`

- [ ] 7. Image Upload + Paste Handler in SSEChat

  **What to do**:
  - Add state to SSEChat: `const [attachments, setAttachments] = useState<Attachment[]>([]);`
  - Add `const uploadAbortRef = useRef<AbortController | null>(null);`
  - **Image upload button**: Add `ImageIcon` button before textarea (same style as send button, using `btn-clay` with `p-2`)
  - **Hidden file input**: `<input type="file" accept="image/*" className="hidden" ref={imageInputRef} onChange={handleImageSelect} />`
  - **Paste handler**: Add `onPaste` to the textarea div wrapper — detect `e.clipboardData.items` with `type.startsWith("image/")`, create File from blob, add to attachments
  - **Upload function**: For each new attachment:
    1. Set status to "uploading"
    2. Create Object URL for preview (`URL.createObjectURL(file)`)
    3. Call `/api/files/upload` with FormData (reuse pattern from `file-api.ts` line 67-109)
    4. On success: set `file_id`, status "ready"
    5. On error: set status "error" with message
  - **Remove handler**: `setAttachments(prev => prev.filter(a => a.id !== id))` — also revoke Object URL
  - Render `<AttachmentPreview attachments={attachments} onRemove={handleRemoveAttachment} />` between slash command area and the textarea row
  - Pass `attachments` in the stream body (only those with status "ready")

  **Must NOT do**:
  - Do NOT modify the mobile companion
  - Do NOT change the textarea styling
  - Do NOT break the existing slash command autocomplete

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 5, 6, 8)
  - **Blocks**: Task 11
  - **Blocked By**: Tasks 1, 2

  **References**:
  **Pattern References**:
  - `src/components/chat/SSEChat.tsx:470-529` — Input area layout — insert AttachmentPreview between line 495 (end of slash commands) and line 497 (start of flex row)
  - `src/components/chat/SSEChat.tsx:497-527` — The flex row with textarea + buttons — add image button before textarea
  - `src/lib/file-api.ts:67-109` — `uploadFile()` function using XMLHttpRequest + FormData — copy this pattern (XHR for progress tracking)
  - `src/components/rag/DocumentUploader.tsx:36-58` — Upload function pattern with `getAuthToken()` and FormData

  **API References**:
  - `POST /api/files/upload` — multipart form, field `file`, returns `{id, filename, content_type, size, user_id, created_at}`
  - Auth: `Authorization: Bearer {token}` header (from `getAuthToken()`)

  **Acceptance Criteria**:
  - [ ] Image button opens file picker filtered to images
  - [ ] Clipboard paste (Ctrl+V) with image on clipboard adds to attachments
  - [ ] Thumbnail preview shows in AttachmentPreview
  - [ ] Upload completes with file_id set
  - [ ] Remove button clears attachment
  - [ ] Attachments included in stream body when sending
  - [ ] `npm run build` succeeds

  **QA Scenarios**:
  ```
  Scenario: Build succeeds with image upload code
    Tool: Bash
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend && npm run build 2>&1 | tail -5
    Expected Result: Build succeeds
    Evidence: .sisyphus/evidence/task-7-build.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(chat): add image upload and clipboard paste to chat input`
  - Files: `src/components/chat/SSEChat.tsx`

- [ ] 8. File Upload Handler in SSEChat

  **What to do**:
  - Add **file upload button**: `Paperclip` icon button next to image button (same `btn-clay p-2` style)
  - Hidden file input: `<input type="file" accept=".pdf,.txt,.md,.csv,.json,.docx,.py,.js,.ts,.tsx,.jsx,.html,.css,.yaml,.yml,.xml" className="hidden" ref={fileInputRef} onChange={handleFileSelect} />`
  - File selection handler: Same pattern as image — create Attachment with type "file", upload, set status
  - File types that are also images (png, jpg, etc.) should be routed to the image handler instead
  - Reuse the same `attachments` state array — both image and file handlers add to it
  - Max 5 total attachments enforced: `if (attachments.length >= 5) { toast.error("Max 5 attachments"); return; }`
  - Drag-and-drop on input area: Add `onDragOver`, `onDrop` handlers to the input wrapper div. Use `e.dataTransfer.files` to process dropped files.

  **Must NOT do**:
  - Do NOT use react-dropzone component (the useDropzone hook is overkill for this simple drop zone)
  - Do NOT change the existing input area structure beyond adding handlers

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 5, 6, 7)
  - **Blocks**: Task 11
  - **Blocked By**: Tasks 1, 2

  **References**:
  **Pattern References**:
  - `src/components/chat/SSEChat.tsx:497` — The flex row where file button goes (next to image button)
  - `src/lib/file-api.ts:67-109` — Upload function pattern — reuse the XHR + FormData approach
  - `src/components/rag/DocumentUploader.tsx:26-34` — Accepted file types for reference

  **Acceptance Criteria**:
  - [ ] Paperclip button opens file picker with document types
  - [ ] File chip shows in AttachmentPreview after selection
  - [ ] Upload completes with file_id
  - [ ] Drag-and-drop works on input area
  - [ ] Max 5 attachments enforced
  - [ ] `npm run build` succeeds

  **QA Scenarios**:
  ```
  Scenario: Build succeeds with file upload code
    Tool: Bash
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend && npm run build 2>&1 | tail -5
    Expected Result: Build succeeds
    Evidence: .sisyphus/evidence/task-8-build.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(chat): add file upload and drag-drop to chat input`
  - Files: `src/components/chat/SSEChat.tsx`

- [ ] 9. Web Search Toggle UI in Input Bar

  **What to do**:
  - Import `useWebSearchToggle` hook from `./useWebSearchToggle`
  - Add toggle button in the input bar, positioned before the send button (right side):
    - Icon: `Globe` from lucide-react (or `Search`)
    - Default state: `text-charcoal/30` (muted, inactive)
    - Active state: `text-clay bg-clay/15 border border-clay/30` (highlighted)
    - Transition: `transition-colors`
  - Tooltip text: "Web search" (inactive) / "Web search on" (active) — use `title` attribute
  - When active, show a small pulsing dot indicator next to the icon
  - Include `web_search: true` in the stream body when enabled

  **Must NOT do**:
  - Do NOT create a complex toggle component — keep it as a simple button
  - Do NOT use any switch/toggle library

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 10, 11 — but 11 depends on 9)
  - **Blocks**: Task 11
  - **Blocked By**: Task 4

  **References**:
  **Pattern References**:
  - `src/components/chat/SSEChat.tsx:509-526` — Send/stop button area — toggle goes here, between stop/send buttons and textarea
  - `src/components/chat/InstrumentPanel.tsx:42-48` — Spinner animation pattern for active indicator

  **Icon References**:
  - `Globe` from lucide-react — standard web icon
  - `Search` from lucide-react — alternative

  **Acceptance Criteria**:
  - [ ] Toggle button renders in input bar
  - [ ] Click toggles active/inactive state
  - [ ] Active state has distinct visual appearance
  - [ ] `web_search: true` included in stream body when active
  - [ ] `npm run build` succeeds

  **QA Scenarios**:
  ```
  Scenario: Build succeeds with toggle
    Tool: Bash
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend && npm run build 2>&1 | tail -5
    Expected Result: Build succeeds
    Evidence: .sisyphus/evidence/task-9-build.txt
  ```

  **Commit**: YES (groups with Wave 3)
  - Message: `feat(chat): add web search toggle to chat input bar`
  - Files: `src/components/chat/SSEChat.tsx`

- [ ] 10. Attachment Rendering in MessageList

  **What to do**:
  - In `MessageItem` component (MessageList.tsx), after the message content div and before `MessageActions`:
    - If `msg.attachments` exists and has items, render them
    - For image attachments: Render `<img>` with `max-w-[200px] max-h-[200px] object-cover rounded-lg border border-white/[0.08]` — clickable to open in new tab (`window.open(attachment.url)`)
    - For file attachments: Render file chip `flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/[0.04] text-xs text-charcoal/60` with `FileText` icon, filename, size
  - Image URL: Use `/api/files/{file_id}/content` for the src (this endpoint exists and returns file content)
  - Only render attachments with `file_id` set (uploaded ones, not pending)

  **Must NOT do**:
  - Do NOT modify the React.memo comparator unless needed
  - Do NOT break existing message rendering

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 9, 11 — but 11 depends on 10 completing)
  - **Blocks**: Task 12
  - **Blocked By**: Task 1

  **References**:
  **Pattern References**:
  - `src/components/chat/MessageList.tsx:340-387` — MessageItem rendering — attachment area goes after the content div (line 386) and before the closing `</div>` (line 387)
  - `src/components/chat/MessageList.tsx:342-346` — User/assistant message bubble styling
  - `src/components/chat/MessageList.tsx:401-412` — React.memo comparator — may need to add `attachments` comparison

  **API References**:
  - `GET /api/files/{file_id}/content` — Returns file content as text/plain. For images, need `GET /api/files/{file_id}` to get storage_path, then serve differently. Actually: the content endpoint returns text — for images, use the file metadata to construct a URL that serves the binary.

  **Acceptance Criteria**:
  - [ ] Image attachments render as thumbnails in messages
  - [ ] File attachments render as chips in messages
  - [ ] Only rendered for attachments with file_id
  - [ ] `npm run build` succeeds

  **QA Scenarios**:
  ```
  Scenario: Build succeeds with attachment rendering
    Tool: Bash
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend && npm run build 2>&1 | tail -5
    Expected Result: Build succeeds
    Evidence: .sisyphus/evidence/task-10-build.txt
  ```

  **Commit**: YES (groups with Wave 3)
  - Message: `feat(chat): render attachments in message list`
  - Files: `src/components/chat/MessageList.tsx`

- [ ] 11. SSEChat Input Bar Integration — Wire Everything Together

  **What to do**:
  - This is the integration task that connects all the pieces
  - Update `streamResponse` to include attachments and web_search in the body:
    ```typescript
    const body: Record<string, unknown> = {
      content: prompt,
      model: settings.model,
      system_prompt: settings.systemPrompt,
      temperature: settings.temperature,
      max_tokens: settings.maxTokens,
    };
    // Add attachments with file_ids
    const readyAttachments = attachments.filter(a => a.status === "ready" && a.file_id);
    if (readyAttachments.length > 0) {
      body.attachments = readyAttachments.map(a => ({
        file_id: a.file_id,
        type: a.type,
        filename: a.filename,
        content_type: a.content_type,
        size: a.size,
      }));
    }
    // Add web search flag
    if (webSearchEnabled) {
      body.web_search = true;
    }
    ```
  - After successful send, clear attachments: `setAttachments([])`
  - When stopping, abort any pending uploads via `uploadAbortRef`
  - Ensure input bar layout:
    ```
    [AttachmentPreview (thumbnails/chips)]
    [ImageBtn] [PaperclipBtn] [textarea] [WebSearchToggle] [Send/Stop]
    ```
  - Disable upload buttons when `isStreaming` or `attachments.length >= 5`
  - The upload buttons go inside the flex row, before the textarea

  **Must NOT do**:
  - Do NOT break the existing slash command flow
  - Do NOT modify the mobile companion
  - Do NOT change the stream parsing logic

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential — waits for Wave 2
  - **Blocks**: Tasks 12, 13
  - **Blocked By**: Tasks 7, 8, 9

  **References**:
  **Pattern References**:
  - `src/components/chat/SSEChat.tsx:196-210` — Stream body construction (lines 199-203) — extend with attachments and web_search
  - `src/components/chat/SSEChat.tsx:312-338` — `handleSend` — add attachment clearing after send (after line 318)
  - `src/components/chat/SSEChat.tsx:497-527` — Input layout — restructure to include new buttons

  **Acceptance Criteria**:
  - [ ] Attachments with file_id included in stream body
  - [ ] Web search flag included when toggle is active
  - [ ] Attachments cleared after send
  - [ ] Upload buttons disabled during streaming
  - [ ] Max 5 attachments enforced
  - [ ] Full flow works: upload image → see thumbnail → send → LLM receives it

  **QA Scenarios**:
  ```
  Scenario: Full build succeeds
    Tool: Bash
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend && npm run build 2>&1 | tail -5
    Expected Result: Build succeeds, no errors
    Evidence: .sisyphus/evidence/task-11-build.txt

  Scenario: TypeScript strict check
    Tool: Bash
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend && npx tsc --noEmit 2>&1 | head -20
    Expected Result: No type errors
    Evidence: .sisyphus/evidence/task-11-typecheck.txt
  ```

  **Commit**: YES (groups with Wave 3)
  - Message: `feat(chat): wire attachment upload and web search into chat stream`
  - Files: `src/components/chat/SSEChat.tsx`

- [ ] 12. Edge Cases + Error Handling Polish

  **What to do**:
  - Handle upload failures gracefully: Show error state in AttachmentPreview, allow retry or remove
  - Handle oversized files: Check file size before upload, show toast error if > limit
  - Handle non-image paste: Ignore paste events that don't contain image data
  - Handle abort during upload: Clean up XHR and Object URLs when Stop is clicked
  - Handle empty attachments in stream: Don't send `attachments: []` — only include if non-empty
  - Handle message history fetch: Map backend message format to include `attachments: []` if field missing
  - Handle web search toggle mid-stream: Disable toggle while streaming is active
  - Add proper TypeScript types: No `any`, no `@ts-ignore`

  **Must NOT do**:
  - Do NOT over-engineer retry logic — single retry is fine
  - Do NOT add complex validation beyond size limits

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential — waits for Wave 3
  - **Blocks**: Task 13
  - **Blocked By**: Task 11

  **References**:
  **Pattern References**:
  - `src/components/chat/SSEChat.tsx:397-401` — `handleStop` — add upload abort cleanup here
  - `src/components/chat/SSEChat.tsx:106-137` — History fetch `useEffect` — ensure `attachments` field defaults to `[]`
  - `src/lib/file-api.ts:89-108` — XHR error handling pattern

  **Acceptance Criteria**:
  - [ ] Oversized files rejected before upload with toast message
  - [ ] Upload errors show in preview with remove option
  - [ ] Stop button cleans up pending uploads
  - [ ] No TypeScript errors (`npx tsc --noEmit` passes)
  - [ ] `npm run build` succeeds

  **QA Scenarios**:
  ```
  Scenario: Full build succeeds after polish
    Tool: Bash
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend && npm run build 2>&1 | tail -5
    Expected Result: Build succeeds
    Evidence: .sisyphus/evidence/task-12-build.txt
  ```

  **Commit**: YES (groups with Wave 4)
  - Message: `fix(chat): edge cases and error handling for attachments`
  - Files: `src/components/chat/SSEChat.tsx`, `src/components/chat/AttachmentPreview.tsx`

- [ ] 13. E2E Smoke Test

  **What to do**:
  - Create `e2e/chat-attachments.spec.ts` (following existing E2E patterns in the project)
  - Test scenarios:
    1. Image upload button visible in chat input
    2. File upload button visible in chat input
    3. Web search toggle visible in chat input
    4. Image upload adds thumbnail preview
    5. File upload adds file chip preview
    6. Remove button clears attachment
    7. Web search toggle changes visual state
  - NOTE: Full E2E with actual upload requires authenticated session — keep tests focused on UI visibility and interaction

  **Must NOT do**:
  - Do NOT write integration tests that hit the real backend
  - Do NOT create complex test infrastructure

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential — final task
  - **Blocks**: F1-F4
  - **Blocked By**: Task 12

  **References**:
  **Pattern References**:
  - `e2e/` directory — existing E2E test patterns

  **Acceptance Criteria**:
  - [ ] Test file created
  - [ ] `npx playwright test e2e/chat-attachments.spec.ts` passes (or at least syntax-valid)
  - [ ] `npm run build` succeeds

  **QA Scenarios**:
  ```
  Scenario: Tests are syntactically valid
    Tool: Bash
    Steps:
      1. cd /home/glenn/FlowmannerV2-frontend && npx playwright test --list 2>&1 | grep attachment
    Expected Result: Test file listed without parse errors
    Evidence: .sisyphus/evidence/task-13-test-list.txt
  ```

  **Commit**: YES (groups with Wave 4)
  - Message: `test(chat): add E2E smoke tests for attachment features`
  - Files: `e2e/chat-attachments.spec.ts`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, curl endpoint, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run linter + `npm run build`. Review all changed files for: `as any`/`@ts-ignore`, empty catches, console.log in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names.
  Output: `Build [PASS/FAIL] | Lint [PASS/FAIL] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high` (+ `playwright` skill)
  Start from clean state. Execute EVERY QA scenario from EVERY task. Test cross-feature integration: image + text together, file + web search together, multiple attachments. Test edge cases: empty upload, oversized file, rapid toggle. Save screenshots to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1 — everything in spec was built, nothing beyond spec was built. Check "Must NOT do" compliance. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **Wave 1**: `feat(chat): add attachment types and backend schema for file/image support` — chat-types.ts, AttachmentPreview.tsx, chat.py schema
- **Wave 2**: `feat(chat): implement backend attachment processing and web search injection` — chat_service.py, chat.py routes
- **Wave 3**: `feat(chat): add image/file upload and web search toggle to chat input` — SSEChat.tsx, MessageList.tsx
- **Wave 4**: `fix(chat): edge cases and error handling for attachments` — various
- **Final**: `test(chat): add E2E smoke tests for attachment and web search features` — test files

---

## Success Criteria

### Verification Commands
```bash
cd /home/glenn/FlowmannerV2-frontend && npm run build  # Expected: success, no errors
cd /home/glenn/FlowmannerV2-frontend && npm test        # Expected: all tests pass
curl -X POST http://localhost:8000/api/web-search/health  # Expected: {"status": "ok"}
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All existing chat functionality unchanged (text messages, slash commands, streaming, branching)
- [ ] Backend rebuilds cleanly
- [ ] Frontend builds without errors
