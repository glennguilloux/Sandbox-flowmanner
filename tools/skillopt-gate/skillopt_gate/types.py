"""Shared data types for skillopt-gate.

These mirror the shapes in microsoft/SkillOpt (``skillopt/types.py``,
``skillopt/optimizer/skill.py``) but are trimmed to what the gate needs:
add / delete / replace edits on a single markdown skill document.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

EditOp = Literal["add", "delete", "replace"]


@dataclass
class Edit:
    """A single bounded edit to the skill document.

    * ``add``    — append ``content`` (``target`` ignored).
    * ``delete`` — remove ``target`` (``content`` ignored).
    * ``replace``— replace ``target`` with ``content``.
    """

    op: EditOp
    content: str = ""
    target: str = ""

    def to_dict(self) -> dict:
        return {"op": self.op, "content": self.content, "target": self.target}

    @classmethod
    def from_dict(cls, d: dict) -> "Edit":
        return cls(op=d["op"], content=d.get("content", ""), target=d.get("target", ""))


@dataclass
class Patch:
    """A candidate patch = a set of edits + free-form reasoning."""

    edits: list[Edit] = field(default_factory=list)
    reasoning: str = ""

    def to_dict(self) -> dict:
        return {
            "edits": [e.to_dict() for e in self.edits],
            "reasoning": self.reasoning,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Patch":
        return cls(
            edits=[Edit.from_dict(e) for e in d.get("edits", [])],
            reasoning=d.get("reasoning", ""),
        )
