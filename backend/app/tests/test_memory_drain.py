"""GOV-1.1 — drain ``pending_writes`` via the existing HITL inbox.

No-DB unit tests: every datastore call is mocked. Covers the three
integration points added for 1.1:

* ``BackgroundReviewService._route_to_inbox``  (staging → inbox item)
* ``BackgroundReviewService.resolve_pending_write`` (inbox → durable write)
* ``HITLService.expire_and_act`` memory-approval branch (audited auto-reject)
* ``app.api.v1.hitl`` approve/reject guards (memory writes skip mission signals)
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, "/opt/flowmanner/backend")

import os

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from app.models.hitl_models import HumanInterruptType
from app.models.memory_models import PendingWriteStatus
from app.services.memory.background_review_service import (
    BackgroundReviewService,
    PendingWriteAction,
)


def _db_session_for_stage() -> AsyncMock:
    """Minimal async session used by ``stage_pending_write``."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    return session


def _pending_write_row(
    *,
    action: str = PendingWriteAction.ADD,
    status: str = PendingWriteStatus.PENDING,
    content: str = "Remember to run migrations after model edits.",
    meta: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id="pw-1",
        workspace_id="ws-1",
        user_id=1,
        mission_id=None,
        action=action,
        content=content,
        old_text=None,
        status=status,
        meta=meta,
        reviewed_at=None,
    )


def _make_resolve_db(row: SimpleNamespace) -> AsyncMock:
    """Async session whose single query returns ``row``."""
    session = AsyncMock()
    execute_mock = AsyncMock()
    execute_mock.return_value = MagicMock(scalar_one_or_none=lambda: row)
    session.execute = execute_mock
    session.flush = AsyncMock()
    return session


# ── 1. _route_to_inbox ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_route_to_inbox_creates_memory_approval_item():
    """staging a write raises a MEMORY_APPROVAL inbox item with no mission_id."""
    service = BackgroundReviewService()
    db = _db_session_for_stage()

    fake_item = SimpleNamespace(id="ii-1")
    interrupt = MagicMock()
    interrupt.create_interrupt = AsyncMock(return_value=fake_item)

    with patch("app.services.hitl_service.HITLService", return_value=interrupt):
        result = await service.stage_pending_write(
            db,
            workspace_id="ws-1",
            user_id=1,
            mission_id=None,
            action=PendingWriteAction.ADD,
            content="The deploy script requires --migrate after touching models.",
            old_text=None,
        )

    assert result is not None  # staged row id returned
    interrupt.create_interrupt.assert_awaited_once()
    call = interrupt.create_interrupt.call_args.kwargs
    assert call["interrupt_type"] == HumanInterruptType.MEMORY_APPROVAL
    assert call["mission_id"] is None  # never bound to a mission
    assert call["context"]["pending_write_id"] == result
    assert call["proposed_action"]["action"] == PendingWriteAction.ADD


@pytest.mark.asyncio
async def test_route_to_inbox_survives_inbox_failure():
    """If inbox creation fails the staged row id is still returned (best-effort)."""
    service = BackgroundReviewService()
    db = _db_session_for_stage()

    interrupt = MagicMock()
    interrupt.create_interrupt = AsyncMock(side_effect=RuntimeError("sse down"))

    with patch("app.services.hitl_service.HITLService", return_value=interrupt):
        result = await service.stage_pending_write(
            db,
            workspace_id="ws-1",
            user_id=1,
            mission_id=None,
            action=PendingWriteAction.ADD,
            content="plain note",
            old_text=None,
        )

    assert result is not None


# ── 2. resolve_pending_write ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_pending_write_approve_add_applies_entry():
    row = _pending_write_row(action=PendingWriteAction.ADD)
    db = _make_resolve_db(row)
    service = BackgroundReviewService()
    service.add_reviewed_entry = AsyncMock(return_value="entry-9")

    out = await service.resolve_pending_write(db, pending_write_id="pw-1", approve=True)

    assert out == "entry-9"
    service.add_reviewed_entry.assert_awaited_once()
    assert row.status == PendingWriteStatus.APPROVED


@pytest.mark.asyncio
async def test_resolve_pending_write_reject_marks_rejected():
    row = _pending_write_row(action=PendingWriteAction.ADD)
    db = _make_resolve_db(row)
    service = BackgroundReviewService()
    service.add_reviewed_entry = AsyncMock(return_value="entry-9")

    out = await service.resolve_pending_write(db, pending_write_id="pw-1", approve=False)

    assert out == "rejected"
    service.add_reviewed_entry.assert_not_awaited()
    assert row.status == PendingWriteStatus.REJECTED


