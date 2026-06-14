from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SECRETS = {"change-me-in-production", "changeme", "secret", "password"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = "development"
    APP_NAME: str = "workflows-backend"
    SECRET_KEY: str = "change-me-in-production"

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/workflows"
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
    LITELLM_ENDPOINT: str = "http://localhost:4000"

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
    LANGFUSE_ENABLED: bool = False
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
    SANDBOXD_ENABLED: bool = True
    SANDBOXD_DEFAULT_TEMPLATE: str = "python-img"

    # Chat tool-calling limits
    CHAT_MAX_TOOL_ROUNDS: int = 15

    # T33 — Inline memory citations in chat.
    # Stage 0 = False (no behavior change). Stage 1+ flips to True to enable
    # the pre-LLM memory recall path in chat_service.stream_message_to_llm.
    # Per-tenant or per-user override is intentionally NOT in scope for T33.
    CHAT_MEMORY_CITATIONS_ENABLED: bool = False

    # Q1-A: Worker lease integration
    FLOWMANNER_LEASE_ENABLED: bool = True
    FLOWMANNER_LEASE_RECLAIMER_ENABLED: bool = True

    # Q1-A chunk 5: Per-workspace+provider circuit breaker
    FLOWMANNER_CIRCUIT_BREAKER_ENABLED: bool = True

    # Q1-B chunk 2: HITL timeout + expiry worker
    HITL_DEFAULT_TIMEOUT_HOURS: int = 24
    HITL_DEFAULT_AUTO_ACTION: str = "reject"  # reject | approve | stay

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
        if bad:
            raise RuntimeError("FATAL: Production secrets not configured:\n" + "\n".join(bad))


settings = Settings()
