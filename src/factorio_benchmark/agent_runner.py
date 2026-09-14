"""Security-critical, Factorio-free primitives for external agent attempts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


BROKER_MEASUREMENT_SOURCE = "factorio-constrained-broker.v1"
_SECRET_ARTIFACT_MARKERS = ("password", "credential", "secret", "token")


@dataclass(frozen=True)
class AgentRunConfiguration:
    """Explicit identity and executable for one external agent attempt."""

    model_id: str
    agent_command: tuple[str, ...]


def validate_agent_configuration(configuration: AgentRunConfiguration) -> None:
    if not configuration.model_id.strip():
        raise ValueError("model ID must be non-empty")
    if not configuration.agent_command or not all(part for part in configuration.agent_command):
        raise ValueError("agent command must be a non-empty argument array")


def build_agent_mcp_config(broker_url: str) -> dict[str, Any]:
    """Expose only FastMCP's remote constrained-broker transport to an agent."""
    if not broker_url.startswith("http://127.0.0.1:"):
        raise ValueError("broker URL must be loopback HTTP")
    return {"mcpServers": {"factorio": {"transport": "streamable-http", "url": broker_url}}}


def build_agent_environment(*, base_environment: Mapping[str, str], prompt_path: str, mcp_config_path: str) -> dict[str, str]:
    """Return the deliberately narrow environment visible to an agent process."""
    environment = {key: value for key, value in base_environment.items() if key in {"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ"}}
    environment.update({"BENCHMARK_AGENT_PROMPT": prompt_path, "BENCHMARK_AGENT_MCP_CONFIG": mcp_config_path})
    return environment


def build_graphical_client_environment(base_environment: Mapping[str, str]) -> dict[str, str]:
    """Supply the local Wayland session defaults needed by the Factorio client."""
    environment = dict(base_environment)
    environment.setdefault("XDG_RUNTIME_DIR", "/run/user/1000")
    environment.setdefault("WAYLAND_DISPLAY", "wayland-0")
    environment.setdefault("SDL_VIDEODRIVER", "wayland")
    return environment


def validate_trusted_measurements(measurements: Mapping[str, Any], *, tool_call_budget: int, tick_budget: int) -> dict[str, int]:
    """Accept only counters emitted by the constrained broker, never agent text."""
    if measurements.get("source") != BROKER_MEASUREMENT_SOURCE:
        raise ValueError("measurements are not from the trusted broker")
    values = {name: measurements.get(name) for name in ("tool_calls", "initial_tick", "final_tick")}
    if any(not isinstance(value, int) or isinstance(value, bool) for value in values.values()):
        raise ValueError("trusted measurements must contain integer counters")
    tool_calls, initial_tick, final_tick = values.values()
    if tool_calls == 0:
        raise ValueError("trusted measurements contain no broker calls")
    if tool_calls < 0 or tool_calls > tool_call_budget:
        raise ValueError("trusted measurements exceed tool-call budget")
    if final_tick < initial_tick:
        raise ValueError("trusted measurements have an inconsistent tick range")
    game_tick_delta = final_tick - initial_tick
    if game_tick_delta > tick_budget:
        raise ValueError("trusted measurements exceed tick budget")
    return {"tool_calls": tool_calls, "initial_tick": initial_tick, "final_tick": final_tick, "game_tick_delta": game_tick_delta}


def start_isolated_process(command: Sequence[str], **kwargs: Any) -> subprocess.Popen[bytes]:
    """Start a child in its own session so its whole process tree is addressable."""
    return subprocess.Popen(list(command), start_new_session=True, **kwargs)


def terminate_process_tree(process: subprocess.Popen[bytes] | None, *, grace_seconds: float = 20) -> None:
    """Terminate a session leader and every child before evaluator credentials exist."""
    if process is None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    if process.poll() is None:
        try:
            process.wait(timeout=grace_seconds)
            return
        except subprocess.TimeoutExpired:
            pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if process.poll() is None:
        process.wait(timeout=grace_seconds)


