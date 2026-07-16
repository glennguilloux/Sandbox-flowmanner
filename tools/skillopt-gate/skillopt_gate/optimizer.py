"""Optimizer step for skillopt-gate.

Two implementations of the ``Optimizer`` protocol:

  * ``DeterministicOptimizer`` — wraps pre-supplied candidate edits
    (hypotheses you wrote, or edits proposed by another agent). Always
    runnable; no API key. This is the default offline path.
  * ``LLMOptimizer`` — asks an OpenAI-compatible chat model for edits.
    Key-gated: it is never imported at package load, so the tool works
    without the ``openai`` package or any key.

Both return a ``Patch`` (list of Edit) that the runner feeds to the gate.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import Edit, Patch


@runtime_checkable
class Optimizer(Protocol):
    def propose(self, skill: str, *, failures: list[str] | None = None) -> Patch:
        """Return a candidate patch for the given skill text."""
        ...


class DeterministicOptimizer:
    """Use a fixed set of candidate edits (the offline default)."""

    def __init__(self, edits: list[Edit] | None = None, *, reasoning: str = "") -> None:
        self._edits = edits or []
        self._reasoning = reasoning

    def propose(self, skill: str, *, failures: list[str] | None = None) -> Patch:
        return Patch(edits=list(self._edits), reasoning=self._reasoning)

    @classmethod
    def from_dicts(
        cls, edits: list[dict], *, reasoning: str = ""
    ) -> "DeterministicOptimizer":
        return cls([Edit.from_dict(e) for e in edits], reasoning=reasoning)


class LLMOptimizer:
    """Ask an OpenAI-compatible chat model for bounded skill edits.

    The model is given ONLY the skill + a short failure summary and must
    return JSON ``{"edits": [...], "reasoning": "..."}``. The gate, not
    the model, decides acceptance — so a weak/biased proposal is simply
    rejected and the live skill is untouched.
    """

    def __init__(
        self,
        model: str,
        *,
        api_key_env: str = "OPENAI_API_KEY",
        base_url: str | None = None,
        temperature: float = 0.2,
    ) -> None:
        self.model = model
        self.api_key_env = api_key_env
        self.base_url = base_url
        self.temperature = temperature

    def propose(self, skill: str, *, failures: list[str] | None = None) -> Patch:
        from openai import OpenAI  # lazy import — keeps the tool key-free until used

        import os

        from .types import Patch as _Patch  # noqa: F811

        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"LLMOptimizer requires {self.api_key_env} to be set; "
                f"or pass a DeterministicOptimizer for offline runs."
            )
        client = OpenAI(api_key=api_key, base_url=self.base_url)
        fail_text = (
            "\n".join(f"- {f}" for f in (failures or []))
            or "(no failure detail supplied)"
        )
        system = (
            "You improve an agent skill document. Propose up to a few BOUNDED "
            'edits as JSON: {"edits": [{"op": "add"|"delete"|"replace", '
            '"content": str, "target": str}], "reasoning": str}. '
            "Use 'add' to append content. 'replace'/'delete' need an exact "
            "'target' substring present in the skill. Do not touch text inside "
            "the SKILLOPT_APPENDIX markers. Return JSON only."
        )
        user = (
            f"## Current skill\n{skill}\n\n## Recent failures to address\n{fail_text}"
        )
        resp = client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
        )
        import json

        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        return _Patch.from_dict(data)
