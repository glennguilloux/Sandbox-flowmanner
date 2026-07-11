"""TDD tests for MemoryDigestDelivery model (D30-60, T31 — daily digest).

Pure-Python model tests (no live DB). Integration tests live in
``test_memory_digest_models_integration.py`` (future) and run via
``docker compose exec backend pytest -m integration``.

Run via::

    cd /opt/flowmanner/backend
    DATABASE_URL="postgresql+asyncpg://flowmanner:REDACTED_DB_PASSWORD@127.0.0.1:5432/flowmanner" \\
      .venv/bin/python -m pytest tests/test_memory_digest_models.py -v
"""
from __future__ import annotations

import os

import pytest

# Ensure DATABASE_URL is set BEFORE importing app modules that need it.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://flowmanner:REDACTED_DB_PASSWORD@127.0.0.1:5432/flowmanner",
)


class TestTableRegistration:
    def test_table_registered_in_metadata(self) -> None:
        from app.models import Base
        from app.models.memory_digest_models import MemoryDigestDelivery

        assert "memory_digest_deliveries" in Base.metadata.tables

    def test_tablename(self) -> None:
        from app.models.memory_digest_models import MemoryDigestDelivery

        assert MemoryDigestDelivery.__tablename__ == "memory_digest_deliveries"


class TestHardcodedTuples:
    def test_all_delivery_channels_hardcoded(self) -> None:
        from app.models.memory_digest_models import ALL_DELIVERY_CHANNELS

        assert ALL_DELIVERY_CHANNELS == ("email", "in_app", "preview")

    def test_all_delivery_statuses_hardcoded(self) -> None:
        from app.models.memory_digest_models import ALL_DELIVERY_STATUSES

        assert ALL_DELIVERY_STATUSES == (
            "pending",
            "delivered",
            "failed",
            "previewed",
        )

    def test_no_sunder_name_leak(self) -> None:
        """Defensive: ensure no _TRANSITIONS or other sunder-name leaks
        in the model class (project's known pitfall for str-Enum CHECK
        constraint SQL)."""
        from app.models.memory_digest_models import MemoryDigestDelivery

        for attr in dir(MemoryDigestDelivery):
            assert not attr.startswith("_TRANSITIONS"), (
                f"sunder-name leak: {attr}"
            )


class TestColumns:
    def test_id_column(self) -> None:
        from app.models import Base
        from app.models.memory_digest_models import MemoryDigestDelivery

        col = Base.metadata.tables["memory_digest_deliveries"].columns["id"]
        assert col.primary_key
        assert not col.nullable

    def test_user_id_not_null_fk_to_users(self) -> None:
        from app.models import Base
        from app.models.memory_digest_models import MemoryDigestDelivery

        col = Base.metadata.tables["memory_digest_deliveries"].columns["user_id"]
        assert not col.nullable
        fks = list(col.foreign_keys)
        assert any(fk.target_fullname == "users.id" for fk in fks)

    def test_workspace_id_not_null_fk_cascade(self) -> None:
        from app.models import Base
        from app.models.memory_digest_models import MemoryDigestDelivery

        col = Base.metadata.tables["memory_digest_deliveries"].columns[
            "workspace_id"
        ]
        assert not col.nullable
        fks = list(col.foreign_keys)
        matching = [
            fk for fk in fks if fk.target_fullname == "workspaces.id"
        ]
        assert matching
        assert "CASCADE" in (matching[0].ondelete or "")

    def test_sent_at_not_null(self) -> None:
        from app.models import Base
        from app.models.memory_digest_models import MemoryDigestDelivery

        col = Base.metadata.tables["memory_digest_deliveries"].columns["sent_at"]
        assert not col.nullable

    def test_delivery_channel_not_null(self) -> None:
        from app.models import Base
        from app.models.memory_digest_models import MemoryDigestDelivery

        col = Base.metadata.tables["memory_digest_deliveries"].columns[
            "delivery_channel"
        ]
        assert not col.nullable

    def test_status_not_null(self) -> None:
        from app.models import Base
        from app.models.memory_digest_models import MemoryDigestDelivery

        col = Base.metadata.tables["memory_digest_deliveries"].columns["status"]
        assert not col.nullable

    def test_claims_count_not_null(self) -> None:
        from app.models import Base
        from app.models.memory_digest_models import MemoryDigestDelivery

        col = Base.metadata.tables["memory_digest_deliveries"].columns[
            "claims_count"
        ]
        assert not col.nullable

    def test_claims_summary_nullable(self) -> None:
        from app.models import Base
        from app.models.memory_digest_models import MemoryDigestDelivery

        col = Base.metadata.tables["memory_digest_deliveries"].columns[
            "claims_summary"
        ]
        assert col.nullable

    def test_recipient_nullable(self) -> None:
        from app.models import Base
        from app.models.memory_digest_models import MemoryDigestDelivery

        col = Base.metadata.tables["memory_digest_deliveries"].columns["recipient"]
        assert col.nullable

    def test_delivered_at_nullable(self) -> None:
        from app.models import Base
        from app.models.memory_digest_models import MemoryDigestDelivery

        col = Base.metadata.tables["memory_digest_deliveries"].columns[
            "delivered_at"
        ]
        assert col.nullable

    def test_error_message_nullable(self) -> None:
        from app.models import Base
        from app.models.memory_digest_models import MemoryDigestDelivery

        col = Base.metadata.tables["memory_digest_deliveries"].columns[
            "error_message"
        ]
        assert col.nullable


class TestCheckConstraints:
    def test_delivery_channel_check(self) -> None:
        from app.models import Base

        table = Base.metadata.tables["memory_digest_deliveries"]
        checks = {c.name for c in table.constraints if hasattr(c, "sqltext")}
        assert "ck_memory_digest_delivery_channel_valid" in checks

    def test_status_check(self) -> None:
        from app.models import Base

        table = Base.metadata.tables["memory_digest_deliveries"]
        checks = {c.name for c in table.constraints if hasattr(c, "sqltext")}
        assert "ck_memory_digest_delivery_status_valid" in checks


class TestIndexes:
    def test_user_ws_sent_index(self) -> None:
        from app.models import Base

        table = Base.metadata.tables["memory_digest_deliveries"]
        idx_names = {idx.name for idx in table.indexes}
        assert "ix_memory_digest_deliveries_user_ws_sent" in idx_names

    def test_user_ws_channel_index(self) -> None:
        from app.models import Base

        table = Base.metadata.tables["memory_digest_deliveries"]
        idx_names = {idx.name for idx in table.indexes}
        assert "ix_memory_digest_deliveries_user_ws_channel" in idx_names

    def test_sent_at_index(self) -> None:
        from app.models import Base

        table = Base.metadata.tables["memory_digest_deliveries"]
        idx_names = {idx.name for idx in table.indexes}
        assert "ix_memory_digest_deliveries_sent_at" in idx_names
