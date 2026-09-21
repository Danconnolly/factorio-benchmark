"""Benchmark-owned in-process session callback contract.

The callback is intentionally untrusted: it receives neither lifecycle nor
evaluator credentials, and its result cannot affect the independent score.
"""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
import time
from typing import Any, Awaitable, Callable, Mapping


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


AsyncCallback = Callable[[CallbackRequest], Awaitable[Mapping[str, Any]]]


async def run_callback_attempt(callback: AsyncCallback, request: CallbackRequest, *,
                               timeout_seconds: float) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
    """Run a cooperative callback within its wall-clock budget.

    Callbacks are deliberately asynchronous: cancellation closes the callback's
    MCP client context before this function returns, so callers can stop the
    broker before creating evaluator credentials. A callback that suppresses
    cancellation violates this contract and is not supported.
    """
    started = time.monotonic()
    task: asyncio.Future[Mapping[str, Any]] | None = None
    try:
        task = asyncio.ensure_future(callback(request))
        result = await asyncio.wait_for(task, timeout=timeout_seconds)
        return "completed_pending_budget", {
            "kind": "callback_returned", "wall_clock_seconds": time.monotonic() - started,
        }, validate_callback_result(result)
    except asyncio.TimeoutError:
        return "agent_callback_timeout", {
            "kind": "timeout", "wall_clock_seconds": time.monotonic() - started,
        }, None
    except Exception as error:
        return "agent_callback_error", {
            "kind": "callback_error", "wall_clock_seconds": time.monotonic() - started,
            "error": str(error),
        }, None
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
