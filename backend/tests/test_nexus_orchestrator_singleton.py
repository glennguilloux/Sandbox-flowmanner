"""Test NexusOrchestrator singleton behavior.

Verifies:
- Module imports cleanly (no NameError from _nexus_orchestrator)
- get_nexus_orchestrator() returns the same instance on repeated calls
- distributed_mode path does not break singleton initialization
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


# ═══════════════════════════════════════════════════════════════════
# Import cleanliness
# ═══════════════════════════════════════════════════════════════════


class TestOrchestratorModuleImport:
    def test_module_imports_cleanly(self):
        """The orchestrator module imports without NameError."""
        # This import was previously broken due to _nexus_orchestrator
        # being defined inside a class method body instead of module level.
        from app.services.nexus.orchestrator import (
            NexusOrchestrator,
            get_nexus_orchestrator,
        )

        assert callable(get_nexus_orchestrator)

    def test_get_nexus_orchestrator_returns_singleton(self):
        """get_nexus_orchestrator() returns the same instance."""
        # Reset any cached instance for clean test
        import app.services.nexus.orchestrator as orch_module
        from app.services.nexus.orchestrator import (
            NexusOrchestrator,
            get_nexus_orchestrator,
        )

        orch_module._nexus_orchestrator = None

        inst1 = get_nexus_orchestrator()
        inst2 = get_nexus_orchestrator()

        assert inst1 is inst2
        assert isinstance(inst1, NexusOrchestrator)

        # Cleanup
        orch_module._nexus_orchestrator = None

    def test_distributed_mode_caches_singleton(self):
        """get_nexus_orchestrator(distributed_mode=True) returns a singleton."""
        import app.services.nexus.orchestrator as orch_module
        from app.services.nexus.orchestrator import get_nexus_orchestrator

        orch_module._nexus_orchestrator = None

        inst1 = get_nexus_orchestrator(distributed_mode=True)
        inst2 = get_nexus_orchestrator(distributed_mode=False)

        # First call creates the singleton; second returns same instance
        # (distributed_mode on second call is ignored because singleton exists)
        assert inst1 is inst2

        orch_module._nexus_orchestrator = None

    def test_singleton_recreation_after_none(self):
        """After resetting to None, next call creates a new singleton."""
        import app.services.nexus.orchestrator as orch_module
        from app.services.nexus.orchestrator import get_nexus_orchestrator

        orch_module._nexus_orchestrator = None

        inst1 = get_nexus_orchestrator()
        orch_module._nexus_orchestrator = None
        inst2 = get_nexus_orchestrator()

        # After clearing, new instance is created
        assert inst1 is not inst2
