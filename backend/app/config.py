from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SECRETS = {"change-me-in-production", "changeme", "secret", "password"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = "development"
    APP_NAME: str = "workflows-backend"
    SECRET_KEY: str = "change-me-in-production"

    DATABASE_URL: str = "postgresql+asyncpg://flowmanner:flowmanner_dev_password@localhost:5432/flowmanner"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_TIMEOUT: int = 10
    DATABASE_POOL_RECYCLE: int = 1800
    DATABASE_STATEMENT_TIMEOUT_MS: int = 15000
    DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MS: int = 300000
    DATABASE_CONNECT_TIMEOUT: int = 10
    DB_ECHO: bool = False

    REDIS_URL: str = "redis://localhost:6379/0"

    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ACCESS_TOKEN_EXPIRES: int = 900
    JWT_REFRESH_TOKEN_EXPIRES: int = 604800

    AES_ENCRYPTION_KEY: str = "change-me-in-production"

    LLAMACPP_URL: str = "http://10.0.4.1:11434"
    LLAMACPP_LIGHT_URL: str = "http://10.0.4.1:11435"
    LITELLM_ENDPOINT: str = "http://localhost:4000"

    # Comma-separated CIDR/IP list of PROXY hops we trust to provide a truthful
    # X-Forwarded-For client IP. Only when the immediate TCP peer is in this
    # set do we honor XFF for rate-limit client-IP resolution. Covers the
    # homelab topology: VPS Nginx (public) -> WireGuard (10.99.0.0/16) ->
    # homelab backend, plus localhost / Docker bridge / link-local.
    RATE_LIMIT_TRUSTED_PROXIES: str = "127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,169.254.0.0/16"

    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION_NAME: str = "workflows_docs"

    # RAG Prompt Engineer settings
    QDRANT_HOST: str = "10.0.4.3"
    QDRANT_PORT: int = 6333
    QDRANT_GRPC_PORT: int = 6334
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    RAG_COLLECTION_PREFIX: str = "book_notes_"

    CHROMA_PERSIST_DIR: str = "./chroma_db"

    DEFAULT_LOCAL_MODEL: str = "Qwen3.6-27B-Q5_K_M-mtp.gguf"
    DEFAULT_CLOUD_MODEL: str = "deepseek/deepseek-v4-flash"

    LLM_MODEL_NAME: str = "deepseek/deepseek-v4-flash"
    LLM_API_BASE: str = "https://api.deepseek.com/v1"
    LLM_API_KEY: str = ""

    RAG_CHUNK_SIZE: int = 1000
    RAG_CHUNK_OVERLAP: int = 200
    RAG_EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    RAG_SIMILARITY_THRESHOLD: float = 0.7

    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,https://workflows.glennguilloux.com,https://www.workflows.glennguilloux.com,https://flowmanner.com,https://www.flowmanner.com"

    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    LANGFUSE_ENABLED: bool = False  # Glenn: "I am not using Langfuse" — disabled 2026-07-03
    LANGFUSE_SAMPLING_RATE: float = 0.1
    LANGFUSE_FLUSH_INTERVAL: int = 30

    ENABLE_COST_TRACKING: bool = True
    BUDGET_LIMIT_MONTHLY_USD: float = 100.0

    # Sentry error tracking
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = "production"
    SENTRY_TRACES_SAMPLE_RATE: float = 1.0
    SENTRY_PROFILES_SAMPLE_RATE: float = 0.1
    SENTRY_ORG_SLUG: str = ""
    SENTRY_PROJECT_SLUG: str = ""
    SENTRY_API_TOKEN: str = ""

    # Linear integration
    LINEAR_API_KEY: str = ""
    LINEAR_WEBHOOK_SECRET: str = ""
    LINEAR_TEAM_ID: str = ""
    LINEAR_OAUTH_CLIENT_ID: str = ""
    LINEAR_OAUTH_CLIENT_SECRET: str = ""

    # Sentry user-facing integration (separate from internal SDK monitoring)
    SENTRY_WEBHOOK_SECRET: str = ""
    SENTRY_USER_OAUTH_CLIENT_ID: str = ""
    SENTRY_USER_OAUTH_CLIENT_SECRET: str = ""

    # Vercel integration
    VERCEL_OAUTH_CLIENT_ID: str = ""
    VERCEL_OAUTH_CLIENT_SECRET: str = ""
    VERCEL_WEBHOOK_SECRET: str = ""

    # Jira integration
    JIRA_OAUTH_CLIENT_ID: str = ""
    JIRA_OAUTH_CLIENT_SECRET: str = ""
    JIRA_WEBHOOK_SECRET: str = ""

    # Confluence integration
    CONFLUENCE_OAUTH_CLIENT_ID: str = ""
    CONFLUENCE_OAUTH_CLIENT_SECRET: str = ""
    CONFLUENCE_WEBHOOK_SECRET: str = ""

    # Figma integration
    FIGMA_OAUTH_CLIENT_ID: str = ""
    FIGMA_OAUTH_CLIENT_SECRET: str = ""
    FIGMA_WEBHOOK_SECRET: str = ""

    # Stripe integration
    STRIPE_OAUTH_CLIENT_ID: str = ""  # Platform client_id (ca_...)
    STRIPE_OAUTH_CLIENT_SECRET: str = ""  # Platform secret key (sk_...)
    STRIPE_WEBHOOK_SECRET: str = ""  # Webhook endpoint signing secret (whsec_...)

    # PagerDuty integration
    PAGERDUTY_OAUTH_CLIENT_ID: str = ""
    PAGERDUTY_OAUTH_CLIENT_SECRET: str = ""
    PAGERDUTY_WEBHOOK_SECRET: str = ""

    # Datadog integration
    DATADOG_OAUTH_CLIENT_ID: str = ""
    DATADOG_OAUTH_CLIENT_SECRET: str = ""
    DATADOG_WEBHOOK_SECRET: str = ""

    # Airtable integration
    AIRTABLE_OAUTH_CLIENT_ID: str = ""
    AIRTABLE_OAUTH_CLIENT_SECRET: str = ""
    AIRTABLE_WEBHOOK_SECRET: str = ""

    # Intercom integration
    INTERCOM_OAUTH_CLIENT_ID: str = ""
    INTERCOM_OAUTH_CLIENT_SECRET: str = ""
    INTERCOM_WEBHOOK_SECRET: str = ""

    # Asana integration
    ASANA_OAUTH_CLIENT_ID: str = ""
    ASANA_OAUTH_CLIENT_SECRET: str = ""
    ASANA_WEBHOOK_SECRET: str = ""

    # GitLab integration
    GITLAB_OAUTH_CLIENT_ID: str = ""
    GITLAB_OAUTH_CLIENT_SECRET: str = ""
    GITLAB_WEBHOOK_SECRET: str = ""

    # ClickUp integration
    CLICKUP_OAUTH_CLIENT_ID: str = ""
    CLICKUP_OAUTH_CLIENT_SECRET: str = ""
    CLICKUP_WEBHOOK_SECRET: str = ""

    # HubSpot integration
    HUBSPOT_OAUTH_CLIENT_ID: str = ""
    HUBSPOT_OAUTH_CLIENT_SECRET: str = ""
    HUBSPOT_WEBHOOK_SECRET: str = ""

    # Twilio integration
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_API_KEY_SID: str = ""
    TWILIO_API_KEY_SECRET: str = ""
    TWILIO_WEBHOOK_SECRET: str = ""

    # Shopify integration
    SHOPIFY_OAUTH_CLIENT_ID: str = ""
    SHOPIFY_OAUTH_CLIENT_SECRET: str = ""
    SHOPIFY_WEBHOOK_SECRET: str = ""

    # Zendesk integration
    ZENDESK_OAUTH_CLIENT_ID: str = ""
    ZENDESK_OAUTH_CLIENT_SECRET: str = ""
    ZENDESK_WEBHOOK_SECRET: str = ""

    # Monday.com integration
    MONDAY_OAUTH_CLIENT_ID: str = ""
    MONDAY_OAUTH_CLIENT_SECRET: str = ""
    MONDAY_WEBHOOK_SECRET: str = ""

    # GitHub integration
    GITHUB_OAUTH_CLIENT_ID: str = ""
    GITHUB_OAUTH_CLIENT_SECRET: str = ""
    GITHUB_WEBHOOK_SECRET: str = ""

    # Slack integration
    SLACK_OAUTH_CLIENT_ID: str = ""
    SLACK_OAUTH_CLIENT_SECRET: str = ""
    SLACK_SIGNING_SECRET: str = ""

    # Telegram integration
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""

    # Event bus failure alerting (Slack + PagerDuty)
    SLACK_ALERT_WEBHOOK_URL: str = ""  # Slack incoming webhook URL for failure alerts
    PAGERDUTY_ALERT_ROUTING_KEY: str = ""  # PagerDuty Events API v2 routing key for failure alerts

    # Discord integration
    DISCORD_BOT_TOKEN: str = ""

    # Web Push (VAPID) — auto-generated if empty
    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_CLAIM_EMAIL: str = "admin@flowmanner.com"

    # Email delivery (Resend API preferred, SMTP fallback)
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "noreply@flowmanner.com"
    EMAIL_FROM_NAME: str = "Flowmanner"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""

    # Auth v3 — httpOnly cookie configuration
    AUTH_V3_COOKIE_DOMAIN: str = ""  # e.g. ".flowmanner.com" — empty = same-origin only
    AUTH_V3_COOKIE_SECURE: bool = True  # True in production (HTTPS only), False for localhost dev
    AUTH_V3_REFRESH_EXPIRY_DAYS: int = 30

    # PayPal subscription billing
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_CLIENT_SECRET: str = ""
    PAYPAL_MODE: str = "sandbox"  # "sandbox" or "live"
    PAYPAL_WEBHOOK_ID: str = ""  # Set to PayPal webhook ID for signature verification

    # Mission executor resource limits
    MISSION_RESOURCE_CPU_SECONDS: int = 60
    MISSION_RESOURCE_MEMORY_MB: int = 512
    MISSION_RESOURCE_FILE_SIZE_MB: int = 10
    # Mission executor LLM defaults
    MISSION_PLAN_TEMPERATURE: float = 0.7
    MISSION_PLAN_MAX_TOKENS: int = 2000
    MISSION_DEFAULT_MAX_RETRIES: int = 3
    MISSION_LLM_REQUEST_TIMEOUT: float = 60.0
    # Mission rate limits (v2 per-user)
    MISSION_RATE_LIMIT_CREATE: int = 30
    MISSION_RATE_LIMIT_UPDATE: int = 30
    MISSION_RATE_LIMIT_DELETE: int = 15
    MISSION_RATE_LIMIT_EXECUTE: int = 20
    MISSION_RATE_LIMIT_ABORT: int = 15
    MISSION_RATE_LIMIT_PLAN: int = 20
    # Pause-timeout auto-fail window (days). A mission paused longer than this
    # is auto-transitioned PAUSED -> FAILED and compensation is run. See
    # app/tasks/expire_paused_missions.py. Historical rows with paused_at = NULL
    # are treated as infinity and exempt.
    MISSION_PAUSE_AUTO_FAIL_DAYS: int = 7
    MISSION_RATE_LIMIT_DEFAULT: int = 60
    MISSION_RATE_LIMIT_WINDOW_SECONDS: int = 60
    MISSION_RATE_LIMIT_BURST_MULTIPLIER: int = 2

    # Mission cache TTLs (seconds)
    MISSION_CACHE_LIST_TTL: int = 30
    MISSION_CACHE_GET_TTL: int = 60
    MISSION_CACHE_ACTIVE_TTL: int = 15

    # Mission executor misc
    MISSION_RAG_RESULTS_LIMIT: int = 5
    MISSION_LEARNING_PATTERNS_LIMIT: int = 3
    MISSION_MAX_ITERATION_MULTIPLIER: int = 3
    MISSION_REPORT_JSON_SLICE_LIMIT: int = 5000
    MISSION_COST_DIVISOR: int = 1_000_000
    MISSION_DEFAULT_SCROLL_X: int = 0
    MISSION_DEFAULT_SCROLL_Y: int = 300

    # sandboxd integration
    SANDBOXD_API_URL: str = "http://127.0.0.1:9090"
    SANDBOXD_AUTH_TOKEN: str = ""
    SANDBOXD_PREVIEW_DOMAIN: str = "preview.flowmanner.com"
    SANDBOXD_PREVIEW_PORT: int = 8081
    SANDBOXD_ENABLED: bool = True
    SANDBOXD_DEFAULT_TEMPLATE: str = "python"

    # Chat tool-calling limits
    CHAT_MAX_TOOL_ROUNDS: int = 15

    # T33 — Inline memory citations in chat.
    # Stage 0 = False (no behavior change). Stage 1+ flips to True to enable
    # the pre-LLM memory recall path in chat_service.stream_message_to_llm.
    # Per-tenant or per-user override is intentionally NOT in scope for T33.
    CHAT_MEMORY_CITATIONS_ENABLED: bool = False

    # Q2-C — Token budget for the personal-memory block injected into the
    # LLM prompt. Independent of CHAT_CONTEXT_TOKEN_BUDGET (which bounds the
    # *conversation* history pruning) so tuning message pruning never starves
    # memory. The resolved claim set (E23-B ranked + Tier-0 constraints
    # protected) is dropped lowest-rank-first when it would exceed this.
    # 0 disables memory injection entirely (selects nothing).
    CHAT_MEMORY_INJECTION_TOKEN_BUDGET: int = 600

    # SPIKE (ADR-002): ordered prepareStep injection closure for chat.
    # When True, chat context injection (memory + web_search) is routed through
    # ``_prepare_step_inject`` instead of the legacy inline path, and an
    # ``injected`` SSE receipt event is emitted per source. Defaults False so
    # single-shot chat behavior is unchanged until agentic/multi-step chat lands.
    CHAT_PREPARE_STEP_HOOK_ENABLED: bool = False

    # T2.1 — Context window token-budget pruning.
    # When enabled, _build_chat_messages applies token-budget pruning
    # after the count-based max_history cap. Keeps beginning + end of
    # conversation, replaces middle with a placeholder.
    CHAT_CONTEXT_PRUNING_ENABLED: bool = True
    CHAT_CONTEXT_TOKEN_BUDGET: int = 6000

    # Q1-A: Worker lease integration
    FLOWMANNER_LEASE_ENABLED: bool = True
    FLOWMANNER_LEASE_RECLAIMER_ENABLED: bool = True

    # Q1-A chunk 5: Per-workspace+provider circuit breaker
    FLOWMANNER_CIRCUIT_BREAKER_ENABLED: bool = True
    # Fail-closed default: if the breaker's pre-call check throws (DB/serialization
    # error), the guardrail DENIES the call rather than silently allowing it. Set to
    # False only to restore the old fail-open behaviour (not recommended; it defeats
    # the breaker). When False, check failures are still surfaced at ERROR + metric.
    FLOWMANNER_CIRCUIT_BREAKER_FAIL_CLOSED: bool = True

    # Q1-B chunk 2: HITL timeout + expiry worker
    HITL_DEFAULT_TIMEOUT_HOURS: int = 24
    HITL_DEFAULT_AUTO_ACTION: str = "reject"  # reject | approve | stay

    # Epic 3.3 — personal-memory / memory-entry retrieval-lifecycle decay job.
    # Soft-archive + importance decay + hard-delete of expired sensitive claims.
    # All values are safe to tune via env without a code change.
    #
    # NOTE on schema mapping (the merged PersonalMemoryClaim has no
    # scope='constraint' / scope='sensitive' — see personal_memory_models.py):
    #   - "immortal" claims = sensitivity == 'restricted'  (never arch/decay)
    #   - "sensitive + expired" claims = claim_type == 'sensitive' AND
    #     expires_at < now()  (hard-deleted)
    # These map onto the real CHECK-constrained enumerations.
    MEMORY_DECAY_TTL_DAYS: int = 90  # soft-archive if not recalled within this window
    MEMORY_DECAY_RATE_PER_DAY: float = 0.01  # importance * (1 - rate * days_since_last_use)
    MEMORY_DECAY_MIN_IMPORTANCE: float = 0.0  # floor after decay (0 = allow decay to zero)
    MEMORY_DECAY_IMMORTAL_SENSITIVITY: str = "restricted"  # claims with this sensitivity are immortal
    MEMORY_DECAY_SENSITIVE_CLAIM_TYPE: str = "sensitive"  # claim_type that may be hard-deleted when expired

    # Q2-Q3 Chunk 2 Tier 2: Cross-mission episodic memory
    # Default OFF — the BM25+vector episodic memory system is a sunset
    # candidate (model eats individual agent memory by late 2027).
    # Gated behind this flag so it can be re-enabled for the DRR experiment
    # or if cross-mission recall proves valuable.
    FLOWMANNER_CROSS_MISSION_MEMORY: bool = True

    # Q6 GOLD-LEDGER #2: bridge ReviewerGuard -> HITL inbox.  When ON, every
    # completed substrate run has its node outputs verified (lexical-only,
    # $0 token cost) and any ungrounded claim is drained into /api/inbox as
    # an ESCALATION.  Escalate-only: never mutates or corrupts run data.
    # Default OFF — first production wiring of a previously-uncalled engine;
    # flip to True (env or here) for gradual rollout once inbox-noise volume
    # is observed on real traffic.
    REVIEWER_GUARD_DRAIN_ENABLED: bool = False

    # Comment 9: wire the Q6-B cross-family SecondPassVerifier into the
    # production inbox drain. Off by default: the drain stays lexical-only
    # ($0 token cost) until this is explicitly enabled AND a different-family
    # verifier model is available in the catalog. When ON but no verifier
    # model can be resolved, the drain degrades to lexical-only and records
    # that degradation in the HITL context + metrics (never silent).
    REVIEWER_GUARD_SECOND_PASS_ENABLED: bool = False

    # Strategy gating — experimental strategies (swarm, pipeline, meta, langgraph)
    # Set to True to enable strategies that require complex workflow structures.
    # Per strategy profiling 2026-07-04, these failed validation with simple workflows.
    STRATEGY_EXPERIMENTAL: bool = False

    # Strategy gating — deprecated strategies (meta, swarm, pipeline, langgraph)
    # 0% success with 27B model per strategy profiling 2026-07-04.
    # Set to True to allow deprecated strategies (escape hatch for testing).
    STRATEGY_ALLOW_DEPRECATED: bool = False

    # Cost-aware plan selection (K-Plan Scored Pick)
    #
    # Default changed from "off" -> "auto" (GOLD ledger #5): the full path
    # (engine + planner wiring + frontend observatory) was already built and
    # verified, but the "off" default kept the observatory silently empty.
    #
    # Mode semantics (see app/services/mission_planner.py::_plan_with_selection):
    #   "off"  -> original single-shot path (no candidate generation).
    #   "on"   -> generate K candidates, pick the CHEAPEST eligible plan
    #             (policy="min_cost"). Best when you want the lowest-resource plan.
    #   "auto" -> generate K candidates, pick the balanced winner
    #             (policy="balanced"; quality composite already folds in a cost
    #             penalty). Graceful default: no hard external dependency.
    #
    # Why "auto" and not "on":
    #   - "auto" requires nothing beyond what the wiring already provides:
    #     candidates are produced by a rule-based heuristic (no LLM) plus two
    #     LLM personas that fall back to the heuristic tasks on failure, so the
    #     candidate list is NEVER empty. Scoring is fully heuristic (no external
    #     scoring model, no network). select_plan() falls back to the best-overall
    #     candidate when nothing clears PLAN_SELECTION_MIN_QUALITY. And any failure
    #     inside _plan_with_selection is swallowed and falls back to the original
    #     single-shot path, so a mission can never fail because plan selection broke.
    #   - "on" (min_cost) is safe too but strictly prefers the cheapest plan, which
    #     can sacrifice quality; it is the more opinionated choice, so it stays
    #     opt-in rather than the default.
    #   - The only concrete cost of enabling is two extra LLM persona calls per
    #     planning run (on top of the heuristic). Tune with PLAN_SELECTION_K.
    #
    # Degenerate-case guards (all already present, documented for reviewers):
    #   - Empty candidates -> RuntimeError -> single-shot fallback.
    #   - No candidate >= PLAN_SELECTION_MIN_QUALITY -> select_plan uses best-overall.
    #   - Any planner-side exception -> single-shot fallback (mission still plans).
    BUDGET_AWARE_PLAN_SELECTION: Literal["off", "on", "auto"] = "auto"
    PLAN_SELECTION_K: int = 3
    PLAN_SELECTION_MIN_QUALITY: float = 0.6

    # ── Native Anthropic / Opus support (Comment 6) ──────────────────────
    # Opus (and other native Anthropic models) require a real Anthropic API key
    # or an approved OpenRouter Anthropic route. They are DISABLED unless the
    # catalog marks them enabled AND this flag is true, so a misconfigured deploy
    # can never silently route Opus through the OpenAI-compatible path.
    ENABLE_NATIVE_ANTHROPIC: bool = False
    # Allow routing Anthropic models via OpenRouter's OpenAI-compatible proxy
    # (requires OPENROUTER_API_KEY and an approved Anthropic route on OpenRouter).
    ALLOW_ANTHROPIC_VIA_OPENROUTER: bool = False
    # Hard gate for premium models (e.g. claude-3-opus). Even when the catalog
    # enables a premium model, this must be on for it to be selectable.
    ENABLE_PREMIUM_MODELS: bool = False

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    def validate_secrets(self) -> list[str]:
        """Return list of warnings for secrets still using placeholder values."""
        warnings: list[str] = []
        if self.APP_ENV != "development":
            secret_fields = {
                "JWT_SECRET_KEY": self.JWT_SECRET_KEY,
                "SECRET_KEY": self.SECRET_KEY,
                "AES_ENCRYPTION_KEY": self.AES_ENCRYPTION_KEY,
            }
            for name, value in secret_fields.items():
                if value in PLACEHOLDER_SECRETS:
                    warnings.append(f"{name} is using a placeholder value — set a strong secret in .env")
        return warnings

    def assert_production_ready(self) -> None:
        """Fail fast if production secrets are not set. Call from lifespan startup."""
        if self.APP_ENV == "development":
            return
        bad: list[str] = []
        if self.SECRET_KEY in PLACEHOLDER_SECRETS or len(self.SECRET_KEY) < 32:
            bad.append("SECRET_KEY must be set to a random string of at least 32 characters")
        if self.JWT_SECRET_KEY in PLACEHOLDER_SECRETS or len(self.JWT_SECRET_KEY) < 32:
            bad.append("JWT_SECRET_KEY must be set to a random string of at least 32 characters")
        if self.AES_ENCRYPTION_KEY in PLACEHOLDER_SECRETS or len(self.AES_ENCRYPTION_KEY) < 32:
            bad.append(
                "AES_ENCRYPTION_KEY must be set to a random string of at least 32 characters (used for API key encryption)"
            )
        if not self.AUTH_V3_COOKIE_SECURE:
            bad.append("AUTH_V3_COOKIE_SECURE must be true in production (HTTPS-only cookies)")
        if not self.SENTRY_WEBHOOK_SECRET or len(self.SENTRY_WEBHOOK_SECRET) < 16:
            bad.append(
                "SENTRY_WEBHOOK_SECRET must be set (>=16 chars) in production to prevent unsigned webhook acceptance"
            )
        if bad:
            raise RuntimeError("FATAL: Production secrets not configured:\n" + "\n".join(bad))


settings = Settings()
