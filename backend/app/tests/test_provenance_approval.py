"""Tests for GOV-1.2 provenance-gated approval policy.

The reliable control: only ``user_explicit`` claims may bypass human
approval; every externally-derived source_type (and unknown/None) MUST be
routed to approval. Confidence is intentionally NOT an input — a high
confidence external claim is still external.
"""

from app.services.memory.provenance_approval import (
    EXTERNALLY_DERIVED_SOURCES,
    USER_AUTHORED_SOURCES,
    requires_provenance_approval,
    requires_provenance_approval_for_claim,
)


class TestRequiresProvenanceApproval:
    def test_user_explicit_bypasses(self):
        assert requires_provenance_approval("user_explicit") is False

    def test_externally_derived_never_bypass(self):
        for src in EXTERNALLY_DERIVED_SOURCES:
            assert requires_provenance_approval(src) is True, src

    def test_conversation_always_requires(self):
        # The chat extractor's default provenance → must be staged.
        assert requires_provenance_approval("conversation") is True

    def test_mission_always_requires(self):
        assert requires_provenance_approval("mission") is True

    def test_program_learning_always_requires(self):
        assert requires_provenance_approval("program_learning") is True

    def test_unknown_source_fails_safe(self):
        # An unrecognized source_type must NOT auto-write.
        assert requires_provenance_approval("totally_made_up") is True

    def test_none_source_fails_safe(self):
        # Missing provenance → ask the human, never auto-write.
        assert requires_provenance_approval(None) is True

    def test_empty_string_fails_safe(self):
        assert requires_provenance_approval("") is True


class TestRequiresProvenanceApprovalForClaim:
    def _claim(self, source_type):
        class C:
            pass

        c = C()
        c.source_type = source_type
        return c

    def test_user_explicit_claim_bypasses(self):
        assert requires_provenance_approval_for_claim(self._claim("user_explicit")) is False

    def test_conversation_claim_requires(self):
        assert requires_provenance_approval_for_claim(self._claim("conversation")) is True

    def test_missing_source_type_fails_safe(self):
        class C:
            pass

        assert requires_provenance_approval_for_claim(C()) is True
