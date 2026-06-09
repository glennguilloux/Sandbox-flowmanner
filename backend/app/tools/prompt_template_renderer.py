"""
LLM Operations Tools — Prompt Template Renderer.

prompt_template_renderer → Inject variables safely into complex prompt
    templates using Jinja2 with nested variable support, built-in filters,
    template validation, and variable schema introspection.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

_SUPPORTED_FILTERS = [
    "default_ext",
    "to_json",
    "trim",
    "upper",
    "lower",
    "code_block",
    "length",
    "first_sentence",
]


class PromptTemplateRendererInput(ToolInput):
    """Input schema: template, variables, engine, validate_only, strict_mode, trim_blocks, autoescape."""

    template: str | list[dict[str, str]] = Field(
        ...,
        min_length=1,
        description="Template string with {{ variable }} placeholders or list of chat messages [{role, content}]",
    )
    variables: dict[str, Any] | None = Field(
        None,
        description="Dictionary of variable names to their values for substitution",
    )
    engine: Literal["jinja2", "fstring", "mustache"] = Field(
        "jinja2",
        description="Template engine: 'jinja2' for logic-rich, 'fstring' for simple {var}, 'mustache' for logic-less",
    )
    validate_only: bool = Field(
        False,
        description="If True, only validate and extract variables without rendering",
    )
    strict_variables: bool = Field(
        True,
        description="If True, raise error when a variable is undefined. If False, leave unchanged.",
    )
    trim_blocks: bool = Field(
        True,
        description="Remove first newline after template tags",
    )
    autoescape: bool = Field(
        False,
        description="Enable HTML auto-escaping of variable values",
    )
    custom_filters: dict[str, str] | None = Field(
        None,
        description="Custom Jinja2 filter definitions (name -> Python expression)",
    )


class PromptTemplateRendererTool(BaseTool):
    """Render prompt templates with variable injection using Jinja2."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="prompt_template_renderer",
            name="Prompt Template Renderer",
            description=(
                "Inject variables safely into complex prompt templates using "
                "Jinja2 templating. Supports nested variable references, "
                "conditionals, loops, built-in filters, template validation, "
                "and variable schema introspection. Falls back to simple "
                "substitution if Jinja2 is unavailable."
            ),
            category="llm-operations",
            input_schema=PromptTemplateRendererInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "rendered": {"type": "string"},
                    "variables_provided": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "variable_count": {"type": "integer"},
                    "variables_extracted": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "unresolved_placeholders": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "fully_resolved": {"type": "boolean"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["llm", "prompt", "template", "jinja2", "rendering"],
            requires_auth=True,
            timeout_seconds=15,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = PromptTemplateRendererInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        variables = validated.variables or {}

        # Extract all variable names from template
        extracted = self._extract_variables(validated.template)

        if validated.validate_only:
            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "variables_extracted": extracted,
                    "variable_count": len(extracted),
                    "provided_variables": list(variables.keys()),
                    "missing_variables": [v for v in extracted if v not in variables],
                    "fully_resolved": all(v in variables for v in extracted),
                    "available_filters": _SUPPORTED_FILTERS,
                    "success": True,
                },
            )

        try:
            rendered = await self._render(
                validated.template,
                variables,
                strict=validated.strict_variables,
                engine=validated.engine,
                trim_blocks=validated.trim_blocks,
                autoescape=validated.autoescape,
                custom_filters=validated.custom_filters,
            )
            unresolved = self._find_unresolved(rendered)

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "rendered": rendered,
                    "variables_provided": list(variables.keys()),
                    "variable_count": len(variables),
                    "variables_extracted": extracted,
                    "unresolved_placeholders": unresolved,
                    "fully_resolved": len(unresolved) == 0,
                    "success": True,
                },
            )
        except Exception as e:
            logger.exception("prompt_template_renderer failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    async def _render(
        self,
        template: str | list,
        variables: dict,
        strict: bool = True,
        engine: str = "jinja2",
        trim_blocks: bool = True,
        autoescape: bool = False,
        custom_filters: dict[str, str] | None = None,
    ) -> str:
        # Extract plain text from chat message list
        if isinstance(template, list):
            template = "\n".join(
                (
                    f"{{{{ {'assistant' if m.get('role') == 'assistant' else m.get('role', 'user')}_message }}}}"
                    if m.get("role") in ("user", "assistant", "system")
                    and m.get("content", "").startswith("{{")
                    else m.get("content", "")
                )
                for m in template
            )

        # Handle non-Jinja2 engines
        if engine == "fstring":
            return self._fstring_render(template, variables)
        elif engine == "mustache":
            return self._mustache_render(template, variables)

        try:
            from jinja2 import (
                BaseLoader,
                SandboxedEnvironment,
                TemplateSyntaxError,
                UndefinedError,
            )

            env = SandboxedEnvironment(
                loader=BaseLoader(),
                undefined=self._strict_undefined if strict else None,
                autoescape=autoescape,
                trim_blocks=trim_blocks,
            )
            env.filters["default_ext"] = lambda v, d: v if v else d
            env.filters["to_json"] = lambda v: __import__("json").dumps(v, indent=2)
            env.filters["trim"] = lambda v: v.strip() if isinstance(v, str) else v
            env.filters["upper"] = lambda v: v.upper() if isinstance(v, str) else v
            env.filters["lower"] = lambda v: v.lower() if isinstance(v, str) else v
            env.filters["code_block"] = lambda v, lang="": (
                f"```{lang}\n{v}\n```" if v else ""
            )
            env.filters["length"] = len
            env.filters["first_sentence"] = lambda v: (
                (v.split(".")[0].strip() + ".") if isinstance(v, str) and v else v
            )

            # Register custom user-provided filters
            if custom_filters:
                for name, expr in custom_filters.items():
                    try:
                        compiled = compile(expr, "<custom_filter>", "eval")
                        env.filters[name] = lambda v, _c=compiled: eval(
                            _c, {"v": v, "__builtins__": {}}, {}
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to register custom filter '%s': %s", name, e
                        )

            tmpl = env.from_string(template)
            return tmpl.render(**variables)

        except ImportError:
            logger.debug("Jinja2 not installed, using simple variable substitution")
            return (
                self._simple_substitute(template, variables)
                if strict
                else self._simple_substitute(template, variables)
            )

        except TemplateSyntaxError as e:
            raise ValueError(f"Template syntax error at line {e.lineno}: {e.message}")

        except UndefinedError as e:
            raise ValueError(f"Undefined variable in template: {e.message}")

    def _simple_substitute(self, template: str, variables: dict) -> str:
        import re

        def replace_match(match):
            expr = match.group(1).strip()
            if expr in variables:
                return str(variables[expr])
            or_match = re.match(r'^(\w+)\s+or\s+["\'](.+?)["\']$', expr)
            if or_match:
                return str(variables.get(or_match.group(1), or_match.group(2)))
            parts = expr.split("|")
            var_name = parts[0].strip()
            if var_name in variables:
                val = variables[var_name]
                for filt in parts[1:]:
                    filt = filt.strip()
                    if filt == "upper" and isinstance(val, str):
                        val = val.upper()
                    elif filt == "lower" and isinstance(val, str):
                        val = val.lower()
                    elif filt == "trim" and isinstance(val, str):
                        val = val.strip()
                return str(val)
            return match.group(0)

        return re.sub(r"\{\{(.+?)\}\}", replace_match, template, flags=re.DOTALL)

    def _find_unresolved(self, text: str) -> list[str]:
        import re

        return [m.strip() for m in re.findall(r"\{\{(.+?)\}\}", text)]

    def _extract_variables(self, template: str) -> list[str]:
        """Extract all variable names from the template."""
        import re

        # Match {{ variable_name }} and {{ variable_name|filter }}
        matches = re.findall(r"\{\{\s*(\w+)(?:\s*[\|\}])", template)
        seen = set()
        result = []
        for m in matches:
            if m not in seen and m not in (
                "else",
                "endif",
                "endfor",
                "endblock",
                "endmacro",
            ):
                seen.add(m)
                result.append(m)
        return result

    @staticmethod
    def _strict_undefined(*args, **kwargs):
        from jinja2 import UndefinedError

        raise UndefinedError(
            f"Variable '{args[0] if args else 'unknown'}' is undefined"
        )

    def _fstring_render(self, template: str, variables: dict) -> str:
        """Simple Python f-string-style {variable} substitution."""
        import re

        def replacer(m):
            key = m.group(1).strip()
            return str(variables.get(key, m.group(0)))

        return re.sub(r"\{([^}]+)\}", replacer, template)

    def _mustache_render(self, template: str, variables: dict) -> str:
        """Mustache-style {{variable}} substitution without logic."""
        import re

        def replacer(m):
            key = m.group(1).strip()
            return str(variables.get(key, m.group(0)))

        return re.sub(r"\{\{\s*(\w+)\s*\}\}", replacer, template)


register_tool(PromptTemplateRendererTool())
