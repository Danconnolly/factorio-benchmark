"""Regression coverage for the constrained FastMCP broker's public tools."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).parents[1]
BROKER = REPOSITORY_ROOT / "src" / "factorio_benchmark" / "assets" / "scripts" / "factorio_constrained_broker.py"


class ConstrainedBrokerTests(unittest.TestCase):
    def test_validation_error_is_rejected_and_charged(self) -> None:
        """Player validation errors remain visible to the agent as tool results."""
        class Sender:
            def __init__(self, **_kwargs: object) -> None:
                pass

        class Service:
            def __init__(self, _sender: Sender) -> None:
                pass

            def interact_inventory(self, **_kwargs: object) -> object:
                if _kwargs["operation"] == "invalid":
                    raise ValueError("operation must be deposit or withdraw")
                raise RuntimeError("RCON connection lost")

        class FastMCP:
            def __init__(self, _name: str) -> None:
                self.tools: list[object] = []

            def tool(self, function: object) -> object:
                self.tools.append(function)
                return function

        fastmcp = types.ModuleType("fastmcp")
        fastmcp.FastMCP = FastMCP
        rcon = types.ModuleType("factorio_player_mcp.rcon")
        rcon.FactorioRconSender = Sender
        service = types.ModuleType("factorio_player_mcp.service")
        service.ActorService = Service
        package = types.ModuleType("factorio_player_mcp")
        package.__path__ = []
        spec = importlib.util.spec_from_file_location("constrained_broker_validation_error", BROKER)
        assert spec and spec.loader
        broker = importlib.util.module_from_spec(spec)

        with patch.dict(sys.modules, {
            "fastmcp": fastmcp,
            "factorio_player_mcp": package,
            "factorio_player_mcp.rcon": rcon,
            "factorio_player_mcp.service": service,
        }):
            spec.loader.exec_module(broker)
            with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {
                "FACTORIO_RCON_HOST": "127.0.0.1",
                "FACTORIO_RCON_PORT": "27015",
                "FACTORIO_RCON_PASSWORD": "unused",
            }, clear=False):
                measurement_path = Path(directory) / "measurements.json"
                transcript_path = Path(directory) / "transcript.jsonl"
                server = broker.make_server(measurement_path, transcript_path)
                interact_inventory = next(tool for tool in server.tools if tool.__name__ == "interact_inventory")
                result = interact_inventory(0, 0, "iron-ore", 1, "invalid", "input")

                self.assertEqual(result, {
                    "status": "rejected",
                    "reason": "invalid_request",
                    "message": "operation must be deposit or withdraw",
                })
                self.assertEqual(json.loads(measurement_path.read_text(encoding="utf-8"))["tool_calls"], 1)
                self.assertEqual(json.loads(transcript_path.read_text(encoding="utf-8")), {
                    "tool": "interact_inventory",
                    "arguments": {"x": 0, "y": 0, "item": "iron-ore", "count": 1, "operation": "invalid", "slot": "input"},
                    "result": result,
                })
                with self.assertRaisesRegex(RuntimeError, "RCON connection lost"):
                    interact_inventory(0, 0, "iron-ore", 1, "infrastructure", "input")

    def test_exposed_tools_have_descriptions_without_rcon_connection(self) -> None:
        """FastMCP can inspect every broker tool before Factorio is available."""
        class Sender:
            def __init__(self, **_kwargs: object) -> None:
                pass

        class Service:
            def __init__(self, _sender: Sender) -> None:
                pass

        class FastMCP:
            def __init__(self, _name: str) -> None:
                self.tools: list[object] = []

            def tool(self, function: object) -> object:
                self.tools.append(function)
                return function

        fastmcp = types.ModuleType("fastmcp")
        fastmcp.FastMCP = FastMCP
        rcon = types.ModuleType("factorio_player_mcp.rcon")
        rcon.FactorioRconSender = Sender
        service = types.ModuleType("factorio_player_mcp.service")
        service.ActorService = Service
        package = types.ModuleType("factorio_player_mcp")
        package.__path__ = []
        spec = importlib.util.spec_from_file_location("constrained_broker_under_test", BROKER)
        assert spec and spec.loader
        broker = importlib.util.module_from_spec(spec)

        with patch.dict(sys.modules, {
            "fastmcp": fastmcp,
            "factorio_player_mcp": package,
            "factorio_player_mcp.rcon": rcon,
            "factorio_player_mcp.service": service,
        }):
            spec.loader.exec_module(broker)
            with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {
                "FACTORIO_RCON_HOST": "127.0.0.1",
                "FACTORIO_RCON_PORT": "27015",
                "FACTORIO_RCON_PASSWORD": "unused",
            }, clear=False):
                server = broker.make_server(Path(directory) / "measurements.json", Path(directory) / "transcript.jsonl")

        self.assertEqual({tool.__name__ for tool in server.tools}, {"observe_actor", "observe_local", "place", "interact_inventory", "wait"})
        self.assertTrue(all(tool.__doc__ and tool.__doc__.strip() for tool in server.tools))


if __name__ == "__main__":
    unittest.main()