@pytest.mark.asyncio
async def test_resolve_pending_write_remove_records_without_delete():
    row = _pending_write_row(action=PendingWriteAction.REMOVE)
    db = _make_resolve_db(row)
    service = BackgroundReviewService()
    service.add_reviewed_entry = AsyncMock(return_value="entry-9")
    service.supersede_entry = AsyncMock(return_value="new-1")

    out = await service.resolve_pending_write(db, pending_write_id="pw-1", approve=True)

    assert out == "removed"
    service.add_reviewed_entry.assert_not_awaited()
    service.supersede_entry.assert_not_awaited()
    assert row.status == PendingWriteStatus.APPROVED


@pytest.mark.asyncio
async def test_resolve_pending_write_replace_falls_back_to_add_without_target():
    row = _pending_write_row(action=PendingWriteAction.REPLACE)
    db = _make_resolve_db(row)
    service = BackgroundReviewService()
    service.add_reviewed_entry = AsyncMock(return_value="entry-9")
    service.supersede_entry = AsyncMock(return_value="new-1")

    out = await service.resolve_pending_write(db, pending_write_id="pw-1", approve=True)

    # No target_entry_id -> treated as add (v1 behaviour).
    assert out == "entry-9"
    service.add_reviewed_entry.assert_awaited_once()
    service.supersede_entry.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_pending_write_unknown_action_returns_none():
    row = _pending_write_row(action="bogus")
    db = _make_resolve_db(row)
    service = BackgroundReviewService()

    out = await service.resolve_pending_write(db, pending_write_id="pw-1", approve=True)

    assert out is None


@pytest.mark.asyncio
async def test_resolve_pending_write_not_pending_is_noop():
    row = _pending_write_row(status=PendingWriteStatus.APPROVED)
    db = _make_resolve_db(row)
    service = BackgroundReviewService()
    service.add_reviewed_entry = AsyncMock(return_value="entry-9")

    out = await service.resolve_pending_write(db, pending_write_id="pw-1", approve=True)

    assert out is None
    service.add_reviewed_entry.assert_not_awaited()


# ── 3. expire_and_act memory-approval branch ──────────────────────────


@pytest.mark.asyncio
async def test_expire_and_act_rejects_memory_approval_without_dispatch():
    """C4: expiry of a MEMORY_APPROVAL auto-rejects the write but never resumes/aborts a mission."""
    from app.services.hitl_service import HITLService

    memory_item = SimpleNamespace(
        id="ii-mem",
        workspace_id=None,
        interrupt_type=HumanInterruptType.MEMORY_APPROVAL.value,
        context={"pending_write_id": "pw-1"},
        status=PendingWriteStatus.PENDING,
        resolved_at=None,
        resolution_note=None,
    )

    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [memory_item]
    db.execute = AsyncMock(return_value=result)
    db.flush = AsyncMock()

    with (
        patch.object(HITLService, "_emit_resolved_event", new=AsyncMock()),
        patch.object(HITLService, "_dispatch_resume", new=AsyncMock()) as dispatch,
        patch("app.services.memory.background_review_service.BackgroundReviewService") as brs_cls,
    ):
        brs_cls.return_value.resolve_pending_write = AsyncMock(return_value="rejected")
        service = HITLService(db)
        results = await service.expire_and_act()

    assert results == [
        {
            "inbox_item_id": "ii-mem",
            "workspace_id": None,
            "auto_action": "reject",
            "dispatched": False,
        }
    ]
    brs_cls.return_value.resolve_pending_write.assert_awaited_once_with(
        db, pending_write_id="pw-1", approve=False, decided_by="hitl_expiry"
    )
    dispatch.assert_not_awaited()  # memory writes must never trigger mission signals


# ── 4. API guards in app.api.v1.hitl ──────────────────────────────────
def _patch_hitl(hitl_mod, item):
    """Patch HITLService in hitl_mod so HITLService(db) returns a configured instance."""
    svc_instance = MagicMock()
    svc_instance.get_item = AsyncMock(return_value=item)
    svc_instance.resolve_interrupt = AsyncMock(return_value=item)
    svc_instance._item_to_dict = MagicMock(return_value={"id": item.id})
    svc_cls = MagicMock(return_value=svc_instance)
    return svc_cls, svc_instance


def _memory_inbox_item() -> SimpleNamespace:
    return SimpleNamespace(
        id="ii-mem",
        user_id=1,
        status=PendingWriteStatus.PENDING,
        interrupt_type=HumanInterruptType.MEMORY_APPROVAL.value,
        mission_id=None,
        run_id=None,
        context={"pending_write_id": "pw-1"},
        proposed_action={"pending_write_id": "pw-1"},
    )


