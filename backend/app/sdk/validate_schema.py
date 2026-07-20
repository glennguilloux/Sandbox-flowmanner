"""validate_schema node handler — asserts an incoming payload against a schema.

A ``validate_schema`` node checks the payload flowing into it against a
JSON-Schema config declared on the node. On a match, execution continues down
the main (default) output edge; on a mismatch, the handler routes to the
``on_invalid`` edge instead of raising, so the workflow author can branch on
invalid data (log it, repair it, escalate, etc.).

Two entry points, both derived from the SAME schema so they never disagree:

- :meth:`ValidateSchemaHandler.validate` — pre-execution validation
  (``BaseNodeHandler.validate`` contract). Returns a list of human-readable
  error strings; an empty list means the payload is valid. This is what
  catches a *missing required field* BEFORE the node executes.
- :meth:`ValidateSchemaHandler.execute` — runtime execution. Re-runs the
  assertion and emits routing outputs (``valid``, ``route``, ``errors``,
  ``payload``) so the interpreter can pick the ``on_invalid`` edge on mismatch.

Config shape (read from ``context.config`` / the node's ``schema`` config)::

    {
        "schema": {                      # a JSON Schema (draft 2020-12 / 7)
            "type": "object",
            "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
            "required": ["id"],
        },
        "payload_key": "payload",        # optional; which input holds the payload
        "on_invalid": "on_invalid",       # optional; the invalid-route edge label
    }

``jsonschema`` and ``pydantic`` are both in-stack; this handler uses
``jsonschema`` because the node config *is* a JSON Schema (no model synthesis
step needed) and it yields every validation error, not just the first.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from app.sdk.base import BaseNodeHandler

if TYPE_CHECKING:
    from app.sdk.context import PluginContext

#: Default output edge label taken when the payload matches the schema.
DEFAULT_ROUTE = "default"
#: Default output edge label taken when the payload fails validation.
INVALID_ROUTE = "on_invalid"
#: Default input key that carries the payload to validate.
DEFAULT_PAYLOAD_KEY = "payload"


class ValidateSchemaHandler(BaseNodeHandler):
    """Assert an incoming payload against a JSON-Schema config.

    Matches -> continues down the default edge.
    Mismatch (or missing required field) -> routes to the ``on_invalid`` edge.
    """

    node_type_id = "validate_schema"

    # ── Schema resolution ─────────────────────────────────────────

    @staticmethod
    def _resolve_schema(context: PluginContext) -> dict[str, Any] | None:
        """Read the JSON Schema from node config (config first, then input)."""
        schema = context.get_config("schema")
        if schema is None:
            # Fall back to a same-named input for callers that pass the schema
            # inline alongside the payload.
            schema = context.get_input("schema")
        return schema if isinstance(schema, dict) else None

    @staticmethod
    def _resolve_payload(context: PluginContext) -> tuple[str, Any]:
        """Return ``(payload_key, payload_value)`` for the incoming payload."""
        payload_key = context.get_config("payload_key") or DEFAULT_PAYLOAD_KEY
        return payload_key, context.get_input(payload_key)

    @staticmethod
    def _invalid_route(context: PluginContext) -> str:
        """The edge label to take on a validation failure."""
        route = context.get_config("on_invalid")
        return route if isinstance(route, str) and route else INVALID_ROUTE

    # ── Core validation ───────────────────────────────────────────

    def _collect_errors(self, context: PluginContext) -> list[str]:
        """Validate the payload against the schema; return error strings.

        An empty list means the payload is valid. Configuration problems
        (missing/invalid schema) are surfaced as errors too, so a
        misconfigured node fails closed rather than silently passing.
        """
        schema = self._resolve_schema(context)
        if schema is None:
            return ["validate_schema node is missing a 'schema' config"]

        # Guard against an invalid schema document itself.
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:  # pragma: no cover - defensive
            return [f"Invalid schema config: {exc.message}"]

        payload_key, payload = self._resolve_payload(context)
        if payload is None and payload_key not in context.inputs:
            return [f"Required input '{payload_key}' is missing"]

        validator = Draft202012Validator(schema)
        errors: list[str] = []
        for err in sorted(validator.iter_errors(payload), key=str):
            location = "/".join(str(p) for p in err.absolute_path)
            prefix = f"{location}: " if location else ""
            errors.append(f"{prefix}{err.message}")
        return errors

    # ── BaseNodeHandler contract ──────────────────────────────────

    async def validate(self, context: PluginContext) -> list[str]:
        """Pre-execution validation.

        Returns a list of human-readable error strings (empty == valid). This
        is what catches a *missing required field* before the node executes.
        """
        return self._collect_errors(context)

    async def execute(self, context: PluginContext) -> dict[str, Any]:
        """Validate at runtime and emit routing outputs.

        Never raises on a payload mismatch: instead it sets ``route`` to the
        ``on_invalid`` edge so the interpreter branches to the invalid path.
        The ``valid`` / ``errors`` / ``payload`` outputs let downstream nodes
        inspect the result.
        """
        errors = self._collect_errors(context)
        _payload_key, payload = self._resolve_payload(context)
        valid = not errors
        route = DEFAULT_ROUTE if valid else self._invalid_route(context)

        result: dict[str, Any] = {
            "valid": valid,
            "route": route,
            "errors": errors,
            "payload": payload,
        }
        for key, value in result.items():
            context.set_output(key, value)

        if valid:
            context.logger.info("validate_schema: payload matched schema")
        else:
            context.logger.info(
                "validate_schema: payload failed validation (%d error(s)) -> routing to '%s'",
                len(errors),
                route,
            )
        return result


__all__ = [
    "DEFAULT_PAYLOAD_KEY",
    "DEFAULT_ROUTE",
    "INVALID_ROUTE",
    "ValidateSchemaHandler",
]
