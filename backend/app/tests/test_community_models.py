"""Unit tests for CommunityTemplate ORM model (Q2-Q3 Chunk 8).

Proves that adding the CommunityTemplate class resolves the
NoReferencedTableError that blocked `alembic check` (issue #1).

No live DB required — all tests operate on SQLAlchemy metadata.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, inspect


class TestCommunityTemplateDriftClosure:
    """Prove the FK target is resolvable — the whole point of this chunk."""

    def test_community_template_model_resolves_fk_from_comment(self):
        """CommunityComment.template_id has ForeignKey('community_templates.id');
        the FK target must be a known table in the SQLAlchemy metadata.

        Before this chunk, alembic check raised NoReferencedTableError.
        After, it must resolve cleanly.
        """
        # The FK target table must be in Base.metadata
        from app.models import Base
        from app.models.community_models import CommunityComment, CommunityTemplate

        assert (
            "community_templates" in Base.metadata.tables
        ), "community_templates not in Base.metadata — FK target unresolved"

        # CommunityComment's template_id FK must point to community_templates
        comment_table = CommunityComment.__table__
        template_id_col = comment_table.columns["template_id"]
        fk_targets = [fk.target_fullname for fk in template_id_col.foreign_keys]
        assert "community_templates.id" in fk_targets, f"FK target not found. Got: {fk_targets}"


class TestCommunityTemplateSchemaShape:
    """Prove the model matches the live DB schema (15 columns)."""

    def test_community_template_table_name(self):
        from app.models.community_models import CommunityTemplate

        assert CommunityTemplate.__tablename__ == "community_templates"

    def test_community_template_has_all_15_columns(self):
        from app.models.community_models import CommunityTemplate

        expected_columns = {
            "id",
            "title",
            "description",
            "author_id",
            "author_name",
            "category",
            "tags",
            "content",
            "rating",
            "rating_count",
            "fork_count",
            "use_count",
            "is_featured",
            "created_at",
            "updated_at",
        }
        actual_columns = set(CommunityTemplate.__table__.columns.keys())
        missing = expected_columns - actual_columns
        extra = actual_columns - expected_columns
        assert not missing, f"CommunityTemplate missing columns: {missing}"
        assert not extra, f"CommunityTemplate has unexpected columns: {extra}"

    def test_community_template_column_types_match_db(self):
        """Column types must match the live PostgreSQL schema."""
        from app.models.community_models import CommunityTemplate

        cols = CommunityTemplate.__table__.columns

        # varchar(36) UUIDs
        assert isinstance(cols["id"].type, String)
        assert cols["id"].type.length == 36

        # varchar(255)
        assert isinstance(cols["title"].type, String)
        assert cols["title"].type.length == 255

        # text
        assert isinstance(cols["description"].type, Text)
        assert isinstance(cols["tags"].type, Text)
        assert isinstance(cols["content"].type, Text)

        # varchar(36), varchar(100), varchar(50)
        assert isinstance(cols["author_id"].type, String)
        assert cols["author_id"].type.length == 36
        assert isinstance(cols["author_name"].type, String)
        assert cols["author_name"].type.length == 100
        assert isinstance(cols["category"].type, String)
        assert cols["category"].type.length == 50

        # double precision
        assert isinstance(cols["rating"].type, Float)

        # integer
        assert isinstance(cols["rating_count"].type, Integer)
        assert isinstance(cols["fork_count"].type, Integer)
        assert isinstance(cols["use_count"].type, Integer)

        # boolean
        assert isinstance(cols["is_featured"].type, Boolean)

        # timestamp with time zone (from TimestampMixin)
        assert isinstance(cols["created_at"].type, DateTime)
        assert cols["created_at"].type.timezone is True
        assert isinstance(cols["updated_at"].type, DateTime)
        assert cols["updated_at"].type.timezone is True

    def test_community_template_primary_key_is_id(self):
        from app.models.community_models import CommunityTemplate

        pk_cols = list(CommunityTemplate.__table__.primary_key.columns)
        assert len(pk_cols) == 1
        assert pk_cols[0].name == "id"

    def test_community_template_nullable_matches_db(self):
        """Nullable flags must match the live DB constraints."""
        from app.models.community_models import CommunityTemplate

        cols = CommunityTemplate.__table__.columns

        # NOT NULL columns
        assert cols["id"].nullable is False
        assert cols["title"].nullable is False
        assert cols["description"].nullable is False
        assert cols["author_id"].nullable is False
        assert cols["author_name"].nullable is False
        assert cols["category"].nullable is False

        # Nullable columns
        assert cols["tags"].nullable is True
        assert cols["content"].nullable is True
        assert cols["rating"].nullable is True
        assert cols["rating_count"].nullable is True
        assert cols["fork_count"].nullable is True
        assert cols["use_count"].nullable is True
        assert cols["is_featured"].nullable is True