@pytest.mark.asyncio
async def test_approve_item_memory_write_skips_executor_resume():
    from app.api.v1 import hitl as hitl_mod

    item = _memory_inbox_item()
    svc_cls, _ = _patch_hitl(hitl_mod, item)

    user = SimpleNamespace(id=1)
    db = AsyncMock()

    with (
        patch.object(hitl_mod, "HITLService", svc_cls),
        patch.object(hitl_mod, "_signal_executor_resume", new=AsyncMock()) as resume,
        patch.object(hitl_mod, "_signal_executor_abort", new=AsyncMock()) as abort,
        patch("app.services.memory.background_review_service.BackgroundReviewService") as brs_cls,
    ):
        brs_cls.return_value.resolve_pending_write = AsyncMock(return_value="entry-9")
        await hitl_mod.approve_item("ii-mem", None, user, db)

    brs_cls.return_value.resolve_pending_write.assert_awaited_once_with(
        db, pending_write_id="pw-1", approve=True, resolved_by=1
    )
    resume.assert_not_awaited()
    abort.assert_not_awaited()


@pytest.mark.asyncio
async def test_reject_item_memory_write_skips_executor_abort():
    from app.api.v1 import hitl as hitl_mod

    item = _memory_inbox_item()
    svc_cls, _ = _patch_hitl(hitl_mod, item)

    user = SimpleNamespace(id=1)
    db = AsyncMock()

    with (
        patch.object(hitl_mod, "HITLService", svc_cls),
        patch.object(hitl_mod, "_signal_executor_resume", new=AsyncMock()) as resume,
        patch.object(hitl_mod, "_signal_executor_abort", new=AsyncMock()) as abort,
        patch("app.services.memory.background_review_service.BackgroundReviewService") as brs_cls,
    ):
        brs_cls.return_value.resolve_pending_write = AsyncMock(return_value="rejected")
        await hitl_mod.reject_item("ii-mem", None, user, db)

    brs_cls.return_value.resolve_pending_write.assert_awaited_once_with(
        db, pending_write_id="pw-1", approve=False, resolved_by=1
    )
    resume.assert_not_awaited()
    abort.assert_not_awaited()


# ── 5. GOV-1.4 (C3): approval decisions persist to the audit trail ──


def _make_audit_db(row: SimpleNamespace) -> AsyncMock:
    """Session whose PendingWrite query returns ``row`` twice (resolve +
    audit reload) and accepts the audit service's flush()."""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=row)
    db.execute = AsyncMock(return_value=result)
    db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_resolve_approve_records_review_audit_event():
    """C3: a human APPROVE of a memory write persists a 'review' audit row."""
    from app.services.memory.background_review_service import (
        _MemoryCorrectionReviewAudit,
    )
    from app.services.memory_correction_service import MemoryCorrectionService

    row = _pending_write_row(action=PendingWriteAction.ADD, meta={"origin": "background_review"})
    db = _make_audit_db(row)

    audit = _MemoryCorrectionReviewAudit()
    svc = BackgroundReviewService()
    svc.audit = audit
    svc.add_reviewed_entry = AsyncMock(return_value="entry-9")

    with patch.object(MemoryCorrectionService, "record_event", new=AsyncMock()) as rec:
        out = await svc.resolve_pending_write(db, pending_write_id="pw-1", approve=True, resolved_by=1)

    assert out == "entry-9"
    rec.assert_awaited_once()
    kwargs = rec.call_args.kwargs
    assert kwargs["event_type"] == "review"
    assert kwargs["user_id"] == 1
    assert kwargs["workspace_id"] == "ws-1"
    assert kwargs["details"]["decision"] == "approve"
    assert kwargs["details"]["pending_write_id"] == "pw-1"
    assert kwargs["actor"] == "user"
    assert kwargs["details"]["resolved_by"] == 1
    # actions writes carry no misleading claim FK
    assert "claim_id" not in rec.call_args.args or rec.call_args.kwargs.get("claim_id") is None


@pytest.mark.asyncio
async def test_resolve_reject_records_review_audit_event():
    """C3: a human REJECT of a memory write persists a 'review' audit row."""
    from app.services.memory.background_review_service import (
        _MemoryCorrectionReviewAudit,
    )
    from app.services.memory_correction_service import MemoryCorrectionService

    row = _pending_write_row(action=PendingWriteAction.ADD)
    db = _make_audit_db(row)

    audit = _MemoryCorrectionReviewAudit()
    svc = BackgroundReviewService()
    svc.audit = audit
    svc.add_reviewed_entry = AsyncMock(return_value="entry-9")

    with patch.object(MemoryCorrectionService, "record_event", new=AsyncMock()) as rec:
        out = await svc.resolve_pending_write(db, pending_write_id="pw-1", approve=False)

    assert out == "rejected"
    rec.assert_awaited_once()
    assert rec.call_args.kwargs["event_type"] == "review"
    assert rec.call_args.kwargs["details"]["decision"] == "reject"


