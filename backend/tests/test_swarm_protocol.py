"""Integration tests for swarm protocol API endpoints.

Tests all 12 endpoints: debate (2), handoff (6), escalation (4).
Validates route registration, request validation, response shapes, and error handling.
Uses synchronous TestClient (project convention) with mocked services.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Mock factories (cannot live in conftest — not importable in pytest) ────


def _make_mock_debate_round(**overrides):
    defaults = {
        "debate_id": "debate-001",
        "round_number": 1,
        "position_a": "Position A argues for X",
        "position_b": "Position B argues for Y",
        "rebuttal_a": "Rebuttal to B",
        "rebuttal_b": "Rebuttal to A",
        "judge_verdict": "a_wins",
        "judge_score_a": 8.5,
        "judge_score_b": 6.0,
        "judge_reasoning": "Agent A had stronger arguments",
        "consensus_reached": True,
        "consensus_synthesis": "Synthesized position combining both views",
        "consensus_score": 0.85,
        "status": "completed",
        "created_at": None,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def _make_mock_handoff(**overrides):
    defaults = {
        "id": "handoff-001",
        "from_agent_id": "agent-a",
        "from_agent_name": "Agent A",
        "to_agent_id": "agent-b",
        "to_agent_name": "Agent B",
        "task_description": "Analyze Q3 reports",
        "status": "pending",
        "priority": 1,
        "created_at": None,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def _make_mock_escalation(**overrides):
    defaults = {
        "id": "esc-001",
        "task_id": "task-001",
        "task_description": "Failed data extraction",
        "level": 1,
        "status": "escalated",
        "escalated_to_agent_name": "Specialist Agent",
        "resolved": False,
        "error_message": "Timeout exceeded",
        "created_at": None,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


# ═══════════════════════════════════════════════════════════════════════════
# Debate endpoints
# ═══════════════════════════════════════════════════════════════════════════


class TestDebate:
    """POST /debate and GET /debate/{id}"""

    # ── POST /debate ────────────────────────────────────────────────

    def test_start_debate_success(self, test_client):
        """Start a debate returns correct shape with consensus reached."""
        mock_round = _make_mock_debate_round()

        with patch("app.api.v1.swarm_protocol.DebateProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.debate = AsyncMock(return_value=mock_round)

            payload = {
                "topic": "Is Python better than JavaScript?",
                "agent_a_id": "a1",
                "agent_a_name": "Python Advocate",
                "agent_b_id": "b1",
                "agent_b_name": "JS Advocate",
            }
            resp = test_client.post("/api/swarm/protocol/debate", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["debate_id"] == "debate-001"
        assert data["round_number"] == 1
        assert data["judge_verdict"] == "a_wins"
        assert data["judge_score_a"] == 8.5
        assert data["judge_score_b"] == 6.0
        assert data["consensus_reached"] is True
        assert (
            data["consensus_synthesis"] == "Synthesized position combining both views"
        )
        assert data["status"] == "completed"

    def test_start_debate_with_max_rounds(self, test_client):
        """Custom max_rounds is passed through."""
        mock_round = _make_mock_debate_round()

        with patch("app.api.v1.swarm_protocol.DebateProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.debate = AsyncMock(return_value=mock_round)

            payload = {
                "topic": "Test topic",
                "agent_a_id": "a1",
                "agent_a_name": "A",
                "agent_b_id": "b1",
                "agent_b_name": "B",
                "max_rounds": 3,
            }
            resp = test_client.post("/api/swarm/protocol/debate", json=payload)

        assert resp.status_code == 200
        mock_proto.debate.assert_called_once()
        call_kwargs = mock_proto.debate.call_args.kwargs
        assert call_kwargs["max_rounds"] == 3

    def test_start_debate_validation_topic_required(self, test_client):
        """Missing topic returns 422."""
        payload = {
            "agent_a_id": "a1",
            "agent_a_name": "A",
            "agent_b_id": "b1",
            "agent_b_name": "B",
        }
        resp = test_client.post("/api/swarm/protocol/debate", json=payload)
        assert resp.status_code == 422

    def test_start_debate_validation_invalid_max_rounds(self, test_client):
        """max_rounds outside 1-5 range returns 422."""
        payload = {
            "topic": "Test",
            "agent_a_id": "a1",
            "agent_a_name": "A",
            "agent_b_id": "b1",
            "agent_b_name": "B",
            "max_rounds": 10,
        }
        resp = test_client.post("/api/swarm/protocol/debate", json=payload)
        assert resp.status_code == 422

    def test_start_debate_boundary_max_rounds_one(self, test_client):
        """Boundary: max_rounds=1 passes validation."""
        mock_round = _make_mock_debate_round()

        with patch("app.api.v1.swarm_protocol.DebateProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.debate = AsyncMock(return_value=mock_round)

            payload = {
                "topic": "Test",
                "agent_a_id": "a1",
                "agent_a_name": "A",
                "agent_b_id": "b1",
                "agent_b_name": "B",
                "max_rounds": 1,
            }
            resp = test_client.post("/api/swarm/protocol/debate", json=payload)

        assert resp.status_code == 200
        assert mock_proto.debate.call_args.kwargs["max_rounds"] == 1

    def test_start_debate_boundary_max_rounds_five(self, test_client):
        """Boundary: max_rounds=5 passes validation."""
        mock_round = _make_mock_debate_round()

        with patch("app.api.v1.swarm_protocol.DebateProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.debate = AsyncMock(return_value=mock_round)

            payload = {
                "topic": "Test",
                "agent_a_id": "a1",
                "agent_a_name": "A",
                "agent_b_id": "b1",
                "agent_b_name": "B",
                "max_rounds": 5,
            }
            resp = test_client.post("/api/swarm/protocol/debate", json=payload)

        assert resp.status_code == 200
        assert mock_proto.debate.call_args.kwargs["max_rounds"] == 5

    def test_start_debate_service_failure(self, test_client):
        """Service exception returns 500."""
        with patch("app.api.v1.swarm_protocol.DebateProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.debate = AsyncMock(side_effect=RuntimeError("LLM timeout"))

            payload = {
                "topic": "Test",
                "agent_a_id": "a1",
                "agent_a_name": "A",
                "agent_b_id": "b1",
                "agent_b_name": "B",
            }
            resp = test_client.post("/api/swarm/protocol/debate", json=payload)

        assert resp.status_code == 500
        assert "LLM timeout" in resp.json()["detail"]

    def test_start_debate_validation_topic_too_long(self, test_client):
        """Topic exceeding max_length=5000 returns 422."""
        payload = {
            "topic": "x" * 5001,
            "agent_a_id": "a1",
            "agent_a_name": "A",
            "agent_b_id": "b1",
            "agent_b_name": "B",
        }
        resp = test_client.post("/api/swarm/protocol/debate", json=payload)
        assert resp.status_code == 422

    def test_start_debate_validation_topic_at_boundary(self, test_client):
        """Topic exactly 5000 chars is accepted."""
        mock_round = _make_mock_debate_round()

        with patch("app.api.v1.swarm_protocol.DebateProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.debate = AsyncMock(return_value=mock_round)

            payload = {
                "topic": "x" * 5000,
                "agent_a_id": "a1",
                "agent_a_name": "A",
                "agent_b_id": "b1",
                "agent_b_name": "B",
            }
            resp = test_client.post("/api/swarm/protocol/debate", json=payload)

        assert resp.status_code == 200

    def test_start_debate_validation_topic_empty(self, test_client):
        """Empty topic returns 422 (min_length=1)."""
        payload = {
            "topic": "",
            "agent_a_id": "a1",
            "agent_a_name": "A",
            "agent_b_id": "b1",
            "agent_b_name": "B",
        }
        resp = test_client.post("/api/swarm/protocol/debate", json=payload)
        assert resp.status_code == 422

    # ── GET /debate/{id} ────────────────────────────────────────────

    def test_get_debate_success(self, test_client):
        """Get debate returns rounds array."""
        mock_round = _make_mock_debate_round()
        mock_round2 = _make_mock_debate_round(
            debate_id="debate-001",
            round_number=2,
            judge_verdict="deadlock",
            consensus_reached=False,
            consensus_synthesis=None,
            status="deadlocked",
        )

        with patch("app.api.v1.swarm_protocol.DebateProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.get_debate = AsyncMock(return_value=[mock_round, mock_round2])

            resp = test_client.get("/api/swarm/protocol/debate/debate-001")

        assert resp.status_code == 200
        data = resp.json()
        assert data["debate_id"] == "debate-001"
        assert len(data["rounds"]) == 2
        assert data["rounds"][0]["round_number"] == 1
        assert data["rounds"][1]["round_number"] == 2
        r0 = data["rounds"][0]
        assert "position_a" in r0
        assert "position_b" in r0
        assert "rebuttal_a" in r0
        assert "rebuttal_b" in r0
        assert "judge_verdict" in r0
        assert "judge_score_a" in r0
        assert "judge_score_b" in r0
        assert "judge_reasoning" in r0
        assert "consensus_reached" in r0
        assert "consensus_synthesis" in r0
        assert "consensus_score" in r0
        assert "status" in r0

    def test_get_debate_not_found(self, test_client):
        """Non-existent debate returns 404."""
        with patch("app.api.v1.swarm_protocol.DebateProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.get_debate = AsyncMock(return_value=[])

            resp = test_client.get("/api/swarm/protocol/debate/nonexistent")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Debate not found"


# ═══════════════════════════════════════════════════════════════════════════
# Handoff endpoints
# ═══════════════════════════════════════════════════════════════════════════


class TestHandoff:
    """6 endpoints: delegate, accept, complete, reject, list, chain."""

    # ── POST /handoff/delegate ──────────────────────────────────────

    def test_delegate_success(self, test_client):
        """Delegate creates a handoff and returns correct shape."""
        mock_h = _make_mock_handoff()

        with patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.delegate = AsyncMock(return_value=mock_h)

            payload = {
                "from_agent_id": "agent-a",
                "from_agent_name": "Agent A",
                "task_description": "Analyze Q3 reports",
            }
            resp = test_client.post(
                "/api/swarm/protocol/handoff/delegate", json=payload
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["handoff_id"] == "handoff-001"
        assert data["from"] == "Agent A"
        assert data["to"] == "Agent B"
        assert data["task"] == "Analyze Q3 reports"
        assert data["task_description"] == "Analyze Q3 reports"
        assert data["status"] == "pending"
        assert data["priority"] == 1

    def test_delegate_validation_task_required(self, test_client):
        """Missing task_description returns 422."""
        payload = {
            "from_agent_id": "agent-a",
            "from_agent_name": "Agent A",
        }
        resp = test_client.post("/api/swarm/protocol/handoff/delegate", json=payload)
        assert resp.status_code == 422

    def test_delegate_no_agent_match(self, test_client):
        """ValueError from service (no agent match) returns 400."""
        with patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.delegate = AsyncMock(
                side_effect=ValueError("No agent found for task")
            )

            payload = {
                "from_agent_id": "agent-a",
                "from_agent_name": "Agent A",
                "task_description": "Unmatchable task",
            }
            resp = test_client.post(
                "/api/swarm/protocol/handoff/delegate", json=payload
            )

        assert resp.status_code == 400
        assert "No agent found" in resp.json()["detail"]

    def test_delegate_service_failure(self, test_client):
        """Generic service exception returns 500."""
        with patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.delegate = AsyncMock(
                side_effect=RuntimeError("Database connection lost")
            )

            payload = {
                "from_agent_id": "agent-a",
                "from_agent_name": "Agent A",
                "task_description": "Test task",
            }
            resp = test_client.post(
                "/api/swarm/protocol/handoff/delegate", json=payload
            )

        assert resp.status_code == 500
        assert "Database connection lost" in resp.json()["detail"]

    def test_delegate_with_to_agent(self, test_client):
        """Delegate passes to_agent_id when provided."""
        mock_h = _make_mock_handoff()

        with patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.delegate = AsyncMock(return_value=mock_h)

            payload = {
                "from_agent_id": "agent-a",
                "from_agent_name": "Agent A",
                "task_description": "Test task",
                "to_agent_id": "agent-c",
                "priority": 2,
            }
            resp = test_client.post(
                "/api/swarm/protocol/handoff/delegate", json=payload
            )

        assert resp.status_code == 200
        mock_proto.delegate.assert_called_once()
        call_kwargs = mock_proto.delegate.call_args.kwargs
        assert call_kwargs["to_agent_id"] == "agent-c"
        assert call_kwargs["priority"] == 2

    # ── POST /handoff/{id}/accept ───────────────────────────────────

    def test_accept_success(self, test_client):
        """Accept returns updated handoff."""
        mock_h = _make_mock_handoff(status="accepted")

        with patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.accept = AsyncMock(return_value=mock_h)

            resp = test_client.post("/api/swarm/protocol/handoff/handoff-001/accept")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"

    def test_accept_not_found(self, test_client):
        """Accept non-existent handoff returns 404."""
        with patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.accept = AsyncMock(return_value=None)

            resp = test_client.post("/api/swarm/protocol/handoff/nonexistent/accept")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Handoff not found"

    # ── POST /handoff/{id}/complete ─────────────────────────────────

    def test_complete_success(self, test_client):
        """Complete with result returns updated handoff."""
        mock_h = _make_mock_handoff(status="completed")

        with patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.complete = AsyncMock(return_value=mock_h)

            resp = test_client.post(
                "/api/swarm/protocol/handoff/handoff-001/complete",
                json={"result": "Analysis complete: 42"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        mock_proto.complete.assert_called_once()
        call_kwargs = mock_proto.complete.call_args.kwargs
        assert call_kwargs["result"] == "Analysis complete: 42"

    def test_complete_not_found(self, test_client):
        """Complete non-existent handoff returns 404."""
        with patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.complete = AsyncMock(return_value=None)

            resp = test_client.post(
                "/api/swarm/protocol/handoff/nonexistent/complete",
                json={"result": "done"},
            )

        assert resp.status_code == 404

    # ── POST /handoff/{id}/reject ───────────────────────────────────

    def test_reject_success(self, test_client):
        """Reject with reason returns updated handoff."""
        mock_h = _make_mock_handoff(status="rejected")

        with patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.reject = AsyncMock(return_value=mock_h)

            resp = test_client.post(
                "/api/swarm/protocol/handoff/handoff-001/reject",
                json={"reason": "Not my expertise"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rejected"
        mock_proto.reject.assert_called_once()
        call_kwargs = mock_proto.reject.call_args.kwargs
        assert call_kwargs["reason"] == "Not my expertise"

    def test_reject_default_reason(self, test_client):
        """Reject without reason uses default."""
        mock_h = _make_mock_handoff(status="rejected")

        with patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.reject = AsyncMock(return_value=mock_h)

            resp = test_client.post(
                "/api/swarm/protocol/handoff/handoff-001/reject", json={}
            )

        assert resp.status_code == 200
        mock_proto.reject.assert_called_once()
        call_kwargs = mock_proto.reject.call_args.kwargs
        assert call_kwargs["reason"] == "Agent declined the handoff"

    # ── GET /handoffs ───────────────────────────────────────────────

    def test_list_handoffs_success(self, test_client):
        """List handoffs returns correct envelope."""
        mock_h1 = _make_mock_handoff(id="h1")
        mock_h2 = _make_mock_handoff(
            id="h2", from_agent_name="Agent C", status="completed"
        )

        with patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.list_handoffs = AsyncMock(return_value=[mock_h1, mock_h2])

            resp = test_client.get("/api/swarm/protocol/handoffs")

        assert resp.status_code == 200
        data = resp.json()
        assert "handoffs" in data
        assert len(data["handoffs"]) == 2
        assert data["handoffs"][0]["handoff_id"] == "h1"
        assert data["handoffs"][1]["handoff_id"] == "h2"

    def test_list_handoffs_with_filters(self, test_client):
        """Query params are passed to service."""
        with patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.list_handoffs = AsyncMock(return_value=[])

            resp = test_client.get(
                "/api/swarm/protocol/handoffs",
                params={"status": "pending", "limit": 5},
            )

        assert resp.status_code == 200
        mock_proto.list_handoffs.assert_called_once()
        call_kwargs = mock_proto.list_handoffs.call_args.kwargs
        assert call_kwargs["status"] == "pending"
        assert call_kwargs["limit"] == 5

    def test_list_handoffs_empty(self, test_client):
        """Empty list returns empty handoffs array."""
        with patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.list_handoffs = AsyncMock(return_value=[])

            resp = test_client.get("/api/swarm/protocol/handoffs")

        assert resp.status_code == 200
        assert resp.json() == {"handoffs": []}

    # ── GET /handoff/{id}/chain ─────────────────────────────────────

    def test_get_chain_success(self, test_client):
        """Get handoff chain returns ordered chain."""
        root = _make_mock_handoff(id="root", task_description="Root task")
        child = _make_mock_handoff(id="child", task_description="Child task")

        with patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.get_chain = AsyncMock(return_value=[root, child])

            resp = test_client.get("/api/swarm/protocol/handoff/root/chain")

        assert resp.status_code == 200
        data = resp.json()
        assert data["handoff_id"] == "root"
        assert len(data["chain"]) == 2
        assert data["chain"][0]["handoff_id"] == "root"
        assert data["chain"][1]["handoff_id"] == "child"

    def test_get_chain_empty(self, test_client):
        """Empty chain returns empty list under handoff_id."""
        with patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.get_chain = AsyncMock(return_value=[])

            resp = test_client.get("/api/swarm/protocol/handoff/any-id/chain")

        assert resp.status_code == 200
        data = resp.json()
        assert data["handoff_id"] == "any-id"
        assert data["chain"] == []

    # ── Field mapping edge cases ────────────────────────────────────

    def test_handoff_with_null_names_fallback_to_ids(self, test_client):
        """When agent names are None, 'from'/'to' fall back to agent IDs."""
        mock_h = _make_mock_handoff(
            from_agent_name=None,
            to_agent_name=None,
            from_agent_id="agent-x",
            to_agent_id="agent-y",
        )

        with patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.delegate = AsyncMock(return_value=mock_h)

            payload = {
                "from_agent_id": "agent-x",
                "from_agent_name": "X",
                "task_description": "Test",
            }
            resp = test_client.post(
                "/api/swarm/protocol/handoff/delegate", json=payload
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["from"] == "agent-x"
        assert data["to"] == "agent-y"

    # ── Validation edge cases: task_description boundaries ──────────

    def test_delegate_validation_task_too_long(self, test_client):
        """Task description exceeding max_length=5000 returns 422."""
        payload = {
            "from_agent_id": "agent-a",
            "from_agent_name": "Agent A",
            "task_description": "x" * 5001,
        }
        resp = test_client.post("/api/swarm/protocol/handoff/delegate", json=payload)
        assert resp.status_code == 422

    def test_delegate_validation_task_at_boundary(self, test_client):
        """Task description exactly 5000 chars is accepted."""
        mock_h = _make_mock_handoff(task_description="x" * 5000)

        with patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.delegate = AsyncMock(return_value=mock_h)

            payload = {
                "from_agent_id": "agent-a",
                "from_agent_name": "Agent A",
                "task_description": "x" * 5000,
            }
            resp = test_client.post(
                "/api/swarm/protocol/handoff/delegate", json=payload
            )

        assert resp.status_code == 200

    def test_delegate_validation_task_empty(self, test_client):
        """Empty task_description returns 422 (min_length=1)."""
        payload = {
            "from_agent_id": "agent-a",
            "from_agent_name": "Agent A",
            "task_description": "",
        }
        resp = test_client.post("/api/swarm/protocol/handoff/delegate", json=payload)
        assert resp.status_code == 422

    # ── Validation edge cases: priority boundaries ──────────────────

    @pytest.mark.parametrize("priority", [-2, 3])
    def test_delegate_validation_priority_out_of_range(self, test_client, priority):
        """Priority outside -1..2 returns 422."""
        payload = {
            "from_agent_id": "agent-a",
            "from_agent_name": "Agent A",
            "task_description": "Test",
            "priority": priority,
        }
        resp = test_client.post("/api/swarm/protocol/handoff/delegate", json=payload)
        assert (
            resp.status_code == 422
        ), f"priority={priority} should return 422, got {resp.status_code}"

    @pytest.mark.parametrize("priority", [-1, 2])
    def test_delegate_validation_priority_boundaries(self, test_client, priority):
        """Priority at boundaries -1 and 2 is accepted."""
        mock_h = _make_mock_handoff()

        with patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.delegate = AsyncMock(return_value=mock_h)

            payload = {
                "from_agent_id": "agent-a",
                "from_agent_name": "Agent A",
                "task_description": "Test",
                "priority": priority,
            }
            resp = test_client.post(
                "/api/swarm/protocol/handoff/delegate", json=payload
            )

        assert (
            resp.status_code == 200
        ), f"priority={priority} should be accepted, got {resp.status_code}"
        call_kwargs = mock_proto.delegate.call_args.kwargs
        assert call_kwargs["priority"] == priority

    # ── Validation edge cases: limit out of range ───────────────────

    @pytest.mark.parametrize("limit", [0, 101])
    def test_list_handoffs_limit_out_of_range(self, test_client, limit):
        """Limit outside 1-100 returns 422."""
        resp = test_client.get("/api/swarm/protocol/handoffs", params={"limit": limit})
        assert (
            resp.status_code == 422
        ), f"limit={limit} should return 422, got {resp.status_code}"


# ═══════════════════════════════════════════════════════════════════════════
# Escalation endpoints
# ═══════════════════════════════════════════════════════════════════════════


class TestEscalation:
    """4 endpoints: escalate, resolve, list escalations, dead-letters."""

    # ── POST /escalate ──────────────────────────────────────────────

    def test_escalate_success(self, test_client):
        """Escalate creates record and returns correct shape."""
        mock_e = _make_mock_escalation()

        with patch("app.api.v1.swarm_protocol.EscalationChain") as mock_chain_cls:
            mock_chain = mock_chain_cls.return_value
            mock_chain.escalate = AsyncMock(return_value=mock_e)

            payload = {
                "task_id": "task-001",
                "task_description": "Failed data extraction",
                "error_message": "Timeout exceeded",
            }
            resp = test_client.post("/api/swarm/protocol/escalate", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["escalation_id"] == "esc-001"
        assert data["task_id"] == "task-001"
        assert data["task_description"] == "Failed data extraction"
        assert data["level"] == 1
        assert data["status"] == "escalated"
        assert data["escalated_to"] == "Specialist Agent"
        assert data["resolved"] is False
        assert data["error_message"] == "Timeout exceeded"

    def test_escalate_with_policy(self, test_client):
        """Policy parameter is passed to service."""
        mock_e = _make_mock_escalation()

        with patch("app.api.v1.swarm_protocol.EscalationChain") as mock_chain_cls:
            mock_chain = mock_chain_cls.return_value
            mock_chain.escalate = AsyncMock(return_value=mock_e)

            payload = {
                "task_id": "task-001",
                "task_description": "test",
                "error_message": "error",
                "policy": "aggressive",
            }
            resp = test_client.post("/api/swarm/protocol/escalate", json=payload)

        assert resp.status_code == 200
        mock_chain.escalate.assert_called_once()
        call_kwargs = mock_chain.escalate.call_args.kwargs
        assert call_kwargs["policy"] == "aggressive"

    def test_escalate_validation_invalid_policy(self, test_client):
        """Invalid policy value returns 422."""
        payload = {
            "task_id": "task-001",
            "task_description": "test",
            "error_message": "error",
            "policy": "invalid_policy",
        }
        resp = test_client.post("/api/swarm/protocol/escalate", json=payload)
        assert resp.status_code == 422

    def test_escalate_validation_task_description_required(self, test_client):
        """Missing task_description returns 422."""
        payload = {
            "task_id": "task-001",
            "error_message": "error",
        }
        resp = test_client.post("/api/swarm/protocol/escalate", json=payload)
        assert resp.status_code == 422

    def test_escalate_service_failure(self, test_client):
        """Generic service exception returns 500."""
        with patch("app.api.v1.swarm_protocol.EscalationChain") as mock_chain_cls:
            mock_chain = mock_chain_cls.return_value
            mock_chain.escalate = AsyncMock(
                side_effect=RuntimeError("Dead-letter queue full")
            )

            payload = {
                "task_id": "task-001",
                "task_description": "test",
                "error_message": "error",
            }
            resp = test_client.post("/api/swarm/protocol/escalate", json=payload)

        assert resp.status_code == 500
        assert "Dead-letter queue full" in resp.json()["detail"]

    # ── POST /escalate/{id}/resolve ─────────────────────────────────

    def test_resolve_success(self, test_client):
        """Resolve marks escalation as resolved."""
        mock_e = _make_mock_escalation(resolved=True, status="resolved")

        with patch("app.api.v1.swarm_protocol.EscalationChain") as mock_chain_cls:
            mock_chain = mock_chain_cls.return_value
            mock_chain.resolve = AsyncMock(return_value=mock_e)

            resp = test_client.post(
                "/api/swarm/protocol/escalate/esc-001/resolve",
                json={"resolution_output": "Fixed by increasing timeout"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["resolved"] is True
        assert data["status"] == "resolved"
        mock_chain.resolve.assert_called_once()
        call_kwargs = mock_chain.resolve.call_args.kwargs
        assert call_kwargs["resolution_output"] == "Fixed by increasing timeout"

    def test_resolve_not_found(self, test_client):
        """Resolve non-existent escalation returns 404."""
        with patch("app.api.v1.swarm_protocol.EscalationChain") as mock_chain_cls:
            mock_chain = mock_chain_cls.return_value
            mock_chain.resolve = AsyncMock(return_value=None)

            resp = test_client.post(
                "/api/swarm/protocol/escalate/nonexistent/resolve",
                json={"resolution_output": "done"},
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Escalation not found"

    # ── GET /escalations ────────────────────────────────────────────

    def test_list_escalations_success(self, test_client):
        """List escalations returns correct envelope."""
        mock_e1 = _make_mock_escalation(id="e1")
        mock_e2 = _make_mock_escalation(
            id="e2", resolved=True, status="resolved", level=3
        )

        with patch("app.api.v1.swarm_protocol.EscalationChain") as mock_chain_cls:
            mock_chain = mock_chain_cls.return_value
            mock_chain.list_escalations = AsyncMock(return_value=[mock_e1, mock_e2])

            resp = test_client.get("/api/swarm/protocol/escalations")

        assert resp.status_code == 200
        data = resp.json()
        assert "escalations" in data
        assert len(data["escalations"]) == 2
        assert data["escalations"][0]["escalation_id"] == "e1"
        assert data["escalations"][1]["escalation_id"] == "e2"

    def test_list_escalations_filter_resolved(self, test_client):
        """Filter by resolved=true param."""
        with patch("app.api.v1.swarm_protocol.EscalationChain") as mock_chain_cls:
            mock_chain = mock_chain_cls.return_value
            mock_chain.list_escalations = AsyncMock(return_value=[])

            resp = test_client.get(
                "/api/swarm/protocol/escalations",
                params={"resolved": "true"},
            )

        assert resp.status_code == 200
        mock_chain.list_escalations.assert_called_once()
        call_kwargs = mock_chain.list_escalations.call_args.kwargs
        assert call_kwargs["resolved"] is True

    def test_list_escalations_filter_unresolved(self, test_client):
        """Filter by resolved=false param (coercion both ways)."""
        with patch("app.api.v1.swarm_protocol.EscalationChain") as mock_chain_cls:
            mock_chain = mock_chain_cls.return_value
            mock_chain.list_escalations = AsyncMock(return_value=[])

            resp = test_client.get(
                "/api/swarm/protocol/escalations",
                params={"resolved": "false"},
            )

        assert resp.status_code == 200
        mock_chain.list_escalations.assert_called_once()
        call_kwargs = mock_chain.list_escalations.call_args.kwargs
        assert call_kwargs["resolved"] is False

    def test_list_escalations_empty(self, test_client):
        """Empty escalations returns empty list."""
        with patch("app.api.v1.swarm_protocol.EscalationChain") as mock_chain_cls:
            mock_chain = mock_chain_cls.return_value
            mock_chain.list_escalations = AsyncMock(return_value=[])

            resp = test_client.get("/api/swarm/protocol/escalations")

        assert resp.status_code == 200
        assert resp.json() == {"escalations": []}

    # ── GET /dead-letters ───────────────────────────────────────────

    def test_list_dead_letters_success(self, test_client):
        """List dead letters returns correct envelope."""
        mock_dl = _make_mock_escalation(
            id="dl-001", status="dead_letter", level=3, resolved=True
        )

        with patch("app.api.v1.swarm_protocol.EscalationChain") as mock_chain_cls:
            mock_chain = mock_chain_cls.return_value
            mock_chain.list_dead_letters = AsyncMock(return_value=[mock_dl])

            resp = test_client.get("/api/swarm/protocol/dead-letters")

        assert resp.status_code == 200
        data = resp.json()
        assert "dead_letters" in data
        assert len(data["dead_letters"]) == 1
        assert data["dead_letters"][0]["escalation_id"] == "dl-001"
        assert data["dead_letters"][0]["status"] == "dead_letter"

    def test_list_dead_letters_with_limit(self, test_client):
        """Limit query param is passed."""
        with patch("app.api.v1.swarm_protocol.EscalationChain") as mock_chain_cls:
            mock_chain = mock_chain_cls.return_value
            mock_chain.list_dead_letters = AsyncMock(return_value=[])

            resp = test_client.get(
                "/api/swarm/protocol/dead-letters", params={"limit": 5}
            )

        assert resp.status_code == 200
        mock_chain.list_dead_letters.assert_called_once()
        call_kwargs = mock_chain.list_dead_letters.call_args.kwargs
        assert call_kwargs["limit"] == 5

    def test_list_dead_letters_empty(self, test_client):
        """Empty dead letters returns empty list."""
        with patch("app.api.v1.swarm_protocol.EscalationChain") as mock_chain_cls:
            mock_chain = mock_chain_cls.return_value
            mock_chain.list_dead_letters = AsyncMock(return_value=[])

            resp = test_client.get("/api/swarm/protocol/dead-letters")

        assert resp.status_code == 200
        assert resp.json() == {"dead_letters": []}

    # ── Escalation field mapping edge case ──────────────────────────

    def test_escalation_with_null_agent_name(self, test_client):
        """When escalated_to_agent_name is None, escalated_to is None."""
        mock_e = _make_mock_escalation(
            escalated_to_agent_name=None,
            status="dead_letter",
        )

        with patch("app.api.v1.swarm_protocol.EscalationChain") as mock_chain_cls:
            mock_chain = mock_chain_cls.return_value
            mock_chain.escalate = AsyncMock(return_value=mock_e)

            payload = {
                "task_id": "task-001",
                "task_description": "test",
                "error_message": "error",
            }
            resp = test_client.post("/api/swarm/protocol/escalate", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["escalated_to"] is None

    # ── Validation edge cases: task_description boundaries ──────────

    def test_escalate_validation_task_too_long(self, test_client):
        """Task description exceeding max_length=5000 returns 422."""
        payload = {
            "task_id": "task-001",
            "task_description": "x" * 5001,
            "error_message": "error",
        }
        resp = test_client.post("/api/swarm/protocol/escalate", json=payload)
        assert resp.status_code == 422

    def test_escalate_validation_task_at_boundary(self, test_client):
        """Task description exactly 5000 chars is accepted."""
        mock_e = _make_mock_escalation()

        with patch("app.api.v1.swarm_protocol.EscalationChain") as mock_chain_cls:
            mock_chain = mock_chain_cls.return_value
            mock_chain.escalate = AsyncMock(return_value=mock_e)

            payload = {
                "task_id": "task-001",
                "task_description": "x" * 5000,
                "error_message": "error",
            }
            resp = test_client.post("/api/swarm/protocol/escalate", json=payload)

        assert resp.status_code == 200

    def test_escalate_validation_task_empty(self, test_client):
        """Empty task_description returns 422 (min_length=1)."""
        payload = {
            "task_id": "task-001",
            "task_description": "",
            "error_message": "error",
        }
        resp = test_client.post("/api/swarm/protocol/escalate", json=payload)
        assert resp.status_code == 422

    # ── Validation edge cases: limit out of range ───────────────────

    @pytest.mark.parametrize("limit", [0, 101])
    def test_list_escalations_limit_out_of_range(self, test_client, limit):
        """Limit outside 1-100 returns 422."""
        resp = test_client.get(
            "/api/swarm/protocol/escalations", params={"limit": limit}
        )
        assert (
            resp.status_code == 422
        ), f"limit={limit} should return 422, got {resp.status_code}"

    @pytest.mark.parametrize("limit", [0, 101])
    def test_list_dead_letters_limit_out_of_range(self, test_client, limit):
        """Dead-letters limit outside 1-100 returns 422."""
        resp = test_client.get(
            "/api/swarm/protocol/dead-letters", params={"limit": limit}
        )
        assert (
            resp.status_code == 422
        ), f"limit={limit} should return 422, got {resp.status_code}"


# ═══════════════════════════════════════════════════════════════════════════
# Cross-cutting: route registration & method validation
# ═══════════════════════════════════════════════════════════════════════════


class TestRouteRegistration:
    """Verify all 12 endpoints are registered at the expected paths."""

    @pytest.mark.parametrize(
        "method, path, expected_status",
        [
            # GET endpoints should return 200 with mocks
            ("GET", "/api/swarm/protocol/handoffs", 200),
            ("GET", "/api/swarm/protocol/escalations", 200),
            ("GET", "/api/swarm/protocol/dead-letters", 200),
            # POST endpoints should return 422 (missing body) not 405/404
            ("POST", "/api/swarm/protocol/debate", 422),
            ("POST", "/api/swarm/protocol/handoff/delegate", 422),
            ("POST", "/api/swarm/protocol/escalate", 422),
        ],
    )
    def test_endpoint_registered(self, test_client, method, path, expected_status):
        """Endpoint returns expected status (not 404)."""
        # Patch services so GET endpoints don't error trying to use real DB
        with (
            patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_hp,
            patch("app.api.v1.swarm_protocol.EscalationChain") as mock_ec,
        ):
            mock_hp.return_value.list_handoffs = AsyncMock(return_value=[])
            mock_ec.return_value.list_escalations = AsyncMock(return_value=[])
            mock_ec.return_value.list_dead_letters = AsyncMock(return_value=[])

            if method == "GET":
                resp = test_client.get(path)
            else:
                resp = test_client.post(path, json={})
            assert (
                resp.status_code == expected_status
            ), f"Expected {expected_status} for {method} {path}, got {resp.status_code}"

    def test_parameterized_routes_exist(self, test_client):
        """Parameterized routes return 404 for non-existent IDs (route itself exists)."""
        # GET debate/{id}
        with patch("app.api.v1.swarm_protocol.DebateProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.get_debate = AsyncMock(return_value=[])

            resp = test_client.get("/api/swarm/protocol/debate/test-id")
            assert resp.status_code == 404  # service-level not-found

        # POST handoff/{id}/accept
        with patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.accept = AsyncMock(return_value=None)

            resp = test_client.post("/api/swarm/protocol/handoff/test-id/accept")
            assert resp.status_code == 404

        # POST escalate/{id}/resolve
        with patch("app.api.v1.swarm_protocol.EscalationChain") as mock_chain_cls:
            mock_chain = mock_chain_cls.return_value
            mock_chain.resolve = AsyncMock(return_value=None)

            resp = test_client.post(
                "/api/swarm/protocol/escalate/test-id/resolve",
                json={"resolution_output": "done"},
            )
            assert resp.status_code == 404

        # GET handoff/{id}/chain
        with patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_proto_cls:
            mock_proto = mock_proto_cls.return_value
            mock_proto.get_chain = AsyncMock(return_value=[])

            resp = test_client.get("/api/swarm/protocol/handoff/test-id/chain")
            assert resp.status_code == 200  # empty chain is valid
