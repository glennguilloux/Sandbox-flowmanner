"""
Capability Composer - Dynamic Capability Composition System

Enables creation of composed capabilities that chain multiple
capabilities together in various execution patterns.

Composition Types:
- sequential: Execute capabilities in order, pass output to next
- parallel: Execute all at once, merge results
- conditional: Branch based on previous output
- loop: Repeat until condition met

H2.3: All compositions are now registered with the CapabilityLattice
for depth enforcement, cycle detection, and loop termination validation.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models.models import ComposedCapabilityModel

logger = logging.getLogger(__name__)


class CompositionType(str, Enum):
    """Types of capability composition"""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"
    LOOP = "loop"


@dataclass
class ComposedCapability:
    """Represents a chain of capabilities composed together"""

    id: str
    name: str
    description: str
    capability_ids: list[str]
    composition_type: CompositionType
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # Conditional composition fields
    condition_field: str | None = None
    condition_value: Any | None = None
    true_branch: list[str] | None = None
    false_branch: list[str] | None = None

    # Loop composition fields
    loop_condition: str | None = None  # Field to check for loop termination
    loop_max_iterations: int = 10

    # Execution tracking
    execution_count: int = 0
    last_executed: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "capability_ids": self.capability_ids,
            "composition_type": self.composition_type.value,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "metadata": self.metadata,
            "condition_field": self.condition_field,
            "condition_value": self.condition_value,
            "true_branch": self.true_branch,
            "false_branch": self.false_branch,
            "loop_condition": self.loop_condition,
            "loop_max_iterations": self.loop_max_iterations,
            "execution_count": self.execution_count,
            "last_executed": (self.last_executed.isoformat() if self.last_executed else None),
        }


@dataclass
class CompositionTemplate:
    """Reusable composition pattern template"""

    id: str
    name: str
    description: str
    composition_type: CompositionType
    capability_slots: list[str]  # Placeholder names for capabilities
    default_capabilities: dict[str, str] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "composition_type": self.composition_type.value,
            "capability_slots": self.capability_slots,
            "default_capabilities": self.default_capabilities,
            "parameters": self.parameters,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class CompositionResult:
    """Result of composed capability execution"""

    success: bool
    composed_id: str
    outputs: list[dict[str, Any]]
    final_output: Any
    execution_time_ms: float = 0
    capabilities_executed: list[str] = field(default_factory=list)
    error: str | None = None
    iterations: int = 1


class CapabilityComposer:
    """
    Composes multiple capabilities into unified operations.

    Supports various composition patterns:
    - Sequential: Chain capabilities, passing output to next
    - Parallel: Execute all simultaneously, merge results
    - Conditional: Branch based on conditions
    - Loop: Repeat until condition met
    """

    def __init__(self):
        self._composed: dict[str, ComposedCapability] = {}
        self._templates: dict[str, CompositionTemplate] = {}
        self._registry = None
        self._sync_engine = None
        # Load persisted composed capabilities on initialization
        self._load_persisted_capabilities()

    def _get_registry(self):
        """Lazy load capability registry"""
        if self._registry is None:
            from .capability_registry import get_capability_registry

            self._registry = get_capability_registry()
        return self._registry

    def _get_db_session(self) -> Session:
        """Get or create database session"""
        if self._sync_engine is None:
            sync_url = settings.DATABASE_URL.replace("+asyncpg", "").replace("postgresql+asyncpg", "postgresql")
            self._sync_engine = create_engine(sync_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
        factory = sessionmaker(bind=self._sync_engine)
        return factory()

    def _load_persisted_capabilities(self):
        """Load all persisted composed capabilities from database"""
        db = None
        try:
            db = self._get_db_session()
            models = db.query(ComposedCapabilityModel).all()
            for model in models:
                composed = ComposedCapability(
                    id=model.id,
                    name=model.name,
                    description=model.description,
                    capability_ids=model.capability_ids,
                    composition_type=CompositionType(model.composition_type),
                    created_by=model.created_by,
                    metadata=model.metadata or {},
                    condition_field=model.condition_field,
                    condition_value=model.condition_value,
                    true_branch=model.true_branch,
                    false_branch=model.false_branch,
                    loop_condition=model.loop_condition,
                    loop_max_iterations=model.loop_max_iterations or 10,
                    execution_count=model.execution_count or 0,
                    last_executed=model.last_executed,
                )
                self._composed[model.id] = composed
            if models:
                logger.info(
                    "Loaded %s persisted composed capabilities from database",
                    len(models),
                )
        except Exception as e:
            logger.warning("Could not load persisted capabilities: %s", e)
        finally:
            if db:
                db.close()

    async def _save_composed_capability(self, composed: ComposedCapability):
        """Save a composed capability to database"""
        db = None
        try:
            db = self._get_db_session()
            existing = db.query(ComposedCapabilityModel).filter(ComposedCapabilityModel.id == composed.id).first()

            if existing:
                # Update existing
                existing.name = composed.name
                existing.description = composed.description
                existing.capability_ids = composed.capability_ids  # type: ignore[assignment]
                existing.composition_type = composed.composition_type.value  # type: ignore[attr-defined]
                existing.metadata = composed.metadata  # type: ignore[misc,assignment]
                existing.execution_count = composed.execution_count  # type: ignore[attr-defined]
                existing.last_executed = composed.last_executed  # type: ignore[attr-defined]
            else:
                # Create new
                model = ComposedCapabilityModel(
                    id=composed.id,
                    name=composed.name,
                    description=composed.description,
                    capability_ids=composed.capability_ids,
                    composition_type=composed.composition_type.value,
                    created_by=composed.created_by,
                    metadata=composed.metadata,
                    condition_field=composed.condition_field,
                    condition_value=composed.condition_value,
                    true_branch=composed.true_branch,
                    false_branch=composed.false_branch,
                    loop_condition=composed.loop_condition,
                    loop_max_iterations=composed.loop_max_iterations,
                    execution_count=composed.execution_count,
                    last_executed=composed.last_executed,
                )
                db.add(model)

            db.commit()
            logger.info("Saved composed capability to database: %s", composed.id)
        except Exception as e:
            logger.error("Failed to save composed capability %s: %s", composed.id, e)
            if db:
                db.rollback()
        finally:
            if db:
                db.close()

    async def delete_composed_capability(self, composed_id: str) -> bool:
        """Delete a composed capability from memory and database"""
        db = None
        try:
            # Remove from memory
            if composed_id in self._composed:
                del self._composed[composed_id]

            # Remove from database
            db = self._get_db_session()
            db.query(ComposedCapabilityModel).filter(ComposedCapabilityModel.id == composed_id).delete()
            db.commit()

            logger.info("Deleted composed capability: %s", composed_id)
            return True
        except Exception as e:
            logger.error("Failed to delete composed capability %s: %s", composed_id, e)
            if db:
                db.rollback()
            return False
        finally:
            if db:
                db.close()

    async def compose(
        self,
        capability_ids: list[str],
        composition_type: str,
        name: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs,
    ) -> ComposedCapability:
        """
        Create a new composed capability.

        H2.3: Registers the composition with the CapabilityLattice for depth
        enforcement, cycle detection, and loop termination validation.

        Args:
            capability_ids: List of capability IDs to compose
            composition_type: Type of composition (sequential, parallel, conditional, loop)
            name: Human-readable name
            description: Description of the composed capability
            metadata: Additional metadata
            **kwargs: Additional composition-specific parameters

        Returns:
            ComposedCapability instance

        Raises:
            LatticeError: If the composition violates lattice invariants (depth, cycles).
            ValueError: If the composition type is invalid.
        """
        # Validate composition type
        try:
            comp_type = CompositionType(composition_type)
        except ValueError:
            raise ValueError(
                f"Invalid composition type: {composition_type}. Valid types: {[t.value for t in CompositionType]}"
            )

        # Validate capabilities exist
        registry = self._get_registry()
        for cap_id in capability_ids:
            if not registry.get(cap_id):
                logger.warning("Capability %s not found in registry", cap_id)

        # Generate ID and create composed capability
        composed_id = f"composed:{uuid.uuid4().hex[:8]}"

        # H2.3: Register with CapabilityLattice for depth enforcement
        try:
            from .capability_lattice import (
                CapabilityLattice,
                LatticeError,
                get_capability_lattice,
            )
            from .capability_lattice import (
                CompositionType as LatticeCompositionType,
            )

            lattice = get_capability_lattice()

            # Map CompositionType enum to lattice enum
            lattice_type_map = {
                CompositionType.SEQUENTIAL: LatticeCompositionType.SEQUENTIAL,
                CompositionType.PARALLEL: LatticeCompositionType.PARALLEL,
                CompositionType.CONDITIONAL: LatticeCompositionType.CONDITIONAL,
                CompositionType.LOOP: LatticeCompositionType.LOOP,
            }
            lattice_type = lattice_type_map.get(comp_type)

            # Register leaf nodes first for any child not yet in lattice
            for cap_id in capability_ids:
                if lattice.get_node(cap_id) is None:
                    lattice.register_leaf(cap_id, cap_id)

            lattice.register_composed(
                capability_id=composed_id,
                name=name or f"Composed-{comp_type.value}-{len(self._composed)}",
                children=capability_ids,
                composition_type=lattice_type,
                max_iterations=kwargs.get("loop_max_iterations"),
                termination_condition=kwargs.get("termination_condition"),
            )
            logger.debug(
                "Registered %s in CapabilityLattice (depth=%d)",
                composed_id,
                lattice.get_depth(composed_id),
            )
        except LatticeError as e:
            raise LatticeError(f"Composition rejected: {e}") from e
        except ImportError:
            logger.debug("CapabilityLattice not available, skipping depth enforcement")

        composed = ComposedCapability(
            id=composed_id,
            name=name or f"Composed-{comp_type.value}-{len(self._composed)}",
            description=description or f"{comp_type.value.title()} composition of {len(capability_ids)} capabilities",
            capability_ids=capability_ids,
            composition_type=comp_type,
            metadata=metadata or {},
            **kwargs,
        )

        self._composed[composed_id] = composed
        logger.info("Created composed capability: %s (%s)", composed_id, comp_type.value)

        # Persist to database
        await self._save_composed_capability(composed)

        # Register as a capability in the registry
        await self._register_composed_capability(composed)

        return composed

    async def _register_composed_capability(self, composed: ComposedCapability):
        """Register composed capability in the main registry"""
        registry = self._get_registry()

        async def composed_handler(params: dict[str, Any]) -> Any:
            result = await self.execute_composed(composed.id, params)
            return result.final_output if result.success else {"error": result.error}

        from .capability_registry import Capability

        capability = Capability(
            id=composed.id,
            name=composed.name,
            description=composed.description,
            category="composed",
            handler=composed_handler,
            input_schema={
                "type": "object",
                "properties": {"params": {"type": "object"}},
            },
            output_schema={"type": "object"},
            requires_auth=False,
            metadata={
                "composition_type": composed.composition_type.value,
                **composed.metadata,
            },
        )

        registry.register(capability)
        logger.info("Registered composed capability in registry: %s", composed.id)

    def validate_composition(self, capability_ids: list[str]) -> tuple:
        """
        Check if a composition is valid.

        Args:
            capability_ids: List of capability IDs to validate

        Returns:
            (is_valid, error_messages)
        """
        errors = []
        registry = self._get_registry()

        if not capability_ids:
            errors.append("No capabilities provided for composition")
            return False, errors

        for cap_id in capability_ids:
            cap = registry.get(cap_id)
            if not cap:
                errors.append(f"Capability not found: {cap_id}")

        return len(errors) == 0, errors

    async def execute_composed(self, composed_id: str, params: dict[str, Any]) -> CompositionResult:
        """
        Execute a composed capability.

        Args:
            composed_id: ID of the composed capability
            params: Parameters to pass to the composition

        Returns:
            CompositionResult with execution details
        """
        start_time = datetime.now(UTC)

        composed = self._composed.get(composed_id)
        if not composed:
            return CompositionResult(
                success=False,
                composed_id=composed_id,
                outputs=[],
                final_output=None,
                error=f"Composed capability not found: {composed_id}",
            )
        registry = self._get_registry()
        outputs: list[Any] = []
        capabilities_executed: list[str] = []
        current_params = params.copy()

        try:
            if composed.composition_type == CompositionType.SEQUENTIAL:
                result = await self._execute_sequential(
                    composed, registry, current_params, outputs, capabilities_executed
                )
            elif composed.composition_type == CompositionType.PARALLEL:
                result = await self._execute_parallel(
                    composed, registry, current_params, outputs, capabilities_executed
                )
            elif composed.composition_type == CompositionType.CONDITIONAL:
                result = await self._execute_conditional(
                    composed, registry, current_params, outputs, capabilities_executed
                )
            elif composed.composition_type == CompositionType.LOOP:
                result = await self._execute_loop(composed, registry, current_params, outputs, capabilities_executed)
            else:
                raise ValueError(f"Unknown composition type: {composed.composition_type}")

            # Update execution tracking
            composed.execution_count += 1
            composed.last_executed = datetime.now(UTC)

            execution_time = (datetime.now(UTC) - start_time).total_seconds() * 1000

            return CompositionResult(
                success=True,
                composed_id=composed_id,
                outputs=outputs,
                final_output=result,
                execution_time_ms=execution_time,
                capabilities_executed=capabilities_executed,
            )

        except Exception as e:
            logger.error("Error executing composed capability %s: %s", composed_id, e)
            execution_time = (datetime.now(UTC) - start_time).total_seconds() * 1000
            return CompositionResult(
                success=False,
                composed_id=composed_id,
                outputs=outputs,
                final_output=None,
                execution_time_ms=execution_time,
                capabilities_executed=capabilities_executed,
                error=str(e),
            )

    async def _execute_sequential(
        self,
        composed: ComposedCapability,
        registry,
        params: dict[str, Any],
        outputs: list,
        capabilities_executed: list,
    ) -> Any:
        """Execute capabilities sequentially, passing output to next"""
        current_output = params

        for cap_id in composed.capability_ids:
            cap = registry.get(cap_id)
            if not cap:
                logger.warning("Capability %s not found, skipping", cap_id)
                continue

            # Merge current output with params for next capability
            if isinstance(current_output, dict):
                exec_params = {**params, **current_output}
            else:
                exec_params = {**params, "input": current_output}

            result = await cap.execute(exec_params)
            outputs.append({"capability_id": cap_id, "output": result})
            capabilities_executed.append(cap_id)
            current_output = result

            logger.debug("Sequential execution: %s completed", cap_id)

        return current_output

    async def _execute_parallel(
        self,
        composed: ComposedCapability,
        registry,
        params: dict[str, Any],
        outputs: list,
        capabilities_executed: list,
    ) -> Any:
        """Execute all capabilities in parallel, merge results"""
        tasks = []
        valid_caps = []

        for cap_id in composed.capability_ids:
            cap = registry.get(cap_id)
            if cap:
                tasks.append(cap.execute(params))
                valid_caps.append(cap_id)
            else:
                logger.warning("Capability %s not found, skipping", cap_id)

        if not tasks:
            return {"error": "No valid capabilities to execute"}

        results = await asyncio.gather(*tasks, return_exceptions=True)

        merged_output = {}
        for cap_id, result in zip(valid_caps, results, strict=False):
            if isinstance(result, Exception):
                outputs.append({"capability_id": cap_id, "error": str(result)})
            else:
                outputs.append({"capability_id": cap_id, "output": result})
                if isinstance(result, dict):
                    merged_output.update(result)
                else:
                    merged_output[cap_id] = result
            capabilities_executed.append(cap_id)

        return merged_output

    async def _execute_conditional(
        self,
        composed: ComposedCapability,
        registry,
        params: dict[str, Any],
        outputs: list,
        capabilities_executed: list,
    ) -> Any:
        """Execute capabilities conditionally based on previous output"""
        # First execute the condition capability
        condition_cap_id = composed.capability_ids[0]
        condition_cap = registry.get(condition_cap_id)

        if not condition_cap:
            raise ValueError(f"Condition capability not found: {condition_cap_id}")

        condition_result = await condition_cap.execute(params)
        outputs.append({"capability_id": condition_cap_id, "output": condition_result})
        capabilities_executed.append(condition_cap_id)

        # Determine which branch to take
        branch_to_take = None
        if composed.condition_field and isinstance(condition_result, dict):
            field_value = condition_result.get(composed.condition_field)
            branch_to_take = composed.true_branch if field_value == composed.condition_value else composed.false_branch
        else:
            # Default: truthy check
            if condition_result:
                branch_to_take = composed.true_branch or composed.capability_ids[1:]
            else:
                branch_to_take = composed.false_branch or []

        # Execute the chosen branch
        result = condition_result
        if branch_to_take:
            for cap_id in branch_to_take:
                cap = registry.get(cap_id)
                if cap:
                    result = await cap.execute({**params, "condition_result": condition_result})
                    outputs.append({"capability_id": cap_id, "output": result})
                    capabilities_executed.append(cap_id)

        return result

    async def _execute_loop(
        self,
        composed: ComposedCapability,
        registry,
        params: dict[str, Any],
        outputs: list,
        capabilities_executed: list,
    ) -> Any:
        """Execute capabilities in a loop until condition is met"""
        current_output = params
        iterations = 0
        max_iter = composed.loop_max_iterations

        while iterations < max_iter:
            iteration_outputs = []

            for cap_id in composed.capability_ids:
                cap = registry.get(cap_id)
                if not cap:
                    continue

                exec_params = (
                    {**params, **current_output}
                    if isinstance(current_output, dict)
                    else {**params, "input": current_output}
                )
                # Trust-boundary (agent-loop-trust-boundary skill): every
                # capability call needs a timeout; an unguarded await can stall
                # the gather/loop indefinitely. Validate current_output shape so
                # a malformed result from one capability cannot silently poison
                # the next capability's params.
                _cap_timeout = float(getattr(composed, "capability_timeout_seconds", None) or 60)
                try:
                    result = await asyncio.wait_for(cap.execute(exec_params), timeout=_cap_timeout)
                except TimeoutError:
                    logger.error("Capability %s timed out after %ss", cap_id, _cap_timeout)
                    result = {
                        "success": False,
                        "error": f"Capability {cap_id} timed out",
                    }
                if not isinstance(result, dict | str | bytes):
                    result = {"success": False, "error": "non-serializable capability output"}
                iteration_outputs.append({"capability_id": cap_id, "output": result})
                capabilities_executed.append(f"{cap_id}:{iterations}")
                current_output = result

            outputs.append({"iteration": iterations, "outputs": iteration_outputs})
            iterations += 1

            # Check loop condition
            if (
                composed.loop_condition
                and isinstance(current_output, dict)
                and current_output.get(composed.loop_condition) == True
            ):
                logger.info("Loop condition met after %s iterations", iterations)
                break

            # Check for "done" flag in output
            if isinstance(current_output, dict) and current_output.get("done"):
                logger.info("Loop completed after %s iterations", iterations)
                break

        return current_output

    def save_template(self, template: CompositionTemplate) -> bool:
        """
        Save a reusable composition template.

        Args:
            template: CompositionTemplate to save

        Returns:
            True if saved successfully
        """
        self._templates[template.id] = template
        logger.info("Saved composition template: %s", template.id)
        return True

    def create_template(
        self,
        name: str,
        description: str,
        composition_type: str,
        capability_slots: list[str],
        default_capabilities: dict[str, str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> CompositionTemplate:
        """
        Create and save a new composition template.

        Args:
            name: Template name
            description: Template description
            composition_type: Type of composition
            capability_slots: Placeholder names for capabilities
            default_capabilities: Default capability assignments
            parameters: Additional template parameters

        Returns:
            CompositionTemplate instance
        """
        template_id = f"template:{uuid.uuid4().hex[:8]}"

        try:
            comp_type = CompositionType(composition_type)
        except ValueError:
            raise ValueError(f"Invalid composition type: {composition_type}")

        template = CompositionTemplate(
            id=template_id,
            name=name,
            description=description,
            composition_type=comp_type,
            capability_slots=capability_slots,
            default_capabilities=default_capabilities or {},
            parameters=parameters or {},
        )

        self.save_template(template)
        return template

    def list_templates(self) -> list[CompositionTemplate]:
        """List all available composition templates"""
        return list(self._templates.values())

    def get_template(self, template_id: str) -> CompositionTemplate | None:
        """Get a specific template by ID"""
        return self._templates.get(template_id)

    async def compose_from_template(
        self,
        template_id: str,
        capability_assignments: dict[str, str],
        params: dict[str, Any] | None = None,
    ) -> ComposedCapability:
        """
        Create a composed capability from a template.

        Args:
            template_id: ID of the template to use
            capability_assignments: Mapping of slot names to capability IDs
            params: Additional parameters for the composition

        Returns:
            ComposedCapability instance
        """
        template = self._templates.get(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")

        # Merge default capabilities with assignments
        final_assignments = {**template.default_capabilities, **capability_assignments}

        # Build capability list from slots
        capability_ids = [final_assignments.get(slot, f"unknown:{slot}") for slot in template.capability_slots]

        return await self.compose(
            capability_ids=capability_ids,
            composition_type=template.composition_type.value,
            name=f"{template.name}-instance",
            description=template.description,
            metadata={"template_id": template_id, **(params or {})},
        )

    def list_composed(self) -> list[ComposedCapability]:
        """List all composed capabilities"""
        return list(self._composed.values())

    def get_composed(self, composed_id: str) -> ComposedCapability | None:
        """Get a specific composed capability by ID"""
        return self._composed.get(composed_id)

    def delete_composed(self, composed_id: str) -> bool:
        """Delete a composed capability"""
        if composed_id in self._composed:
            del self._composed[composed_id]
            logger.info("Deleted composed capability: %s", composed_id)
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        """Export composer state as dictionary"""
        return {
            "composed_capabilities": [c.to_dict() for c in self._composed.values()],
            "templates": [t.to_dict() for t in self._templates.values()],
            "total_composed": len(self._composed),
            "total_templates": len(self._templates),
        }


# Singleton instance
_capability_composer: Optional["CapabilityComposer"] = None


def get_capability_composer() -> CapabilityComposer:
    """Get or create the capability composer singleton"""
    global _capability_composer
    if _capability_composer is None:
        _capability_composer = CapabilityComposer()
    return _capability_composer