@pytest.mark.asyncio
async def test_default_noop_audit_records_nothing():
    """Backwards-compat: unwired service issues no audit query / no event."""
    row = _pending_write_row(action=PendingWriteAction.ADD)
    db = _make_resolve_db(row)
    svc = BackgroundReviewService()  # default _NoOpMemoryAudit
    svc.add_reviewed_entry = AsyncMock(return_value="entry-9")

    # Only one execute (the resolve query); audit must not reload the row.
    out = await svc.resolve_pending_write(db, pending_write_id="pw-1", approve=True)
    assert out == "entry-9"
    assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_expire_memory_approval_records_review_audit_event():
    """C3 + C4: expiry auto-rejects AND persists a 'review' audit row
    (decided_by=hitl_expiry), without executor dispatch."""
    from app.services.hitl_service import HITLService
    from app.services.memory.background_review_service import (
        BackgroundReviewService,
        _MemoryCorrectionReviewAudit,
    )
    from app.services.memory_correction_service import MemoryCorrectionService

    memory_item = SimpleNamespace(
        id="ii-mem",
        workspace_id=None,
        interrupt_type=HumanInterruptType.MEMORY_APPROVAL.value,
        context={"pending_write_id": "pw-1"},
        status=PendingWriteStatus.PENDING,
        resolved_at=None,
        resolution_note=None,
    )
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [memory_item]
    db.execute = AsyncMock(return_value=result)
    db.flush = AsyncMock()

    with (
        patch.object(HITLService, "_emit_resolved_event", new=AsyncMock()),
        patch.object(HITLService, "_dispatch_resume", new=AsyncMock()) as dispatch,
        patch.object(MemoryCorrectionService, "record_event", new=AsyncMock()) as rec,
        patch("app.services.memory.background_review_service.BackgroundReviewService") as brs_cls,
    ):
        # Wire the audit sink onto the resolve path used by the sweeper.
        real_svc = BackgroundReviewService()
        real_svc.audit = _MemoryCorrectionReviewAudit()
        brs_cls.return_value.resolve_pending_write = real_svc.resolve_pending_write
        service = HITLService(db)
        results = await service.expire_and_act()

    assert results == [
        {
            "inbox_item_id": "ii-mem",
            "workspace_id": None,
            "auto_action": "reject",
            "dispatched": False,
        }
    ]
    dispatch.assert_not_awaited()  # C4: never resume/abort a mission
    rec.assert_awaited_once()  # C3: expiry-as-decision is audited
    assert rec.call_args.kwargs["event_type"] == "review"
    assert rec.call_args.kwargs["details"]["decision"] == "reject"
    assert rec.call_args.kwargs["actor"] == "system"


@pytest.mark.asyncio
async def test_memory_approval_never_auto_approves():
    """Standing Decision 1: a MEMORY_APPROVAL item must expire to REJECT
    regardless of any workspace HITL auto-action=approve config. It never
    becomes an auto-approved memory write."""
    from app.services.hitl_service import HITLService

    memory_item = SimpleNamespace(
        id="ii-mem",
        workspace_id="ws-approve-by-default",
        interrupt_type=HumanInterruptType.MEMORY_APPROVAL.value,
        context={"pending_write_id": "pw-1"},
        status=PendingWriteStatus.PENDING,
        resolved_at=None,
        resolution_note=None,
    )
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [memory_item]
    db.execute = AsyncMock(return_value=result)
    db.flush = AsyncMock()

    with (
        patch.object(HITLService, "_emit_resolved_event", new=AsyncMock()),
        patch.object(HITLService, "_dispatch_resume", new=AsyncMock()) as dispatch,
        patch("app.services.memory.background_review_service.BackgroundReviewService") as brs_cls,
    ):
        brs_cls.return_value.resolve_pending_write = AsyncMock(return_value="rejected")
        service = HITLService(db)
        results = await service.expire_and_act()

    # Even though the workspace config could say "approve", memory writes
    # are hardcoded to reject on expiry (the only path to audited
    # expiry-as-decision, per C4 / Standing Decision 1).
    assert results[0]["auto_action"] == "reject"
    brs_cls.return_value.resolve_pending_write.assert_awaited_once_with(
        db, pending_write_id="pw-1", approve=False, decided_by="hitl_expiry"
    )
