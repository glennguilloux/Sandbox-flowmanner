#!/usr/bin/env python3
"""
Add External Model Support

Phase 5: Migration & Testing Strategy
- Database migration for external_models and model_usage tables
- Enables MoonshotAI Kimi and DeepSeek model integration
- Supports OpenRouter and DeepSeek API providers

Revision ID: 2026_02_07_1600
Revises: 2026_02_07_1500_add_rag_chat_integration
Create Date: 2026-02-07 16:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "2026_02_07_1600"
down_revision = "2026_02_07_1500_add_rag_chat_integration"
branch_labels = None
depends_on = None


def upgrade():
    """
    Upgrade function to add external model support tables.

    Creates the following tables:
    - external_models: External AI provider configurations and model metadata
    - model_usage: Usage statistics tracking for external models

    Supported providers:
    - openrouter: moonshotai/kimi-k2.5, claude-3.5-sonnet, gpt-4o, etc.
    - deepseek: deepseek-chat, deepseek-reasoner
    """

    # Create external_models table
    # Stores external AI provider configurations and model metadata
    op.create_table(
        "external_models",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "provider", sa.String(50), nullable=False, index=True
        ),  # "openrouter", "deepseek"
        sa.Column(
            "model_name", sa.String(100), nullable=False, index=True
        ),  # e.g., "moonshotai/kimi-k2.5"
        sa.Column(
            "display_name", sa.String(255), nullable=False
        ),  # Human-readable name
        sa.Column("max_tokens", sa.Integer(), nullable=True),  # Maximum output tokens
        sa.Column("context_length", sa.Integer(), nullable=True),  # Context window size
        sa.Column(
            "cost_per_1k_input", sa.Float(), nullable=True
        ),  # Cost per 1K input tokens (USD)
        sa.Column(
            "cost_per_1k_output", sa.Float(), nullable=True
        ),  # Cost per 1K output tokens (USD)
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    # Create indexes for external_models
    op.create_index(
        "idx_external_models_provider", "external_models", ["provider"], unique=False
    )
    op.create_index(
        "idx_external_models_model_name",
        "external_models",
        ["model_name"],
        unique=False,
    )
    op.create_index(
        "idx_external_models_active", "external_models", ["is_active"], unique=False
    )

    # Create model_usage table
    # Tracks usage statistics of external AI models
    op.create_table(
        "model_usage",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "provider", sa.String(50), nullable=False, index=True
        ),  # "openrouter", "deepseek"
        sa.Column(
            "model_name", sa.String(100), nullable=False, index=True
        ),  # e.g., "moonshotai/kimi-k2.5"
        sa.Column(
            "request_id", sa.String(255), nullable=True, index=True
        ),  # External provider request ID
        sa.Column(
            "user_id", sa.String(36), nullable=True, index=True
        ),  # User who made the request
        sa.Column("input_tokens", sa.Integer(), default=0, nullable=False),
        sa.Column("output_tokens", sa.Integer(), default=0, nullable=False),
        sa.Column(
            "reasoning_tokens", sa.Integer(), default=0, nullable=False
        ),  # For deepseek-reasoner
        sa.Column("cost_usd", sa.Float(), default=0.0, nullable=False),
        sa.Column(
            "response_time_ms", sa.Integer(), nullable=True
        ),  # Response time in milliseconds
        sa.Column("success", sa.Boolean(), default=True, nullable=False),
        sa.Column(
            "error_message", sa.Text(), nullable=True
        ),  # Error details if success=False
        sa.Column(
            "model_id", sa.String(36), nullable=True
        ),  # Foreign key to external_models
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Create indexes for model_usage
    op.create_index(
        "idx_model_usage_provider", "model_usage", ["provider"], unique=False
    )
    op.create_index(
        "idx_model_usage_model_name", "model_usage", ["model_name"], unique=False
    )
    op.create_index(
        "idx_model_usage_request_id", "model_usage", ["request_id"], unique=False
    )
    op.create_index("idx_model_usage_user_id", "model_usage", ["user_id"], unique=False)
    op.create_index(
        "idx_model_usage_created", "model_usage", ["created_at"], unique=False
    )
    op.create_index("idx_model_usage_success", "model_usage", ["success"], unique=False)

    # Seed initial model configurations
    _seed_external_models()


def _seed_external_models():
    """Seed the external_models table with initial configurations."""

    # MoonshotAI Kimi K2.5 (via OpenRouter)
    op.execute(
        """
        INSERT INTO external_models (id, provider, model_name, display_name, max_tokens, context_length, cost_per_1k_input, cost_per_1k_output, is_active)
        VALUES (
            'ext-kimi-k2.5',
            'openrouter',
            'moonshotai/kimi-k2.5',
            'Kimi K2.5',
            32768,
            32768,
            0.0008,
            0.0016,
            true
        )
    """
    )

    # DeepSeek Chat
    op.execute(
        """
        INSERT INTO external_models (id, provider, model_name, display_name, max_tokens, context_length, cost_per_1k_input, cost_per_1k_output, is_active)
        VALUES (
            'ext-deepseek-chat',
            'deepseek',
            'deepseek-chat',
            'DeepSeek Chat',
            4096,
            4096,
            0.00007,
            0.00028,
            true
        )
    """
    )

    # DeepSeek Reasoner
    op.execute(
        """
        INSERT INTO external_models (id, provider, model_name, display_name, max_tokens, context_length, cost_per_1k_input, cost_per_1k_output, is_active)
        VALUES (
            'ext-deepseek-reasoner',
            'deepseek',
            'deepseek-reasoner',
            'DeepSeek Reasoner',
            8192,
            8192,
            0.00014,
            0.00087,
            true
        )
    """
    )

    # Additional free OpenRouter models
    op.execute(
        """
        INSERT INTO external_models (id, provider, model_name, display_name, max_tokens, context_length, cost_per_1k_input, cost_per_1k_output, is_active)
        VALUES 
            ('ext-gemma-free', 'openrouter', 'openrouter/google/gemma-2-9b-it:free', 'Gemma 2 9B Free', 8192, 8192, 0.0, 0.0, true),
            ('ext-claude-sonnet', 'openrouter', 'openrouter/anthropic/claude-3.5-sonnet', 'Claude 3.5 Sonnet', 200000, 200000, 0.003, 0.015, true),
            ('ext-gpt-4o', 'openrouter', 'openrouter/openai/gpt-4o', 'GPT-4o', 128000, 128000, 0.0025, 0.01, true),
            ('ext-gemini-flash', 'openrouter', 'openrouter/google/gemini-2.0-flash', 'Gemini 2.0 Flash', 1048576, 1048576, 0.00035, 0.0014, true)
    """
    )


def downgrade():
    """
    Downgrade function to remove external model support tables.
    Reverses all changes made in the upgrade function.
    """

    # Drop indexes and tables in reverse order

    # Drop model_usage indexes
    op.drop_index("idx_model_usage_success", table_name="model_usage")
    op.drop_index("idx_model_usage_created", table_name="model_usage")
    op.drop_index("idx_model_usage_user_id", table_name="model_usage")
    op.drop_index("idx_model_usage_request_id", table_name="model_usage")
    op.drop_index("idx_model_usage_model_name", table_name="model_usage")
    op.drop_index("idx_model_usage_provider", table_name="model_usage")

    # Drop model_usage table
    op.drop_table("model_usage")

    # Drop external_models indexes
    op.drop_index("idx_external_models_active", table_name="external_models")
    op.drop_index("idx_external_models_model_name", table_name="external_models")
    op.drop_index("idx_external_models_provider", table_name="external_models")

    # Drop external_models table
    op.drop_table("external_models")
