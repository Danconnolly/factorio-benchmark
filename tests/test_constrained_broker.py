"""Regression coverage for the constrained FastMCP broker's public tools."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).parents[1]
BROKER = REPOSITORY_ROOT / "src" / "factorio_benchmark" / "assets" / "scripts" / "factorio_constrained_broker.py"


class ConstrainedBrokerTests(unittest.TestCase):
    def test_exposed_tools_have_descriptions_without_rcon_connection(self) -> None:
        """FastMCP can inspect every broker tool before Factorio is available."""
        class Sender:
            def __init__(self, **_kwargs: object) -> None:
                pass

        class Service:
            def __init__(self, _sender: Sender) -> None:
                pass

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

        tools = asyncio.run(server.list_tools())
        self.assertEqual({tool.name for tool in tools}, {"observe_actor", "observe_local", "place", "interact_inventory", "wait"})
        self.assertTrue(all(tool.description and tool.description.strip() for tool in tools))


if __name__ == "__main__":
    unittest.main()
