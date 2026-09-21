"""Benchmark-owned in-process session callback contract.

The callback is intentionally untrusted: it receives neither lifecycle nor
evaluator credentials, and its result cannot affect the independent score.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class CallbackRequest:
    """Everything an in-process agent may receive from a benchmark session."""

    prompt: str
    mcp_config: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"prompt": self.prompt, "mcp_config": dict(self.mcp_config)}


def validate_callback_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Retain only agent text; score and measurements remain benchmark-owned."""
    if not isinstance(result, Mapping):
        raise ValueError("callback result must be a mapping")
    answer = result.get("answer", "")
    if not isinstance(answer, str):
        raise ValueError("callback answer must be a string")
    return {"answer": answer}
