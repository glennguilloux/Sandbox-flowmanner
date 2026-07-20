"""Tests for the ``validate_schema`` node handler (CARD MB-T1R4).

Covers the three acceptance criteria:
1. payload matches -> execute continues down the DEFAULT edge (``valid=True``).
2. mismatch -> execute routes to the ``on_invalid`` edge (does NOT raise).
3. missing required field -> caught PRE-execution by ``validate()``.

Plus configuration guards (missing schema, invalid schema, custom keys).
"""

from __future__ import annotations

from typing import Any

import pytest

from app.sdk.context import PluginContext
from app.sdk.validate_schema import (
    DEFAULT_ROUTE,
    INVALID_ROUTE,
    ValidateSchemaHandler,
)

# A representative object schema with a required field and typed properties.
OBJECT_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "name": {"type": "string"},
    },
    "required": ["id"],
    "additionalProperties": True,
}


def _ctx(*, payload: Any = ..., config=None, inputs=None):
    """Build a PluginContext with a schema config and an optional payload."""
    cfg = {"schema": OBJECT_SCHEMA}
    if config:
        cfg.update(config)
    in_dict = dict(inputs or {})
    if payload is not ...:
        in_dict["payload"] = payload
    return PluginContext(inputs=in_dict, config=cfg)


class TestValidatePreExecution:
    """validate() is the pre-execution gate (BaseNodeHandler contract)."""

    async def test_matching_payload_has_no_errors(self) -> None:
        handler = ValidateSchemaHandler()
        errors = await handler.validate(_ctx(payload={"id": 1, "name": "ok"}))
        assert errors == []

    async def test_missing_required_field_caught_pre_execution(self) -> None:
        handler = ValidateSchemaHandler()
        # 'id' is required but absent -> caught before execute() ever runs.
        errors = await handler.validate(_ctx(payload={"name": "no-id"}))
        assert errors
        assert any("id" in e for e in errors)

    async def test_wrong_type_reported(self) -> None:
        handler = ValidateSchemaHandler()
        errors = await handler.validate(_ctx(payload={"id": "not-an-int"}))
        assert errors
        assert any("id" in e for e in errors)

    async def test_missing_payload_input_reported(self) -> None:
        handler = ValidateSchemaHandler()
        errors = await handler.validate(_ctx())  # no payload input at all
        assert errors
        assert any("payload" in e for e in errors)


class TestExecuteRouting:
    """execute() emits routing outputs and never raises on a mismatch."""

    async def test_match_continues_on_default_edge(self) -> None:
        handler = ValidateSchemaHandler()
        ctx = _ctx(payload={"id": 42, "name": "valid"})
        result = await handler.execute(ctx)
        assert result["valid"] is True
        assert result["route"] == DEFAULT_ROUTE
        assert result["errors"] == []
        assert ctx.get_outputs()["route"] == DEFAULT_ROUTE

    async def test_mismatch_routes_to_on_invalid(self) -> None:
        handler = ValidateSchemaHandler()
        ctx = _ctx(payload={"name": "no-id"})
        result = await handler.execute(ctx)  # must NOT raise
        assert result["valid"] is False
        assert result["route"] == INVALID_ROUTE
        assert result["errors"]
        assert ctx.get_outputs()["route"] == INVALID_ROUTE

    async def test_custom_on_invalid_edge_label(self) -> None:
        handler = ValidateSchemaHandler()
        ctx = _ctx(payload={"id": "bad"}, config={"on_invalid": "repair_edge"})
        result = await handler.execute(ctx)
        assert result["valid"] is False
        assert result["route"] == "repair_edge"

    async def test_custom_payload_key(self) -> None:
        handler = ValidateSchemaHandler()
        ctx = PluginContext(
            inputs={"body": {"id": 7}},
            config={"schema": OBJECT_SCHEMA, "payload_key": "body"},
        )
        result = await handler.execute(ctx)
        assert result["valid"] is True
        assert result["route"] == DEFAULT_ROUTE


class TestConfigGuards:
    """A misconfigured node fails CLOSED (routes invalid), never silently passes."""

    async def test_missing_schema_config_is_error(self) -> None:
        handler = ValidateSchemaHandler()
        ctx = PluginContext(inputs={"payload": {"id": 1}}, config={})
        errors = await handler.validate(ctx)
        assert errors
        assert any("schema" in e for e in errors)

    async def test_invalid_schema_document_is_error(self) -> None:
        handler = ValidateSchemaHandler()
        ctx = PluginContext(
            inputs={"payload": {"id": 1}},
            config={"schema": {"type": "not-a-real-type"}},
        )
        errors = await handler.validate(ctx)
        assert errors

    async def test_execute_with_missing_schema_routes_invalid(self) -> None:
        handler = ValidateSchemaHandler()
        ctx = PluginContext(inputs={"payload": {"id": 1}}, config={})
        result = await handler.execute(ctx)
        assert result["valid"] is False
        assert result["route"] == INVALID_ROUTE


class TestEnumMember:
    """The NodeType enum carries the new member (coordinates with sibling PR)."""

    def test_node_type_enum_has_validate_schema(self) -> None:
        from app.services.substrate.workflow_models import NodeType

        assert NodeType.VALIDATE_SCHEMA.value == "validate_schema"
        assert NodeType("validate_schema") is NodeType.VALIDATE_SCHEMA

    def test_handler_node_type_id_matches_enum(self) -> None:
        from app.services.substrate.workflow_models import NodeType

        assert ValidateSchemaHandler.node_type_id == NodeType.VALIDATE_SCHEMA.value


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
