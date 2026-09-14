#!/usr/bin/env python3
"""A small untrusted agent that bridges an OpenAI-compatible model to MCP."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol, Sequence


DEFAULT_MODEL_ENDPOINT = "http://ollama.boodle.info:11434/v1"
DEFAULT_MODEL = "qwen3.8:latest"


class McpClient(Protocol):
    async def list_tools(self) -> Sequence[Any]: ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


PostJson = Callable[[str, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ConversationResult:
    reason: str
    turns: int


def openai_tools(mcp_tools: Sequence[Any]) -> list[dict[str, Any]]:
    """Translate the MCP tool catalog into Chat Completions function tools."""
    return [{"type": "function", "function": {
        "name": tool.name,
        "description": getattr(tool, "description", "") or "",
        "parameters": getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {"type": "object", "properties": {}},
    }} for tool in mcp_tools]


def mcp_client_config(config: dict[str, Any]) -> dict[str, Any]:
    """Accept exactly the runner's single constrained server configuration."""
    servers = config.get("mcpServers")
    if not isinstance(servers, dict) or set(servers) != {"factorio"}:
        raise RuntimeError("MCP config must provide only the factorio server")
    return config


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as error:
        raise RuntimeError(f"model request failed: {error}") from error


def log(event: str, **details: Any) -> None:
    print(json.dumps({"event": event, **details}, sort_keys=True, default=str), file=sys.stderr, flush=True)


async def run_conversation(client: McpClient, model_endpoint: str, model: str, prompt: str,
                           max_turns: int, post: PostJson = post_json) -> ConversationResult:
    available = {tool.name for tool in await client.list_tools()}
    tools = openai_tools(await client.list_tools())
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    endpoint = model_endpoint.rstrip("/") + "/chat/completions"
    for turn in range(1, max_turns + 1):
        request = {"model": model, "messages": list(messages), "tools": tools, "tool_choice": "auto", "stream": False}
        log("model_request", turn=turn, model=model, tool_count=len(tools))
        response = post(endpoint, request)
        try:
            message = response["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError("model response has no choices[0].message") from error
        tool_calls = message.get("tool_calls") or []
        messages.append({key: value for key, value in message.items() if key in {"role", "content", "tool_calls"}})
        if not tool_calls:
            answer = message.get("content") or ""
            print(answer, flush=True)
            log("final_answer", turn=turn)
            return ConversationResult("final_answer", turn)
        for call in tool_calls:
            function = call.get("function", {})
            name = function.get("name")
            raw_arguments = function.get("arguments", "{}")
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
                if not isinstance(arguments, dict):
                    raise ValueError("arguments must be an object")
            except (json.JSONDecodeError, ValueError) as error:
                result: Any = {"error": f"invalid tool arguments: {error}"}
            else:
                if name not in available:
                    result = {"error": "requested tool is not in the constrained MCP catalog"}
                else:
                    log("tool_call", turn=turn, tool=name, arguments=arguments)
                    try:
                        result = await client.call_tool(name, arguments)
                    except Exception as error:  # Tool failures are model-visible, not agent-fatal.
                        result = {"error": str(error)}
            log("tool_result", turn=turn, tool=name, result=result)
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": json.dumps(result, default=str, sort_keys=True)})
    log("turn_limit", turns=max_turns)
    return ConversationResult("turn_limit", max_turns)


async def main_async(args: argparse.Namespace) -> int:
    prompt_path = os.environ.get("BENCHMARK_AGENT_PROMPT")
    config_path = os.environ.get("BENCHMARK_AGENT_MCP_CONFIG")
    if not prompt_path or not config_path:
        raise RuntimeError("BENCHMARK_AGENT_PROMPT and BENCHMARK_AGENT_MCP_CONFIG are required")
    with open(prompt_path, encoding="utf-8") as stream:
        prompt = stream.read()
    with open(config_path, encoding="utf-8") as stream:
        config = json.load(stream)
    from fastmcp import Client
    async with Client(mcp_client_config(config), name="factorio-benchmark-external-agent") as client:
        result = await run_conversation(client, args.model_endpoint, args.model, prompt, args.max_turns)
    log("agent_exit", reason=result.reason, turns=result.turns)
    return 0


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-endpoint", default=DEFAULT_MODEL_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-turns", type=int, default=12)
    args = parser.parse_args(arguments)
    if args.max_turns < 1:
        parser.error("--max-turns must be positive")
    return args


def main() -> int:
    try:
        return asyncio.run(main_async(parse_args()))
    except Exception as error:
        log("agent_error", error=str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
