#!/usr/bin/env python3
"""Constrained FastMCP broker; this process, never the agent, holds RCON access.

Run with the control virtualenv.  Only the five player actions below are
registered.  In particular this module deliberately exposes no generic RCON,
Lua, command, eval, or server administration tool.
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
from pathlib import Path
from typing import Any

SOURCE = "factorio-constrained-broker.v1"


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def runtime_check() -> int:
    """Check the exact external runtime before Factorio is provisioned."""
    try:
        from fastmcp import FastMCP
        from factorio_player_mcp.rcon import FactorioRconSender
        from factorio_player_mcp.service import ActorService
    except ImportError as error:
        print(f"unsupported: {error}")
        return 2
    parameters = inspect.signature(FastMCP.run).parameters
    if "transport" not in parameters or not ({"host", "port"} <= set(parameters) or any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())):
        print("unsupported: FastMCP.run cannot serve configured Streamable HTTP")
        return 2
    # References keep this a precise runtime capability check, rather than a
    # package-name-only claim.
    assert FactorioRconSender and ActorService
    print("supported: FastMCP Streamable HTTP and ActorService")
    return 0


def make_server(measurement_path: Path, transcript_path: Path) -> Any:
    from fastmcp import FastMCP
    from factorio_player_mcp.rcon import FactorioRconSender
    from factorio_player_mcp.service import ActorService

    service = ActorService(FactorioRconSender(
        host=os.environ["FACTORIO_RCON_HOST"], port=int(os.environ["FACTORIO_RCON_PORT"]),
        password=os.environ["FACTORIO_RCON_PASSWORD"],
    ))
    measurements: dict[str, Any] = {"source": SOURCE, "tool_calls": 0, "initial_tick": None, "final_tick": None}
    mcp = FastMCP("factorio-constrained-benchmark")

    def invoke(name: str, **arguments: Any) -> Any:
        try:
            result = getattr(service, name)(**arguments)
        except ValueError as error:
            result = {"status": "rejected", "reason": "invalid_request", "message": str(error)}
        # Every exposed action is charged by this broker, including failures.
        measurements["tool_calls"] += 1
        tick = result.get("tick") if isinstance(result, dict) else None
        if isinstance(tick, int):
            if measurements["initial_tick"] is None:
                measurements["initial_tick"] = tick
            measurements["final_tick"] = tick
        with transcript_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"tool": name, "arguments": arguments, "result": result}, sort_keys=True) + "\n")
        write_json(measurement_path, measurements)
        return result

    @mcp.tool
    def observe_actor() -> Any:
        """Return the controlled player's current state."""
        return invoke("observe_actor")

    @mcp.tool
    def observe_local(radius: int) -> Any:
        """Return nearby world state within the requested radius."""
        return invoke("observe_local", radius=radius)

    @mcp.tool
    def place(item: str, x: float, y: float, direction: str) -> Any:
        """Place an item at the requested position and direction."""
        return invoke("place", item=item, x=x, y=y, direction=direction)

    @mcp.tool
    def interact_inventory(x: float, y: float, item: str, count: int, operation: str, slot: str) -> Any:
        """Transfer items to or from an inventory at a position."""
        return invoke("interact_inventory", x=x, y=y, item=item, count=count, operation=operation, slot=slot)

    @mcp.tool
    def wait(ticks: int) -> Any:
        """Advance the game by the requested number of ticks."""
        return invoke("wait", ticks=ticks)

    return mcp


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-runtime", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int)
    parser.add_argument("--measurements", type=Path)
    parser.add_argument("--transcript", type=Path)
    args = parser.parse_args()
    if args.check_runtime:
        return runtime_check()
    if args.port is None or args.measurements is None or args.transcript is None:
        parser.error("--port, --measurements, and --transcript are required to serve")
    args.measurements.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.measurements, {"source": SOURCE, "tool_calls": 0, "initial_tick": 0, "final_tick": 0})
    make_server(args.measurements, args.transcript).run(transport="streamable-http", host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
