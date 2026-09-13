"""Validation and manifest helpers for isolated benchmark run bundles."""

from __future__ import annotations

from typing import Any


def validate_legal_trace(
    trace: dict[str, Any], *, tool_call_budget: int, tick_budget: int
) -> dict[str, int]:
    """Validate a scripted-policy trace before it is eligible for scoring."""
    tool_calls = trace.get("tool_calls")
    initial_tick = trace.get("initial_tick")
    final_tick = trace.get("final_tick")
    tick_delta = trace.get("game_tick_delta")
    if not isinstance(tool_calls, int) or isinstance(tool_calls, bool):
        raise ValueError("trace tool_calls must be an integer")
    if not isinstance(initial_tick, int) or isinstance(initial_tick, bool):
        raise ValueError("trace initial_tick must be an integer")
    if not isinstance(final_tick, int) or isinstance(final_tick, bool):
        raise ValueError("trace final_tick must be an integer")
    if not isinstance(tick_delta, int) or isinstance(tick_delta, bool):
        raise ValueError("trace game_tick_delta must be an integer")
    if tool_calls < 0 or tool_calls > tool_call_budget:
        raise ValueError("trace exceeds tool-call budget")
    if final_tick < initial_tick or tick_delta != final_tick - initial_tick:
        raise ValueError("trace tick delta is inconsistent")
    if tick_delta > tick_budget:
        raise ValueError("trace exceeds tick budget")
    return {"tool_calls": tool_calls, "game_tick_delta": tick_delta}
