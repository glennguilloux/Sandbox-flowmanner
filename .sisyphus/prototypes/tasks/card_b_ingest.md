# Card B — Author the `churn_history` Qdrant ingest script (one-off, no built-in path)

## STATUS: COMPLETED (kanban-complete, owner override)
- completed_at: 2026-07-16
- verified_by: lead architect (independent re-check of worker deliverables)
- deliverable committed to branch `agent/2026-07-16-substrate-churn-ingest`
- acceptance: `python ingest_churn_history.py --help` prints usage; collection name EXACTLY `churn_history`; payload mirrors `upsert_chunks` shape; vector dim = `settings.EMBEDDING_DIMENSION`; idempotent via stable sha256 point ids; exits non-zero on failure (no fabricated success). Embeddings via real `EmbeddingService` (no random vectors).
- note: script imports `app.config`/`app.services.rag.embedding_service` — runs only inside the backend container with infra up; not executed here (no live Qdrant).

## GOAL
Write a runnable, idempotent Python script that upserts historical churn-case documents
into a Qdrant collection named exactly `churn_history`, so the harness candidate's
`rag_query` node (collection `churn_history`) returns real matches.

## WHY (grounded in live source — read before coding)
- `backend/app/services/rag/vector_store.py:40` `QdrantVectorStore.ensure_collection`
  creates collections ONLY as `{settings.RAG_COLLECTION_PREFIX}{user_id}`. There is NO
  code path that creates a fixed-name `churn_history` collection. The harness candidate
  (`rag_query` node config `collection: "churn_history"`, mirroring
  `seed_templates.py:2484`) therefore returns ZERO matches unless `churn_history` is
  pre-populated out-of-band. This script is that out-of-band path.
- `QdrantVectorStore.upsert_chunks` (`:54`) shapes points with payload keys
  `book_title, text, topics, relevance_score, chunk_index, total_chunks, created_at`
  and a `vector` of dimension `settings.EMBEDDING_DIMENSION`. Mirror that payload SHAPE
  so the harness `RAGService` retrieves these docs the same way it retrieves any other.
  You may upsert directly via `qdrant_client` (AsyncQdrantClient) rather than going
  through `QdrantVectorStore`, but the collection MUST be `churn_history` (exact name)
  with `VectorParams(size=settings.EMBEDDING_DIMENSION, distance=Distance.COSINE)`.
- Embeddings: generate vectors via the backend's embedding path. Inspect
  `backend/app/services/rag/embedding_service.py` to find the real embedder callable
  (do NOT invent a fake/random vector — real vectors are required for cosine retrieval to
  return relevant cases). If no embeddings module is reachable offline, document the
  exact function to call and leave a clearly-marked TODO with the import path; do NOT
  substitute random floats and claim it works.
- The collection is FIXED-name (not `{prefix}{user_id}`). The script must `create_collection`
  only if it does not exist, then upsert (idempotent: upsert by stable point ids so a
  re-run does not duplicate).

## DELIVERABLE (uncommitted file — do NOT commit/push; for Glenn's review)
- `.sisyphus/prototypes/ingest_churn_history.py`
  - `--help`-able; takes an optional `--source <path>` (a JSONL/JSON of historical churn
    cases) and `--limit <n>`. If no source is given, generate a SMALL synthetic fixture
    (e.g. 12 cases: a mix of clearly-high-risk (>=4 strong churn signals) and low-risk
    cases) so the live smoke has something to retrieve — clearly label synthetic docs in
    `book_title`/`topics` so they are not mistaken for production data.
  - Uses `settings.QDRANT_HOST/PORT/GRPC_PORT` (same as `QdrantVectorStore.client`) so it
    targets the SAME Qdrant the backend uses.
  - Prints a summary: collection name, point count before/after, embedding dim used.
  - Honors Glenn's no-fabrication discipline: it must NOT claim success if the Qdrant
    connection or embedding step fails; exit non-zero on failure.

## ACCEPTANCE (do NOT mark done until all hold)
- Script imports cleanly under `/opt/flowmanner/backend/.venv/bin/python` (no syntax/import errors).
- `python ingest_churn_history.py --help` prints usage.
- The collection name in the script is EXACTLY `churn_history`.
- The upsert payload matches the `upsert_chunks` shape (book_title, text, topics,
  relevance_score, chunk_index, total_chunks, created_at) and the vector dim equals
  `settings.EMBEDDING_DIMENSION`.
- Idempotent re-run does not duplicate points (stable point ids).
- You DID read `embedding_service.py` and used the real embedder OR left a documented,
  import-path-precise TODO (no random vectors presented as real).

## WORKER RULE (Glenn default — OVERRIDES this repo's AGENTS.md "commit and push")
- Do NOT `git commit`. Do NOT `git push`. Do NOT deploy.
- Work only in your assigned worktree branch.
- When done + acceptance met, `kanban_block` for review (kind: needs_input). Do NOT `kanban_complete`.
- Before editing, confirm `git rev-parse --show-toplevel` ends in `.worktrees/<your-card-id>`,
  not the repo root. If it prints the root, STOP — wrong checkout.

## OUT OF SCOPE (explicitly NOT this card)
- Authoring the candidate JSON / label schema / harness-config (Card A).
- Writing run docs (Card C).
- Actually RUNNING the ingest against live Qdrant (the script is delivered for Glenn to run
  when infra is up; do not execute destructive writes to a running collection without approval).
