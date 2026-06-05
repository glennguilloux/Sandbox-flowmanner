"""
Add RAG chat integration

Phase 1: Chat-RAG Integration Architecture
- Dynamic Context Engine with smart collection assignment
- RAG-Driven Message Templates with full context tracking
- Semantic Threading for multi-turn conversation context
- Advanced Retrieval Strategies for enhanced chat experiences

Revision ID: 2026_02_07_1500
Revises: 2026_02_01_1400_seed_agent_templates
Create Date: 2026-02-07 15:00:00.000000

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '2026_02_07_1500'
down_revision = '2026_02_01_1400_seed_agent_templates'
branch_labels = None
depends_on = None


def upgrade():
    """
    Upgrade function to add RAG chat integration tables.
    
    Creates the following tables:
    - rag_chat_contexts: RAG context attached to chat messages
    - rag_context_sources: Source document references with similarity scores
    - rag_context_versions: Version history for RAG context
    - rag_retrieval_sessions: Session tracking for retrieval operations
    """
    
    # Create rag_chat_contexts table
    # Stores RAG context information linked to chat messages
    op.create_table(
        'rag_chat_contexts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('context_id', sa.String(64), unique=True, nullable=False, index=True),
        sa.Column('message_id', sa.Integer(), nullable=False, index=True),
        sa.Column('thread_id', sa.Integer(), nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), nullable=True, index=True),
        sa.Column('retrieval_confidence', sa.Float(), default=0.0),
        sa.Column('content_hash', sa.String(64), nullable=True),
        sa.Column('validity_created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('validity_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('validity_decay_factor', sa.Float(), default=0.1),
        sa.Column('validity_last_refreshed', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_valid', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['message_id'], ['chat_messages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['thread_id'], ['chat_threads.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    )
    
    # Create indexes for rag_chat_contexts
    op.create_index('idx_rag_contexts_message', 'rag_chat_contexts', ['message_id'], unique=False)
    op.create_index('idx_rag_contexts_thread', 'rag_chat_contexts', ['thread_id'], unique=False)
    op.create_index('idx_rag_contexts_user', 'rag_chat_contexts', ['user_id'], unique=False)
    op.create_index('idx_rag_contexts_validity', 'rag_chat_contexts', ['validity_expires_at'], unique=False)
    
    # Create rag_context_sources table
    # Stores source document references with similarity scores for RAG context
    op.create_table(
        'rag_context_sources',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('source_id', sa.String(64), unique=True, nullable=False, index=True),
        sa.Column('context_id', sa.String(64), nullable=False, index=True),
        sa.Column('collection_id', sa.String(64), nullable=True, index=True),
        sa.Column('collection_name', sa.String(255), nullable=True),
        sa.Column('document_id', sa.String(64), nullable=True),
        sa.Column('document_title', sa.String(255), nullable=True),
        sa.Column('chunk_id', sa.String(64), nullable=False),
        sa.Column('chunk_content', sa.Text(), nullable=False),
        sa.Column('similarity_score', sa.Float(), default=0.0),
        sa.Column('segment_position', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # Create indexes for rag_context_sources
    op.create_index('idx_rag_sources_context', 'rag_context_sources', ['context_id'], unique=False)
    op.create_index('idx_rag_sources_collection', 'rag_context_sources', ['collection_id'], unique=False)
    op.create_index('idx_rag_sources_chunk', 'rag_context_sources', ['chunk_id'], unique=False)
    op.create_index('idx_rag_sources_similarity', 'rag_context_sources', ['similarity_score'], unique=False)
    
    # Create rag_context_versions table
    # Stores version history for RAG context tracking
    op.create_table(
        'rag_context_versions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('version_id', sa.String(64), unique=True, nullable=False, index=True),
        sa.Column('context_id', sa.String(64), nullable=False, index=True),
        sa.Column('source_chunks', sa.JSON(), nullable=True),  # Array of chunk IDs
        sa.Column('collection_ids', sa.JSON(), nullable=True),  # Array of collection IDs
        sa.Column('content_hash', sa.String(64), nullable=True),
        sa.Column('version_timestamp', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['context_id'], ['rag_chat_contexts.context_id'], ondelete='CASCADE'),
    )
    
    # Create indexes for rag_context_versions
    op.create_index('idx_rag_versions_context', 'rag_context_versions', ['context_id'], unique=False)
    op.create_index('idx_rag_versions_timestamp', 'rag_context_versions', ['version_timestamp'], unique=False)
    
    # Create rag_retrieval_sessions table
    # Tracks retrieval sessions for monitoring and analytics
    op.create_table(
        'rag_retrieval_sessions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('session_id', sa.String(64), unique=True, nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), nullable=True, index=True),
        sa.Column('thread_id', sa.Integer(), nullable=True, index=True),
        sa.Column('query_text', sa.Text(), nullable=False),
        sa.Column('retrieved_collections', sa.JSON(), nullable=True),  # Array of collection IDs
        sa.Column('retrieved_documents', sa.JSON(), nullable=True),  # Array of document IDs
        sa.Column('total_sources_found', sa.Integer(), default=0),
        sa.Column('avg_similarity_score', sa.Float(), default=0.0),
        sa.Column('retrieval_strategy', sa.String(100), nullable=True),  # hierarchical, expansion, etc.
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
        sa.Column('success', sa.Boolean(), default=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['thread_id'], ['chat_threads.id'], ondelete='SET NULL'),
    )
    
    # Create indexes for rag_retrieval_sessions
    op.create_index('idx_rag_sessions_user', 'rag_retrieval_sessions', ['user_id'], unique=False)
    op.create_index('idx_rag_sessions_thread', 'rag_retrieval_sessions', ['thread_id'], unique=False)
    op.create_index('idx_rag_sessions_created', 'rag_retrieval_sessions', ['created_at'], unique=False)
    op.create_index('idx_rag_sessions_success', 'rag_retrieval_sessions', ['success'], unique=False)
    
    # Create rag_collection_topics table
    # Maps collections to topics for smart collection assignment
    op.create_table(
        'rag_collection_topics',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('collection_id', sa.String(64), nullable=False, index=True),
        sa.Column('topic', sa.String(100), nullable=False),
        sa.Column('confidence', sa.Float(), default=1.0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['collection_id'], ['rag_collections.collection_id'], ondelete='CASCADE'),
        sa.UniqueConstraint('collection_id', 'topic', name='uq_rag_collection_topic'),
    )
    
    # Create indexes for rag_collection_topics
    op.create_index('idx_rag_collection_topics_collection', 'rag_collection_topics', ['collection_id'], unique=False)
    op.create_index('idx_rag_collection_topics_topic', 'rag_collection_topics', ['topic'], unique=False)


def downgrade():
    """
    Downgrade function to remove RAG chat integration tables.
    Reverses all changes made in the upgrade function.
    """
    
    # Drop indexes and tables in reverse order
    
    # Drop rag_collection_topics
    op.drop_index('idx_rag_collection_topics_topic', table_name='rag_collection_topics')
    op.drop_index('idx_rag_collection_topics_collection', table_name='rag_collection_topics')
    op.drop_table('rag_collection_topics')
    
    # Drop rag_retrieval_sessions
    op.drop_index('idx_rag_sessions_success', table_name='rag_retrieval_sessions')
    op.drop_index('idx_rag_sessions_created', table_name='rag_retrieval_sessions')
    op.drop_index('idx_rag_sessions_thread', table_name='rag_retrieval_sessions')
    op.drop_index('idx_rag_sessions_user', table_name='rag_retrieval_sessions')
    op.drop_table('rag_retrieval_sessions')
    
    # Drop rag_context_versions
    op.drop_index('idx_rag_versions_timestamp', table_name='rag_context_versions')
    op.drop_index('idx_rag_versions_context', table_name='rag_context_versions')
    op.drop_table('rag_context_versions')
    
    # Drop rag_context_sources
    op.drop_index('idx_rag_sources_similarity', table_name='rag_context_sources')
    op.drop_index('idx_rag_sources_chunk', table_name='rag_context_sources')
    op.drop_index('idx_rag_sources_collection', table_name='rag_context_sources')
    op.drop_index('idx_rag_sources_context', table_name='rag_context_sources')
    op.drop_table('rag_context_sources')
    
    # Drop rag_chat_contexts
    op.drop_index('idx_rag_contexts_validity', table_name='rag_chat_contexts')
    op.drop_index('idx_rag_contexts_user', table_name='rag_chat_contexts')
    op.drop_index('idx_rag_contexts_thread', table_name='rag_chat_contexts')
    op.drop_index('idx_rag_contexts_message', table_name='rag_chat_contexts')
    op.drop_table('rag_chat_contexts')