def run_agent_attempt(
    command: Sequence[str], environment: Mapping[str, str], *, timeout_seconds: float,
    stdout: Any = None, stderr: Any = None, starter: Callable[..., Any] = start_isolated_process,
    terminator: Callable[[Any], None] = terminate_process_tree, clock: Callable[[], float] = time.monotonic,
) -> tuple[str, dict[str, Any]]:
    """Execute one agent attempt and always reap its complete process session."""
    started = clock()
    process = starter(command, env=dict(environment), stdout=stdout, stderr=stderr)
    try:
        returncode = process.wait(timeout=timeout_seconds)
        elapsed = clock() - started
        return ("completed_pending_budget" if returncode == 0 else "agent_nonzero_exit",
                {"kind": "exited", "returncode": returncode, "wall_clock_seconds": elapsed})
    except subprocess.TimeoutExpired:
        return "agent_timeout", {"kind": "timeout", "wall_clock_seconds": clock() - started}
    finally:
        terminator(process)


def wait_for_readiness(probes: Mapping[str, Callable[[], bool]], *, timeout_seconds: float, interval_seconds: float = 1.0) -> None:
    """Require all bounded readiness gates before the agent clock starts."""
    deadline = time.monotonic() + timeout_seconds
    pending = set(probes)
    while pending:
        for name in tuple(pending):
            if probes[name]():
                pending.remove(name)
        if not pending:
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(f"readiness timed out: {', '.join(sorted(pending))}")
        time.sleep(interval_seconds)


def index_retained_artifacts(run_dir: Path, names: Sequence[str]) -> dict[str, dict[str, int | str]]:
    """Digest every retained non-secret regular-file artifact for the manifest."""
    indexed: dict[str, dict[str, int | str]] = {}
    root = run_dir.resolve()
    for name in names:
        if any(marker in name.lower() for marker in _SECRET_ARTIFACT_MARKERS):
            continue
        path = (root / name).resolve()
        if root not in path.parents or not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        indexed[name] = {"sha256": digest, "bytes": path.stat().st_size}
    return indexed


def _unscored_result(terminal_status: str) -> dict[str, Any]:
    return {"score": 0.0, "termination_reason": terminal_status, "eligible": False}


def build_run_manifest(*, scenario_id: str, model_id: str, agent_command: Sequence[str], prompt_sha256: str,
                       control_metadata: Mapping[str, Any], terminal_status: str, agent_exit: Mapping[str, Any],
                       artifacts: Mapping[str, Any], trusted_measurements: Mapping[str, Any] | None,
                       evaluator_projection: str | None, score: Mapping[str, Any] | None) -> dict[str, Any]:
    """Build a complete result whose success is impossible unless eligible."""
    eligible = terminal_status == "completed_eligible" and trusted_measurements is not None and score is not None
    return {
        "scenario": scenario_id, "model_id": model_id, "agent_command": list(agent_command),
        "prompt_sha256": prompt_sha256, "control": dict(control_metadata), "terminal_status": terminal_status,
        "eligible_for_scoring": eligible, "agent_exit": dict(agent_exit), "artifacts": dict(artifacts),
        "trusted_measurements": None if trusted_measurements is None else dict(trusted_measurements),
        "evaluator_projection": evaluator_projection,
        "score": dict(score) if eligible else _unscored_result(terminal_status),
    }


def parse_runner_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse runner options; the agent command is a JSON argv array, never REMAINDER."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--factorio", type=Path, required=True)
    parser.add_argument("--control-python", type=Path, required=True)
    parser.add_argument("--mod-archive", type=Path, required=True)
    parser.add_argument("--client-template", type=Path, required=True)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--agent-command", required=True, help="JSON argv array, for example '[\"agent\", \"--flag\"]'")
    parser.add_argument("--run-name", default=f"smelt-one-iron-plate-agent-{int(time.time())}")
    args = parser.parse_args(arguments)
    try:
        command = json.loads(args.agent_command)
    except json.JSONDecodeError as error:
        parser.error(f"--agent-command must be a JSON argv array: {error.msg}")
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        parser.error("--agent-command must be a JSON argv array of strings")
    args.agent_command = tuple(command)
    return args
