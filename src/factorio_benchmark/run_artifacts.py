"""Validation and manifest helpers for isolated benchmark run bundles."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a regular file."""
    if not path.is_file():
        raise ValueError(f"artifact does not exist or is not a file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_pinned_archive(path: Path, expected_sha256: str, artifact_name: str) -> str:
    """Verify that an input archive is the artifact pinned by its scenario."""
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(f"{artifact_name} hash does not match scenario")
    return actual_sha256


def validate_legal_trace(
    trace: dict[str, Any], *, tool_call_budget: int, tick_budget: int, wall_clock_budget: float
) -> dict[str, int | float]:
    """Validate a scripted-policy trace before it is eligible for scoring."""
    tool_calls = trace.get("tool_calls")
    initial_tick = trace.get("initial_tick")
    final_tick = trace.get("final_tick")
    tick_delta = trace.get("game_tick_delta")
    wall_clock_seconds = trace.get("wall_clock_seconds")
    if not isinstance(tool_calls, int) or isinstance(tool_calls, bool):
        raise ValueError("trace tool_calls must be an integer")
    if not isinstance(initial_tick, int) or isinstance(initial_tick, bool):
        raise ValueError("trace initial_tick must be an integer")
    if not isinstance(final_tick, int) or isinstance(final_tick, bool):
        raise ValueError("trace final_tick must be an integer")
    if not isinstance(tick_delta, int) or isinstance(tick_delta, bool):
        raise ValueError("trace game_tick_delta must be an integer")
    if not isinstance(wall_clock_seconds, (int, float)) or isinstance(wall_clock_seconds, bool):
        raise ValueError("trace wall_clock_seconds must be a number")
    if tool_calls < 0 or tool_calls > tool_call_budget:
        raise ValueError("trace exceeds tool-call budget")
    if final_tick < initial_tick or tick_delta != final_tick - initial_tick:
        raise ValueError("trace tick delta is inconsistent")
    if tick_delta > tick_budget:
        raise ValueError("trace exceeds tick budget")
    if wall_clock_seconds < 0 or wall_clock_seconds > wall_clock_budget:
        raise ValueError("trace exceeds wall-clock budget")
    return {
        "tool_calls": tool_calls,
        "game_tick_delta": tick_delta,
        "wall_clock_seconds": wall_clock_seconds,
    }
