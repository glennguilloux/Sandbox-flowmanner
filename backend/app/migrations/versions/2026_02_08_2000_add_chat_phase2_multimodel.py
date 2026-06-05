"""
Add Phase 2 Chat System Enhancement - Multi-Model Infrastructure

Phase 2: Multi-Model Enhancement
- ModelMetrics: Track performance metrics per model
- UserModelPreferences: User preferences for model selection
- ModelPricing: Pricing information for different models
- ChatMessageModel: Track model used for each message

Revision ID: 2026_02_08_2000
Revises: 2026_02_08_1900_add_chat_phase1_infrastructure
Create Date: 2026-02-08 20:00:00.000000

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '2026_02_08_2000'
down_revision = '2026_02_08_1900_add_chat_phase1_infrastructure'
branch_labels = None
depends_on = None


def upgrade():
    """
    Upgrade function to add Phase 2 multi-model infrastructure tables.
    
    Creates the following tables:
    - model_metrics: Track performance metrics per model
    - user_model_preferences: User preferences for model selection
    - model_pricing: Pricing information for different models
    - chat_message_model: Track model used for each message (extension)
    """
    
    # Create model_metrics table
    # Tracks performance metrics per model usage
    op.create_table(
        'model_metrics',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('metric_id', sa.String(64), unique=True, nullable=False, index=True),
        sa.Column('model_name', sa.String(100), nullable=False, index=True),
        sa.Column('thread_id', sa.Integer(), nullable=True, index=True),
        sa.Column('session_id', sa.String(64), nullable=True, index=True),
        
        # Performance metrics
        sa.Column('response_time_ms', sa.Float(), nullable=True),
        sa.Column('first_token_ms', sa.Float(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), default=0),
        sa.Column('prompt_tokens', sa.Integer(), default=0),
        sa.Column('completion_tokens', sa.Integer(), default=0),
        
        # Quality metrics
        sa.Column('user_rating', sa.Integer(), nullable=True),  # 1-5 rating
        sa.Column('relevance_score', sa.Float(), nullable=True),
        sa.Column('error_count', sa.Integer(), default=0),
        sa.Column('error_message', sa.Text(), nullable=True),
        
        # Cost tracking
        sa.Column('input_cost', sa.Float(), default=0.0),
        sa.Column('output_cost', sa.Float(), default=0.0),
        sa.Column('total_cost', sa.Float(), default=0.0),
        
        # Metadata
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        # Foreign keys
        sa.ForeignKeyConstraint(['thread_id'], ['chat_threads.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['session_id'], ['chat_model_sessions.session_id'], ondelete='SET NULL'),
    )
    
    # Create indexes for model_metrics
    op.create_index('idx_model_metrics_metric_id', 'model_metrics', ['metric_id'], unique=True)
    op.create_index('idx_model_metrics_model', 'model_metrics', ['model_name'], unique=False)
    op.create_index('idx_model_metrics_thread', 'model_metrics', ['thread_id'], unique=False)
    op.create_index('idx_model_metrics_session', 'model_metrics', ['session_id'], unique=False)
    op.create_index('idx_model_metrics_recorded', 'model_metrics', ['recorded_at'], unique=False)
    
    # Create user_model_preferences table
    # Stores user preferences for model selection
    op.create_table(
        'user_model_preferences',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('preference_id', sa.String(64), unique=True, nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), nullable=False, index=True),
        sa.Column('thread_id', sa.Integer(), nullable=True, index=True),
        
        # Model preferences
        sa.Column('default_model', sa.String(100), nullable=True),
        sa.Column('preferred_provider', sa.String(50), nullable=True),
        sa.Column('fallback_model', sa.String(100), nullable=True),
        
        # Model settings per thread
        sa.Column('model_settings', sa.JSON(), nullable=True),  # Per-model settings
        
        # Usage preferences
        sa.Column('auto_switch_enabled', sa.Boolean(), default=False),
        sa.Column('cost_warning_threshold', sa.Float(), default=10.0),  # USD warning threshold
        sa.Column('max_daily_cost', sa.Float(), nullable=True),
        
        # Performance preferences
        sa.Column('prefer_speed', sa.Boolean(), default=False),
        sa.Column('prefer_quality', sa.Boolean(), default=False),
        sa.Column('prefer_cost_efficiency', sa.Boolean(), default=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        
        # Foreign keys
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['thread_id'], ['chat_threads.id'], ondelete='CASCADE'),
    )
    
    # Create indexes for user_model_preferences
    op.create_index('idx_user_prefs_preference_id', 'user_model_preferences', ['preference_id'], unique=True)
    op.create_index('idx_user_prefs_user', 'user_model_preferences', ['user_id'], unique=False)
    op.create_index('idx_user_prefs_thread', 'user_model_preferences', ['thread_id'], unique=False)
    
    # Create model_pricing table
    # Stores pricing information for different models
    op.create_table(
        'model_pricing',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('pricing_id', sa.String(64), unique=True, nullable=False, index=True),
        sa.Column('model_name', sa.String(100), nullable=False, unique=True, index=True),
        sa.Column('provider', sa.String(50), nullable=False, index=True),
        
        # Pricing (per 1K tokens)
        sa.Column('input_cost_per_1k', sa.Float(), default=0.0),
        sa.Column('output_cost_per_1k', sa.Float(), default=0.0),
        sa.Column('currency', sa.String(3), default='USD'),
        
        # Model capabilities
        sa.Column('max_tokens', sa.Integer(), nullable=True),
        sa.Column('supports_streaming', sa.Boolean(), default=True),
        sa.Column('supports_function_calling', sa.Boolean(), default=False),
        sa.Column('supports_vision', sa.Boolean(), default=False),
        sa.Column('supports_thinking', sa.Boolean(), default=False),
        
        # Performance characteristics
        sa.Column('typical_response_time_ms', sa.Float(), nullable=True),
        sa.Column('performance_tier', sa.String(20), default='standard'),  # fast, standard, slow
        
        # Status
        sa.Column('is_active', sa.Boolean(), default=True, index=True),
        sa.Column('is_verified', sa.Boolean(), default=False),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Create indexes for model_pricing
    op.create_index('idx_model_pricing_pricing_id', 'model_pricing', ['pricing_id'], unique=True)
    op.create_index('idx_model_pricing_model', 'model_pricing', ['model_name'], unique=True)
    op.create_index('idx_model_pricing_provider', 'model_pricing', ['provider'], unique=False)
    op.create_index('idx_model_pricing_active', 'model_pricing', ['is_active'], unique=False)
    
    # Add model_name column to chat_messages table to track which model generated each message
    op.add_column('chat_messages', sa.Column('model_name', sa.String(100), nullable=True, index=True))
    op.add_column('chat_messages', sa.Column('model_provider', sa.String(50), nullable=True))
    op.add_column('chat_messages', sa.Column('message_cost', sa.Float(), default=0.0))
    
    # Create index for model_name on chat_messages
    op.create_index('idx_chat_messages_model', 'chat_messages', ['model_name'], unique=False)
    
    # Add model_name column to chat_threads table for current active model
    op.add_column('chat_threads', sa.Column('current_model', sa.String(100), nullable=True, index=True))
    op.add_column('chat_threads', sa.Column('current_provider', sa.String(50), nullable=True))
    
    # Create index for current_model on chat_threads
    op.create_index('idx_chat_threads_model', 'chat_threads', ['current_model'], unique=False)
    
    # Seed default model pricing data
    seed_model_pricing(op)


def seed_model_pricing(op):
    """Seed default model pricing data"""
    
    # Default model pricing configurations
    default_pricing = [
        {
            'pricing_id': 'pricing_deepseek_chat',
            'model_name': 'deepseek-chat',
            'provider': 'deepseek',
            'input_cost_per_1k': 0.00014,
            'output_cost_per_1k': 0.00028,
            'max_tokens': 64000,
            'supports_streaming': True,
            'supports_function_calling': True,
            'supports_vision': False,
            'supports_thinking': False,
            'typical_response_time_ms': 1500.0,
            'performance_tier': 'standard',
            'is_active': True,
            'is_verified': True,
        },
        {
            'pricing_id': 'pricing_deepseek_reasoner',
            'model_name': 'deepseek-reasoner',
            'provider': 'deepseek',
            'input_cost_per_1k': 0.00055,
            'output_cost_per_1k': 0.0011,
            'max_tokens': 64000,
            'supports_streaming': True,
            'supports_function_calling': True,
            'supports_vision': False,
            'supports_thinking': True,
            'typical_response_time_ms': 3000.0,
            'performance_tier': 'slow',
            'is_active': True,
            'is_verified': True,
        },
        {
            'pricing_id': 'pricing_moonshot_kimi',
            'model_name': 'moonshotai/kimi-k2.5',
            'provider': 'openrouter',
            'input_cost_per_1k': 0.001,
            'output_cost_per_1k': 0.002,
            'max_tokens': 128000,
            'supports_streaming': True,
            'supports_function_calling': True,
            'supports_vision': True,
            'supports_thinking': False,
            'typical_response_time_ms': 2000.0,
            'performance_tier': 'standard',
            'is_active': True,
            'is_verified': True,
        },
    ]
    
    for pricing in default_pricing:
        op.execute(
            op.get_bind().execute(
                sa.text("""
                    INSERT INTO model_pricing (
                        pricing_id, model_name, provider, input_cost_per_1k, 
                        output_cost_per_1k, currency, max_tokens, supports_streaming,
                        supports_function_calling, supports_vision, supports_thinking,
                        typical_response_time_ms, performance_tier, is_active, is_verified,
                        created_at, updated_at
                    ) VALUES (
                        :pricing_id, :model_name, :provider, :input_cost_per_1k,
                        :output_cost_per_1k, 'USD', :max_tokens, :supports_streaming,
                        :supports_function_calling, :supports_vision, :supports_thinking,
                        :typical_response_time_ms, :performance_tier, :is_active, :is_verified,
                        NOW(), NOW()
                    )
                    ON CONFLICT (model_name) DO NOTHING
                """),
                pricing
            )
        )


def downgrade():
    """
    Downgrade function to remove Phase 2 multi-model infrastructure tables.
    Reverses all changes made in the upgrade function.
    """
    
    # Remove indexes and columns from chat_threads
    op.drop_index('idx_chat_threads_model', table_name='chat_threads')
    op.drop_column('chat_threads', 'current_provider')
    op.drop_column('chat_threads', 'current_model')
    
    # Remove indexes and columns from chat_messages
    op.drop_index('idx_chat_messages_model', table_name='chat_messages')
    op.drop_column('chat_messages', 'message_cost')
    op.drop_column('chat_messages', 'model_provider')
    op.drop_column('chat_messages', 'model_name')
    
    # Drop model_pricing table
    op.drop_index('idx_model_pricing_active', table_name='model_pricing')
    op.drop_index('idx_model_pricing_provider', table_name='model_pricing')
    op.drop_index('idx_model_pricing_model', table_name='model_pricing')
    op.drop_index('idx_model_pricing_pricing_id', table_name='model_pricing')
    op.drop_table('model_pricing')
    
    # Drop user_model_preferences table
    op.drop_index('idx_user_prefs_thread', table_name='user_model_preferences')
    op.drop_index('idx_user_prefs_user', table_name='user_model_preferences')
    op.drop_index('idx_user_prefs_preference_id', table_name='user_model_preferences')
    op.drop_table('user_model_preferences')
    
    # Drop model_metrics table
    op.drop_index('idx_model_metrics_recorded', table_name='model_metrics')
    op.drop_index('idx_model_metrics_session', table_name='model_metrics')
    op.drop_index('idx_model_metrics_thread', table_name='model_metrics')
    op.drop_index('idx_model_metrics_model', table_name='model_metrics')
    op.drop_index('idx_model_metrics_metric_id', table_name='model_metrics')
    op.drop_table('model_metrics')
