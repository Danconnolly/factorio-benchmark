"""Tests for the untrusted OpenAI-compatible external agent."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import unittest
from pathlib import Path

from factorio_benchmark.agent_runner import build_run_manifest

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("openai_mcp_agent", ROOT / "scripts" / "openai_mcp_agent.py")
assert SPEC and SPEC.loader
agent = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = agent
SPEC.loader.exec_module(agent)


class FakeTool:
    def __init__(self, name: str, description: str, input_schema: dict[str, object]) -> None:
        self.name = name
        self.description = description
        self.inputSchema = input_schema


class FakeMcpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def list_tools(self) -> list[FakeTool]:
        return [FakeTool("observe_actor", "Observe the player.", {"type": "object", "properties": {}})]

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        self.calls.append((name, arguments))
        return {"status": "completed", "tick": 7}


class OpenAiMcpAgentTests(unittest.TestCase):
    def test_default_api_model_is_runnable_alias_while_runner_records_pinned_identity(self) -> None:
        """The Ollama request name is distinct from the benchmark identity."""
        pinned_identity = "qwen3.8:latest@sha256:22130167c4c20e20c7b71454612966ca8e8171e9b3cc8ab6ce8aa6cbfec79643"
        self.assertEqual(agent.parse_args([]).model, "qwen3.8:latest")
        manifest = build_run_manifest(
            scenario_id="smelt", model_id=pinned_identity, agent_command=["agent"], prompt_sha256="a" * 64,
            control_metadata={}, terminal_status="agent_timeout", agent_exit={"kind": "timeout"},
            artifacts={}, trusted_measurements=None, evaluator_projection=None, score=None,
        )
        self.assertEqual(manifest["model_id"], pinned_identity)

    def test_passes_the_full_mcp_servers_config_to_fastmcp(self) -> None:
        config = {"mcpServers": {"factorio": {"transport": "streamable-http", "url": "http://127.0.0.1:38123/mcp"}}}
        self.assertEqual(agent.mcp_client_config(config), config)

    def test_converts_only_mcp_tools_to_openai_function_schemas(self) -> None:
        tools = agent.openai_tools([FakeTool("observe_actor", "Observe the player.", {"type": "object", "properties": {}})])
        self.assertEqual(tools, [{"type": "function", "function": {"name": "observe_actor", "description": "Observe the player.", "parameters": {"type": "object", "properties": {}}}}])

    def test_executes_requested_tool_and_returns_final_answer(self) -> None:
        client = FakeMcpClient()
        requests: list[dict[str, object]] = []
        responses = iter([
            {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "observe_actor", "arguments": "{}"}}]}}]},
            {"choices": [{"message": {"role": "assistant", "content": "Done.", "tool_calls": []}}]},
        ])

        def post(_: str, request: dict[str, object]) -> dict[str, object]:
            requests.append(request)
            return next(responses)

        result = asyncio.run(agent.run_conversation(client, "http://model/v1", "pinned-model", "goal", 2, post))
        self.assertEqual(result, agent.ConversationResult("final_answer", 2))
        self.assertEqual(client.calls, [("observe_actor", {})])
        self.assertEqual(requests[0]["tools"][0]["function"]["name"], "observe_actor")
        self.assertEqual(requests[1]["messages"][-1]["role"], "tool")

    def test_stops_at_turn_limit_without_unrequested_calls(self) -> None:
        client = FakeMcpClient()
        calls = 0

        def post(_: str, __: dict[str, object]) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{"id": f"call-{calls}", "type": "function", "function": {"name": "observe_actor", "arguments": "{}"}}]}}]}

        result = asyncio.run(agent.run_conversation(client, "http://model/v1", "pinned-model", "goal", 2, post))
        self.assertEqual(result, agent.ConversationResult("turn_limit", 2))
        self.assertEqual(client.calls, [("observe_actor", {}), ("observe_actor", {})])

    def test_source_has_no_direct_control_or_accounting_paths(self) -> None:
        source = (ROOT / "scripts" / "openai_mcp_agent.py").read_text(encoding="utf-8").lower()
        for forbidden in ("rcon", "factorio_constrained_broker", "broker-measurements", "write_text", "pathlib"):
            self.assertNotIn(forbidden, source)
