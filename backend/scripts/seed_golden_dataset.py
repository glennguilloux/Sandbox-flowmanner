"""Seed 50 golden test cases across code (20), RAG (15), agent (10), creative (5)."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import AsyncSessionLocal
from app.services.evaluation.dataset_builder import DatasetBuilder

CODE_CASES = [
    {
        "input_prompt": "Write a Python function that checks if a string is a palindrome, ignoring case and non-alphanumeric characters.",
        "expected_behavior": "Function strips non-alphanumeric, lowercases, compares with reversed. Handles empty strings. Returns bool.",
        "task_type": "code_generation",
        "difficulty": "easy",
        "tags": ["python", "strings", "palindrome"],
    },
    {
        "input_prompt": "Implement a LRU cache in Python with get(key) and put(key, value) operations, both O(1) time complexity.",
        "expected_behavior": "Uses OrderedDict or doubly-linked list + hashmap. get evicts nothing, put evicts LRU when capacity exceeded.",
        "task_type": "code_generation",
        "difficulty": "medium",
        "tags": ["python", "data-structures", "cache"],
    },
    {
        "input_prompt": "Write a TypeScript function that deeply flattens a nested array: flatten([1, [2, [3, [4]]]]) => [1, 2, 3, 4].",
        "expected_behavior": "Recursive or iterative approach. Handles arbitrary nesting depth. Preserves element order. Works with mixed types.",
        "task_type": "code_generation",
        "difficulty": "easy",
        "tags": ["typescript", "arrays", "recursion"],
    },
    {
        "input_prompt": "Write a Python async function that fetches multiple URLs concurrently using aiohttp, with a configurable concurrency limit and timeout per request.",
        "expected_behavior": "Uses asyncio.Semaphore for concurrency limit. Per-request timeout via asyncio.wait_for. Returns list of results or errors. Properly closes sessions.",
        "task_type": "code_generation",
        "difficulty": "medium",
        "tags": ["python", "async", "http", "concurrency"],
    },
    {
        "input_prompt": "Implement binary search in Python that works on a rotated sorted array (e.g., [4,5,6,7,0,1,2]).",
        "expected_behavior": "Modified binary search that identifies which half is sorted, then decides which half to search. O(log n) time.",
        "task_type": "code_generation",
        "difficulty": "medium",
        "tags": ["python", "binary-search", "algorithms"],
    },
    {
        "input_prompt": "Write a Python function to serialize and deserialize a binary tree to/from a string using level-order traversal.",
        "expected_behavior": "Serialize: level-order with null markers. Deserialize: reconstruct tree from level-order string. Handles empty trees.",
        "task_type": "code_generation",
        "difficulty": "medium",
        "tags": ["python", "trees", "serialization"],
    },
    {
        "input_prompt": "Create a Python decorator that rate-limits function calls to N per time window, using a sliding window algorithm.",
        "expected_behavior": "Tracks timestamps of calls. Rejects (raises or waits) if limit exceeded. Thread-safe. Configurable window and limit.",
        "task_type": "code_generation",
        "difficulty": "hard",
        "tags": ["python", "decorators", "rate-limiting"],
    },
    {
        "input_prompt": "Write a SQL query to find the second highest salary from an Employee table. Handle ties and missing data.",
        "expected_behavior": "Uses DISTINCT + ORDER BY + LIMIT, or subquery with MAX. Returns NULL or empty if fewer than 2 distinct salaries.",
        "task_type": "code_generation",
        "difficulty": "easy",
        "tags": ["sql", "queries"],
    },
    {
        "input_prompt": "Implement a trie (prefix tree) in Python with insert, search, and startsWith methods.",
        "expected_behavior": "Node class with children dict and is_end flag. Insert adds characters, search checks full word, startsWith checks prefix existence.",
        "task_type": "code_generation",
        "difficulty": "medium",
        "tags": ["python", "trie", "data-structures"],
    },
    {
        "input_prompt": "Write a Python function that merges k sorted lists into one sorted list efficiently.",
        "expected_behavior": "Uses min-heap (heapq). O(N log k) time where N is total elements. Handles empty lists. Returns new sorted list.",
        "task_type": "code_generation",
        "difficulty": "hard",
        "tags": ["python", "heap", "sorting", "algorithms"],
    },
    {
        "input_prompt": "Create a React custom hook useDebounce that delays updating a value until after a specified delay of inactivity.",
        "expected_behavior": "Returns debounced value. Uses useState + useEffect with cleanup. Configurable delay. Cancels previous timeout on value change.",
        "task_type": "code_generation",
        "difficulty": "easy",
        "tags": ["react", "hooks", "debounce"],
    },
    {
        "input_prompt": "Write a Python context manager that measures and logs the execution time of a code block.",
        "expected_behavior": "Uses __enter__/__exit__ or contextmanager decorator. Measures wall clock time. Logs via logging module. Handles exceptions.",
        "task_type": "code_generation",
        "difficulty": "easy",
        "tags": ["python", "context-managers", "timing"],
    },
    {
        "input_prompt": "Implement a Python function that detects cycles in a directed graph using DFS with three-color marking.",
        "expected_behavior": "White/gray/black coloring. DFS from each unvisited node. Gray→gray edge = cycle. Returns bool and optionally the cycle path.",
        "task_type": "code_generation",
        "difficulty": "medium",
        "tags": ["python", "graphs", "dfs", "cycle-detection"],
    },
    {
        "input_prompt": "Write a TypeScript generic function groupBy<T>(arr: T[], keyFn: (item: T) => string): Record<string, T[]> that groups array elements by a key.",
        "expected_behavior": "Generic typed function. Uses reduce or forEach. Returns object with string keys mapping to arrays. Preserves element types.",
        "task_type": "code_generation",
        "difficulty": "easy",
        "tags": ["typescript", "generics", "arrays"],
    },
    {
        "input_prompt": "Write a Python function to solve the N-Queens problem and return all valid board configurations.",
        "expected_behavior": "Backtracking approach. Checks column and diagonal conflicts. Returns list of solutions (each as list of column positions per row).",
        "task_type": "code_generation",
        "difficulty": "hard",
        "tags": ["python", "backtracking", "n-queens"],
    },
    {
        "input_prompt": "Create a Python class implementing a thread-safe producer-consumer queue using threading primitives.",
        "expected_behavior": "Uses threading.Condition or Queue. put() blocks when full, get() blocks when empty. Supports timeout. shutdown() method.",
        "task_type": "code_generation",
        "difficulty": "medium",
        "tags": ["python", "threading", "producer-consumer"],
    },
    {
        "input_prompt": "Write a SQL query using window functions to calculate a running total of sales by date.",
        "expected_behavior": "Uses SUM() OVER (ORDER BY date ROWS UNBOUNDED PRECEDING). Handles nulls. Returns date, amount, running_total columns.",
        "task_type": "code_generation",
        "difficulty": "medium",
        "tags": ["sql", "window-functions"],
    },
    {
        "input_prompt": "Implement a Python function that performs topological sort on a DAG using Kahn's algorithm (BFS-based).",
        "expected_behavior": "Computes in-degrees. BFS from zero-indegree nodes. Detects cycles (if result length < node count). Returns ordered list.",
        "task_type": "code_generation",
        "difficulty": "medium",
        "tags": ["python", "topological-sort", "graphs"],
    },
    {
        "input_prompt": "Write a Python function that implements the Levenshtein edit distance between two strings with dynamic programming.",
        "expected_behavior": "2D DP table. Operations: insert, delete, substitute (cost 1 each). Returns minimum edit distance. O(mn) time and space.",
        "task_type": "code_generation",
        "difficulty": "medium",
        "tags": ["python", "dynamic-programming", "strings"],
    },
    {
        "input_prompt": "Create a Python function retry(max_attempts=3, backoff_factor=2, exceptions=(Exception,)) decorator that retries failed function calls with exponential backoff.",
        "expected_behavior": "Retries up to max_attempts. Sleeps backoff_factor^attempt seconds between retries. Only catches specified exceptions. Re-raises on final failure.",
        "task_type": "code_generation",
        "difficulty": "medium",
        "tags": ["python", "decorators", "retry", "resilience"],
    },
]

RAG_CASES = [
    {
        "input_prompt": "Based on the following context, what is the maximum number of workers recommended for the FastAPI backend?\n\nContext: The Flowmanner backend uses uvicorn with 4 workers. Each worker consumes approximately 500MB of RAM. The homelab server has 32GB of total RAM, with 16GB allocated to PostgreSQL and Redis combined.",
        "expected_behavior": "Correctly identifies 4 workers from context. Calculates theoretical max (~8 workers with remaining RAM) but recommends the configured 4. Notes memory constraints.",
        "task_type": "rag_accuracy",
        "difficulty": "easy",
        "tags": ["infrastructure", "capacity-planning"],
    },
    {
        "input_prompt": "According to the documentation, what authentication methods does Flowmanner support?\n\nContext: Flowmanner uses NextAuth v5 with GitHub OAuth and credentials provider. The backend issues JWT tokens. 2FA is supported via TOTP. OIDC providers can be configured by admins.",
        "expected_behavior": "Lists: GitHub OAuth, credentials (email/password), TOTP 2FA, OIDC. Does not invent SAML or other unmentioned methods.",
        "task_type": "rag_accuracy",
        "difficulty": "easy",
        "tags": ["auth", "security"],
    },
    {
        "input_prompt": "What is the WireGuard tunnel configuration between the homelab and VPS?\n\nContext: WireGuard connects homelab (10.99.0.3) to VPS (10.99.0.1). The tunnel allows the VPS nginx to proxy /api/* requests to the backend on port 8000. Config is at /etc/wireguard/wg0.conf.",
        "expected_behavior": "States homelab is 10.99.0.3, VPS is 10.99.0.1. Nginx proxies through tunnel to backend:8000. Config path correct. Does not invent IPs or ports.",
        "task_type": "rag_accuracy",
        "difficulty": "medium",
        "tags": ["networking", "wireguard"],
    },
    {
        "input_prompt": "How does the Celery task system handle failures in Flowmanner?\n\nContext: Celery tasks use exponential backoff with max 5 retries. The idempotency middleware prevents duplicate task execution. Failed tasks are logged to PostgreSQL. The rabbitMQ dead letter queue captures permanently failed messages.",
        "expected_behavior": "Describes: exponential backoff, 5 max retries, idempotency middleware, PostgreSQL logging, DLQ. Does not add unmentioned mechanisms.",
        "task_type": "rag_accuracy",
        "difficulty": "medium",
        "tags": ["celery", "resilience"],
    },
    {
        "input_prompt": "What monitoring and observability tools are integrated into the Flowmanner stack?\n\nContext: The stack includes Jaeger for distributed tracing, Prometheus for metrics (33 custom metrics), Langfuse for LLM observability, Sentry for error tracking, and 4 circuit breakers for external service calls.",
        "expected_behavior": "Lists: Jaeger, Prometheus (33 metrics), Langfuse, Sentry, circuit breakers (4). Mentions these are integrated, not standalone.",
        "task_type": "rag_accuracy",
        "difficulty": "easy",
        "tags": ["observability", "monitoring"],
    },
    {
        "input_prompt": "What is the deployment process for frontend changes in Flowmanner?\n\nContext: Frontend source lives on the homelab at /home/glenn/FlowmannerV2-frontend/. Changes are rsync'd to the VPS at /opt/flowmanner/frontend/. The VPS runs docker compose build frontend && docker compose up -d --no-deps frontend. Nginx is then restarted.",
        "expected_behavior": "Describes: edit on homelab, rsync to VPS, docker compose build + up, nginx restart. Mentions deploy-frontend.sh script. Correct paths.",
        "task_type": "rag_accuracy",
        "difficulty": "medium",
        "tags": ["deployment", "frontend"],
    },
    {
        "input_prompt": "What database tables store the mission execution data?\n\nContext: Missions are stored in the missions table with fields for status, plan, results, cost, and tokens_used. Mission tasks are in mission_tasks with dependencies, retry_count, and output_data. Mission logs are in mission_logs with level and data fields.",
        "expected_behavior": "Lists: missions (status, plan, results, cost, tokens_used), mission_tasks (dependencies, retry_count, output_data), mission_logs (level, data). Correct table and field names.",
        "task_type": "rag_accuracy",
        "difficulty": "medium",
        "tags": ["database", "missions"],
    },
    {
        "input_prompt": "How does the rate limiting system work in Flowmanner?\n\nContext: Per-endpoint rate limiting uses Redis sliding window. There are 8 rate limit categories. Limits are tier-aware (free, pro, enterprise tiers have different limits). Rate limit headers (X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset) are returned on every response.",
        "expected_behavior": "Describes: Redis sliding window, 8 categories, tier-aware, rate limit headers. Does not invent categories or limits not mentioned.",
        "task_type": "rag_accuracy",
        "difficulty": "medium",
        "tags": ["rate-limiting", "redis"],
    },
    {
        "input_prompt": "What is the llama.cpp server configuration in the homelab?\n\nContext: llama.cpp runs as a bare metal systemd service on port 11434. It uses 2x RTX 5060 Ti GPUs (16GB each, ~32GB total VRAM). The active model is ThinkingCap-Qwen3.6-27B-Q6_K-MTP.gguf with MTP (multi-token prediction) enabled, achieving ~38 tok/s.",
        "expected_behavior": "States: systemd service, port 11434, 2x RTX 5060 Ti, ThinkingCap-Qwen3.6-27B, MTP enabled, ~38 tok/s. Correct model name and performance.",
        "task_type": "rag_accuracy",
        "difficulty": "medium",
        "tags": ["llm", "llama.cpp", "gpu"],
    },
    {
        "input_prompt": "What Pydantic validation patterns are used in the Flowmanner backend?\n\nContext: The backend uses Pydantic v2 with model_validator for cross-field validation. JSONB columns store Pydantic model output via .model_dump(). Input validation happens at API boundaries using request models. Field constraints use Field(ge=0, le=2.0) for numeric ranges.",
        "expected_behavior": "Describes: Pydantic v2, model_validator, .model_dump() for JSONB, Field constraints. Notes validation at API boundaries.",
        "task_type": "rag_accuracy",
        "difficulty": "medium",
        "tags": ["pydantic", "validation"],
    },
    {
        "input_prompt": "How does the WebSocket system work for real-time mission updates?\n\nContext: Socket.IO is used for WebSocket connections. The mission_ws module handles mission-specific events. Clients subscribe to mission_id channels. Updates are broadcast when mission status changes or tasks complete.",
        "expected_behavior": "Describes: Socket.IO, mission_ws module, mission_id subscriptions, status/task broadcasts. Does not invent event names.",
        "task_type": "rag_accuracy",
        "difficulty": "easy",
        "tags": ["websocket", "real-time"],
    },
    {
        "input_prompt": "What is the caching strategy in Flowmanner?\n\nContext: The system uses an in-process cache layer for frequently accessed data. Redis is used for distributed caching. Cache invalidation happens on write operations. The caching layer is transparent to service code via decorators.",
        "expected_behavior": "Describes: in-process cache + Redis, decorator-based, invalidation on writes. Two-layer caching.",
        "task_type": "rag_accuracy",
        "difficulty": "easy",
        "tags": ["caching", "redis"],
    },
    {
        "input_prompt": "What security middleware is applied to the FastAPI application?\n\nContext: The middleware stack includes: CORS, SecurityHeaders, Audit, Metrics, EndpointRateLimit, Idempotency, and APIVersioning. Middleware is applied in reverse order of declaration (last declared = first executed). Security headers include CSP, X-Frame-Options, etc.",
        "expected_behavior": "Lists all 7 middleware. Notes reverse application order. Mentions specific security headers. Does not add unmentioned middleware.",
        "task_type": "rag_accuracy",
        "difficulty": "hard",
        "tags": ["security", "middleware"],
    },
    {
        "input_prompt": "How does the data export/GDPR compliance feature work?\n\nContext: Users can export all their data via /api/data-export. The export includes missions, chat history, settings, and analytics. Export format is JSON. Data is generated on-demand and available for download for 24 hours.",
        "expected_behavior": "Describes: /api/data-export, includes missions/chat/settings/analytics, JSON format, 24-hour availability. Does not add unmentioned data types.",
        "task_type": "rag_accuracy",
        "difficulty": "easy",
        "tags": ["gdpr", "data-export"],
    },
    {
        "input_prompt": "What is the Docker architecture for the homelab services?\n\nContext: All services run in Docker containers on a custom bridge network (10.0.4.0/24). Backend is 10.0.4.6, PostgreSQL is 10.0.4.2, Redis is 10.0.4.5, Qdrant is 10.0.4.3. The backend image is workflows-backend:restored and is rebuilt (not volume-mounted) for code changes.",
        "expected_behavior": "Correct IPs for each service. Custom bridge network. Backend image rebuilt, not volume-mounted. Named volumes for data persistence.",
        "task_type": "rag_accuracy",
        "difficulty": "medium",
        "tags": ["docker", "infrastructure"],
    },
]

AGENT_CASES = [
    {
        "input_prompt": "A user reports that their mission completed in 28ms with 0 tokens used and empty output. Diagnose the root cause.",
        "expected_behavior": "Identifies model routing failure (ModelRouter._is_model_available fails without user_id). Notes mission_executor swallows errors. Suggests checking model configuration and BYOK path.",
        "task_type": "agent_reasoning",
        "difficulty": "hard",
        "tags": ["debugging", "missions", "model-routing"],
    },
    {
        "input_prompt": "The frontend shows infinite loading after login. Backend logs show repeated 401 errors. What is happening?",
        "expected_behavior": "Identifies auth retry storm: auth-store retries on 401 causing infinite loop. Notes difference between 401 (invalid token) vs network errors. Suggests breaking retry loop on 401, only retrying network errors.",
        "task_type": "agent_reasoning",
        "difficulty": "medium",
        "tags": ["debugging", "auth", "frontend"],
    },
    {
        "input_prompt": "A SQLAlchemy query returns data but Pydantic .from_orm() raises AttributeError on 'metadata'. What went wrong?",
        "expected_behavior": "Identifies 'metadata' is reserved by SQLAlchemy (MetaData). Column mapped to different Python attribute name. Suggests checking __mapper__ or renaming column/attribute.",
        "task_type": "agent_reasoning",
        "difficulty": "medium",
        "tags": ["debugging", "sqlalchemy", "pydantic"],
    },
    {
        "input_prompt": "Docker compose build returns 'no service selected' for the backend. The compose file has a backend service. Why?",
        "expected_behavior": "Identifies backend service uses 'image:' not 'build:' section. docker compose build is a no-op. Must use docker build -t workflows-backend:restored /opt/flowmanner/backend/ directly.",
        "task_type": "agent_reasoning",
        "difficulty": "easy",
        "tags": ["debugging", "docker"],
    },
    {
        "input_prompt": "After deploying to VPS, the API returns 404 for /api/evaluation/datasets. The router is registered in __init__.py. What's wrong?",
        "expected_behavior": "Checks: router prefix collision, _safe_import failure (import error silently skips), double-prefix (router prefix + name registration). Suggests checking docker logs for import warnings.",
        "task_type": "agent_reasoning",
        "difficulty": "medium",
        "tags": ["debugging", "api", "routing"],
    },
    {
        "input_prompt": "Celery workers crash on startup with 'module not found' errors. The tasks module exists and works locally.",
        "expected_behavior": "Identifies autodiscover_tasks crash: any broken module in autodiscovery list kills the worker. Suggests checking ALL modules in autodiscover list, not just the one being added.",
        "task_type": "agent_reasoning",
        "difficulty": "medium",
        "tags": ["debugging", "celery"],
    },
    {
        "input_prompt": "Prometheus metrics endpoint shows duplicate time series errors after uvicorn restart. How to fix?",
        "expected_behavior": "Identifies Prometheus multi-worker duplication: metrics defined in __init__ get re-registered on fork. Fix: define metrics at module level, not in __init__.",
        "task_type": "agent_reasoning",
        "difficulty": "hard",
        "tags": ["debugging", "prometheus", "metrics"],
    },
    {
        "input_prompt": "The LLM judge returns scores of 0.0 for all test cases. The API key is valid and the model responds correctly in chat. What's happening?",
        "expected_behavior": "Checks: LLM judge JSON parsing failure (markdown fences in response), wrong API base URL, model name format (needs provider/ prefix). Suggests checking raw judge response.",
        "task_type": "agent_reasoning",
        "difficulty": "medium",
        "tags": ["debugging", "evaluation", "llm"],
    },
    {
        "input_prompt": "After a bulk rename of an import, some files still reference the old name and crash on import. The rename was done with replace_all. Why were some missed?",
        "expected_behavior": "Identifies: replace_all only matches exact strings. Fallback defaults in adjacent modules, string references, and comments may use the old name differently. Suggests grep for old value after bulk replace.",
        "task_type": "agent_reasoning",
        "difficulty": "easy",
        "tags": ["debugging", "refactoring"],
    },
    {
        "input_prompt": "The frontend deploy script rsyncs files but the VPS still serves old code. The container was restarted.",
        "expected_behavior": "Identifies: Next.js standalone build caches in .next/. Need to rebuild (docker compose build frontend) not just restart. Docker layer caching may serve stale build. Suggests force-recreate.",
        "task_type": "agent_reasoning",
        "difficulty": "medium",
        "tags": ["debugging", "deployment", "frontend"],
    },
]

CREATIVE_CASES = [
    {
        "input_prompt": "Write a concise, professional error message for a user whose mission failed due to exceeding the token budget limit.",
        "expected_behavior": "Professional, non-technical tone. States what happened (token budget exceeded), suggests action (reduce scope or upgrade tier). No blame, no jargon.",
        "task_type": "creative",
        "difficulty": "easy",
        "tags": ["ux-writing", "error-messages"],
    },
    {
        "input_prompt": "Draft a 3-sentence onboarding welcome message for new Flowmanner users that conveys the product's value proposition.",
        "expected_behavior": "Conveys: AI workflow automation, ease of use, team collaboration. Professional but approachable tone. No buzzwords or hyperbole.",
        "task_type": "creative",
        "difficulty": "medium",
        "tags": ["copywriting", "onboarding"],
    },
    {
        "input_prompt": "Write a changelog entry for the new LLM evaluation feature. Keep it under 100 words.",
        "expected_behavior": "Describes: golden datasets, automated evaluation, model comparison. Uses present tense. Highlights user benefit. Follows keepachangelog format.",
        "task_type": "creative",
        "difficulty": "easy",
        "tags": ["changelog", "documentation"],
    },
    {
        "input_prompt": "Create a README section explaining how to contribute a new golden test case to the evaluation dataset. Target audience: developers familiar with Python.",
        "expected_behavior": "Shows: file location, schema format, example test case, how to run evaluation. Code examples in Python. Clear steps.",
        "task_type": "creative",
        "difficulty": "medium",
        "tags": ["documentation", "contributing"],
    },
    {
        "input_prompt": "Write a comparison table (markdown) highlighting Flowmanner's evaluation system vs manual prompt testing, covering: consistency, speed, reproducibility, and coverage.",
        "expected_behavior": "4-column markdown table. Honest trade-offs (manual has intuition advantage). Flowmanner wins on consistency/speed/reproducibility. Coverage is comparable.",
        "task_type": "creative",
        "difficulty": "medium",
        "tags": ["documentation", "comparison"],
    },
]


async def seed():
    async with AsyncSessionLocal() as db:
        builder = DatasetBuilder(db)

        # Create datasets
        code_ds = await builder.create_dataset(
            name="Code Generation Golden Set",
            category="code",
            description="20 test cases for code generation quality evaluation",
        )
        rag_ds = await builder.create_dataset(
            name="RAG Accuracy Golden Set",
            category="rag",
            description="15 test cases for retrieval-augmented generation accuracy",
        )
        agent_ds = await builder.create_dataset(
            name="Agent Reasoning Golden Set",
            category="agent",
            description="10 test cases for agent debugging and reasoning capability",
        )
        creative_ds = await builder.create_dataset(
            name="Creative Tasks Golden Set",
            category="creative",
            description="5 test cases for creative writing and communication quality",
        )

        # Seed test cases
        await builder.add_test_cases_bulk(code_ds.id, CODE_CASES)
        await builder.add_test_cases_bulk(rag_ds.id, RAG_CASES)
        await builder.add_test_cases_bulk(agent_ds.id, AGENT_CASES)
        await builder.add_test_cases_bulk(creative_ds.id, CREATIVE_CASES)

        await db.commit()

        total = len(CODE_CASES) + len(RAG_CASES) + len(AGENT_CASES) + len(CREATIVE_CASES)
        print(f"Seeded {total} golden test cases across 4 datasets:")
        print(f"  - Code: {len(CODE_CASES)} cases ({code_ds.id})")
        print(f"  - RAG:  {len(RAG_CASES)} cases ({rag_ds.id})")
        print(f"  - Agent: {len(AGENT_CASES)} cases ({agent_ds.id})")
        print(f"  - Creative: {len(CREATIVE_CASES)} cases ({creative_ds.id})")


if __name__ == "__main__":
    asyncio.run(seed())
