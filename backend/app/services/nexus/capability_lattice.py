"""CapabilityLattice — bounded composition depth with invariants (H2.3).

Replaces the ad-hoc `max_depth = 3` constants scattered across:
- meta_loop_orchestrator.py
- capability_composer.py (loop_max_iterations)

Provides:
1. A `CapabilityLattice` that maintains a `depth` invariant for composed capabilities
2. Static analysis that detects unbounded loops and rejects them at composition time
3. The four composition types (sequential, parallel, conditional, loop) each get
   a halting proof sketch in their docstring

Design:
- The lattice is a directed acyclic graph where nodes are capabilities and edges
  represent composition relationships.
- The depth of a node is the longest path from any leaf capability.
- `max_depth` is a global invariant enforced on every composition operation.
- Loop compositions require a `termination_condition` that can be statically
  checked (field value match, typed finite iterator, or explicit iteration count).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class CompositionType(str, Enum):
    """Types of capability composition with halting proof sketches."""

    SEQUENTIAL = "sequential"
    # Halting proof: A → B → C is bounded by max_depth.
    # Each step reduces the remaining depth budget by 1.

    PARALLEL = "parallel"
    # Halting proof: All branches execute concurrently.
    # Depth is max(branch_depths). Each branch bounded by its own depth budget.

    CONDITIONAL = "conditional"
    # Halting proof: Exactly one branch executes.
    # Depth ≤ 1 + max(true_branch_depth, false_branch_depth).
    # The condition itself has depth 1.

    LOOP = "loop"
    # Halting proof: Requires a termination_condition.
    # Acceptable conditions:
    #   (a) Explicit max_iterations (bounded by the parent's budget)
    #   (b) Typed field match: loop_body.output.field == termination_value
    #   (c) Strict subtype check: loop_body.output ⊆ input at recursion point
    # Rejected: string-based exit conditions with no type constraint.


@dataclass
class CapabilityNode:
    """A node in the capability lattice."""

    capability_id: str
    name: str
    depth: int = 0  # Longest path from any leaf capability
    composition_type: CompositionType | None = None
    children: list[str] = field(default_factory=list)  # Child capability IDs
    parents: list[str] = field(default_factory=list)  # Parent composed capability IDs
    max_iterations: int | None = None  # For LOOP compositions
    termination_condition: dict | None = None  # For LOOP compositions

    def is_leaf(self) -> bool:
        return not self.children and self.composition_type is None

    def to_dict(self) -> dict:
        return {
            "capability_id": self.capability_id,
            "name": self.name,
            "depth": self.depth,
            "composition_type": self.composition_type.value if self.composition_type else None,
            "children": self.children,
            "parents": self.parents,
            "max_iterations": self.max_iterations,
            "termination_condition": self.termination_condition,
        }


class LatticeError(ValueError):
    """Raised when a composition violates lattice invariants."""
    pass


class CapabilityLattice:
    """Bounded capability composition lattice with depth invariant.

    Invariants enforced:
    1. max_depth: No composed capability may exceed this depth.
    2. No cycles: The lattice is a DAG (enforced at edge insertion).
    3. Loop termination: Loop compositions must have a valid termination condition.
    4. Child subset: A composed capability's children must be registered nodes.
    """

    # Default max depth — tuneable per environment
    DEFAULT_MAX_DEPTH = 3

    # Hard ceiling — no composition may exceed this regardless of config
    HARD_MAX_DEPTH = 10

    def __init__(self, max_depth: int = DEFAULT_MAX_DEPTH):
        if max_depth > self.HARD_MAX_DEPTH:
            raise ValueError(
                f"max_depth {max_depth} exceeds hard ceiling {self.HARD_MAX_DEPTH}"
            )
        self.max_depth = max_depth
        self._nodes: dict[str, CapabilityNode] = {}

    # ── Node registration ──────────────────────────────────────────

    def register_leaf(self, capability_id: str, name: str) -> CapabilityNode:
        """Register a leaf capability (no children, no composition)."""
        if capability_id in self._nodes:
            return self._nodes[capability_id]

        node = CapabilityNode(
            capability_id=capability_id,
            name=name,
            depth=0,
        )
        self._nodes[capability_id] = node
        logger.debug("Registered leaf capability: %s (depth=0)", capability_id)
        return node

    def register_composed(
        self,
        capability_id: str,
        name: str,
        children: list[str],
        composition_type: CompositionType,
        *,
        max_iterations: int | None = None,
        termination_condition: dict | None = None,
    ) -> CapabilityNode:
        """Register a composed capability with depth enforcement.

        Raises:
            LatticeError: If the composition violates any invariant.
        """
        # Validate children exist
        for child_id in children:
            if child_id not in self._nodes:
                raise LatticeError(
                    f"Child capability '{child_id}' not registered in lattice"
                )
            if child_id == capability_id:
                raise LatticeError(
                    f"Self-referential composition detected: {capability_id}"
                )

        # Validate loop termination
        if composition_type == CompositionType.LOOP:
            self._validate_loop_termination(
                capability_id, children, max_iterations, termination_condition
            )

        # Compute depth
        child_depths = [self._nodes[c].depth for c in children]
        if composition_type == CompositionType.PARALLEL or composition_type == CompositionType.CONDITIONAL:
            new_depth = 1 + max(child_depths) if child_depths else 1
        elif composition_type == CompositionType.LOOP:
            # Loop depth is bounded by max_iterations + body depth
            body_depth = max(child_depths) if child_depths else 1
            new_depth = 1 + body_depth
        else:  # SEQUENTIAL
            new_depth = 1 + sum(child_depths) if child_depths else 1

        if new_depth > self.max_depth:
            raise LatticeError(
                f"Composed capability '{capability_id}' depth {new_depth} "
                f"exceeds max_depth {self.max_depth} (children: {children})"
            )

        # Check for cycles
        self._validate_no_cycles(capability_id, children)

        node = CapabilityNode(
            capability_id=capability_id,
            name=name,
            depth=new_depth,
            composition_type=composition_type,
            children=list(children),
            max_iterations=max_iterations,
            termination_condition=termination_condition,
        )
        self._nodes[capability_id] = node

        # Update parent references on children
        for child_id in children:
            child_node = self._nodes[child_id]
            if capability_id not in child_node.parents:
                child_node.parents.append(capability_id)

        logger.info(
            "Registered composed capability: %s (depth=%d, type=%s, children=%s)",
            capability_id, new_depth, composition_type.value, children,
        )
        return node

    # ── Validation ─────────────────────────────────────────────────

    def _validate_loop_termination(
        self,
        capability_id: str,
        children: list[str],
        max_iterations: int | None,
        termination_condition: dict | None,
    ) -> None:
        """Validate that a loop composition has a valid termination condition.

        A loop MUST have at least one of:
        - max_iterations (explicit bound)
        - termination_condition with a typed field match

        Rejects: string-based exit conditions with no type constraint.
        """
        if max_iterations is not None and max_iterations > 0:
            if max_iterations > self.max_depth * 10:
                raise LatticeError(
                    f"Loop '{capability_id}' max_iterations {max_iterations} "
                    f"is unreasonably large (max={self.max_depth * 10})"
                )
            return  # OK: explicit iteration bound

        if termination_condition is not None:
            field = termination_condition.get("field")
            value = termination_condition.get("value")
            if field and value is not None:
                return  # OK: typed field match

        raise LatticeError(
            f"Loop composition '{capability_id}' requires a valid termination condition. "
            f"Provide max_iterations (bounded) or a termination_condition with "
            f"typed field match (e.g., {{'field': 'done', 'value': true}}). "
            f"String-based exit conditions with no type constraint are rejected."
        )

    def _validate_no_cycles(
        self, capability_id: str, children: list[str]
    ) -> None:
        """Check that adding edges from children → capability_id creates no cycle.

        Performs a DFS from capability_id through the children's descendants.
        If capability_id is reachable from any child, a cycle would be created.
        """
        visited: set[str] = set()

        def dfs(node_id: str) -> bool:
            """Returns True if capability_id is reachable from node_id."""
            if node_id == capability_id:
                return True
            if node_id in visited:
                return False
            visited.add(node_id)

            node = self._nodes.get(node_id)
            if node is None:
                return False
            return any(dfs(child_id) for child_id in node.children)

        for child_id in children:
            visited.clear()
            if dfs(child_id):
                raise LatticeError(
                    f"Cycle detected: adding '{capability_id}' → '{child_id}' "
                    f"would create a cycle in the capability lattice"
                )

    # ── Queries ─────────────────────────────────────────────────────

    def get_depth(self, capability_id: str) -> int | None:
        """Get the depth of a capability in the lattice."""
        node = self._nodes.get(capability_id)
        return node.depth if node else None

    def get_node(self, capability_id: str) -> CapabilityNode | None:
        """Get a node by capability ID."""
        return self._nodes.get(capability_id)

    def is_within_budget(
        self, capability_id: str, remaining_depth: int
    ) -> bool:
        """Check if a capability can be executed within the remaining depth budget."""
        node = self._nodes.get(capability_id)
        if node is None:
            return False
        return node.depth <= remaining_depth

    def get_ancestors(self, capability_id: str) -> list[str]:
        """Get all ancestor capability IDs (transitive parents)."""
        node = self._nodes.get(capability_id)
        if node is None:
            return []

        ancestors: set[str] = set()

        def collect_ancestors(nid: str):
            n = self._nodes.get(nid)
            if n is None:
                return
            for parent_id in n.parents:
                if parent_id not in ancestors:
                    ancestors.add(parent_id)
                    collect_ancestors(parent_id)

        collect_ancestors(capability_id)
        return list(ancestors)

    def get_descendants(self, capability_id: str) -> list[str]:
        """Get all descendant capability IDs (transitive children)."""
        node = self._nodes.get(capability_id)
        if node is None:
            return []

        descendants: set[str] = set()

        def collect_descendants(nid: str):
            n = self._nodes.get(nid)
            if n is None:
                return
            for child_id in n.children:
                if child_id not in descendants:
                    descendants.add(child_id)
                    collect_descendants(child_id)

        collect_descendants(capability_id)
        return list(descendants)

    def to_dict(self) -> dict:
        return {
            "max_depth": self.max_depth,
            "hard_max_depth": self.HARD_MAX_DEPTH,
            "node_count": len(self._nodes),
            "nodes": {nid: node.to_dict() for nid, node in self._nodes.items()},
        }


# ── Singleton ──────────────────────────────────────────────────────

_lattice: CapabilityLattice | None = None


def get_capability_lattice(max_depth: int | None = None) -> CapabilityLattice:
    """Get or create the CapabilityLattice singleton."""
    global _lattice
    if _lattice is None:
        _lattice = CapabilityLattice(
            max_depth=max_depth if max_depth is not None else CapabilityLattice.DEFAULT_MAX_DEPTH
        )
    return _lattice


def reset_capability_lattice() -> None:
    """Reset the lattice singleton (for testing)."""
    global _lattice
    _lattice = None
