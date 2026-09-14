from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from factorio_benchmark.agent_runner import (
    AgentRunConfiguration, build_agent_environment, build_agent_mcp_config,
    build_graphical_client_environment,
    build_run_manifest, index_retained_artifacts, parse_runner_arguments,
    start_isolated_process, terminate_process_tree, validate_agent_configuration,
    run_agent_attempt, validate_trusted_measurements, wait_for_readiness,
)


class AgentRunnerTests(unittest.TestCase):
    def test_rejects_missing_model_or_agent_command(self) -> None:
        with self.assertRaisesRegex(ValueError, "model ID"):
            validate_agent_configuration(AgentRunConfiguration(model_id="", agent_command=("agent",)))
        with self.assertRaisesRegex(ValueError, "agent command"):
            validate_agent_configuration(AgentRunConfiguration(model_id="test-model", agent_command=()))

    def test_agent_config_is_brokered_and_contains_no_control_secret(self) -> None:
        config = build_agent_mcp_config("http://127.0.0.1:38123/mcp")
        encoded = json.dumps(config).lower()
        self.assertEqual(config["mcpServers"]["factorio"]["transport"], "streamable-http")
        self.assertNotIn("command", config["mcpServers"]["factorio"])
        self.assertNotIn("rcon", encoded)
        self.assertNotIn("password", encoded)
        self.assertNotIn("evaluator", encoded)

    def test_builds_a_narrow_agent_environment(self) -> None:
        environment = build_agent_environment(
            base_environment={"PATH": "/bin", "MODEL_API_KEY": "secret", "FACTORIO_EVALUATOR_RCON_PORT": "27016", "FACTORIO_RCON_PASSWORD": "secret"},
            prompt_path="/runs/one/agent-prompt.txt", mcp_config_path="/runs/one/agent-mcp.json",
        )
        self.assertEqual(environment["PATH"], "/bin")
        self.assertNotIn("FACTORIO_EVALUATOR_RCON_PORT", environment)
        self.assertNotIn("FACTORIO_RCON_PASSWORD", environment)
        self.assertNotIn("MODEL_API_KEY", environment)

    def test_builds_graphical_client_environment_with_verified_wayland_defaults(self) -> None:
        environment = build_graphical_client_environment({"PATH": "/bin"})
        self.assertEqual(environment["XDG_RUNTIME_DIR"], "/run/user/1000")
        self.assertEqual(environment["WAYLAND_DISPLAY"], "wayland-0")
        self.assertEqual(environment["SDL_VIDEODRIVER"], "wayland")

    def test_measurements_must_be_broker_produced_and_within_budget(self) -> None:
        accepted = validate_trusted_measurements(
            {"source": "factorio-constrained-broker.v1", "tool_calls": 2, "initial_tick": 4, "final_tick": 10},
            tool_call_budget=2, tick_budget=6,
        )
        self.assertEqual(accepted["game_tick_delta"], 6)
        with self.assertRaisesRegex(ValueError, "trusted broker"):
            validate_trusted_measurements({"tool_calls": 0, "initial_tick": 0, "final_tick": 0}, tool_call_budget=2, tick_budget=6)
        with self.assertRaisesRegex(ValueError, "tool-call budget"):
            validate_trusted_measurements({"source": "factorio-constrained-broker.v1", "tool_calls": 3, "initial_tick": 0, "final_tick": 0}, tool_call_budget=2, tick_budget=6)
        with self.assertRaisesRegex(ValueError, "no broker calls"):
            validate_trusted_measurements({"source": "factorio-constrained-broker.v1", "tool_calls": 0, "initial_tick": 0, "final_tick": 0}, tool_call_budget=2, tick_budget=6)

    def test_noneligible_attempt_has_explicit_unscored_result(self) -> None:
        manifest = build_run_manifest(
            scenario_id="smelt", model_id="model", agent_command=["agent"], prompt_sha256="a" * 64,
            control_metadata={}, terminal_status="agent_timeout", agent_exit={"kind": "timeout"},
            artifacts={}, trusted_measurements=None, evaluator_projection=None, score={"score": 1.0},
        )
        self.assertFalse(manifest["eligible_for_scoring"])
        self.assertEqual(manifest["score"], {"score": 0.0, "termination_reason": "agent_timeout", "eligible": False})

    def test_indexes_all_nonsecret_retained_artifacts_with_digests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            for name in ("final-save.zip", "evaluator-input.zip", "result.json", "agent.stdout.log", "broker-transcript.jsonl"):
                (run / name).write_text(name, encoding="utf-8")
            (run / "evaluator-rcon-password").write_text("secret", encoding="utf-8")
            indexed = index_retained_artifacts(run, [path.name for path in run.iterdir()])
        self.assertEqual(set(indexed), {"final-save.zip", "evaluator-input.zip", "result.json", "agent.stdout.log", "broker-transcript.jsonl"})
        self.assertTrue(all("sha256" in item for item in indexed.values()))

    def test_runner_options_are_not_consumed_by_agent_command(self) -> None:
        args = parse_runner_arguments([
            "--factorio", "factorio", "--control-python", "python", "--mod-archive", "mod.zip",
            "--client-template", "client", "--runs-dir", "runs", "--model-id", "model",
            "--agent-command", '["agent", "--flag"]', "--run-name", "named-run",
        ])
        self.assertEqual(args.agent_command, ("agent", "--flag"))
        self.assertEqual(args.run_name, "named-run")

    def test_process_group_termination_kills_descendants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            child_pid = Path(directory) / "child.pid"
            program = (
                "import pathlib,subprocess,sys,time; "
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                f"pathlib.Path({str(child_pid)!r}).write_text(str(p.pid)); time.sleep(60)"
            )
            process = start_isolated_process([sys.executable, "-c", program])
            deadline = time.monotonic() + 3
            while not child_pid.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(child_pid.exists())
            descendant = int(child_pid.read_text())
            terminate_process_tree(process, grace_seconds=.1)
            with self.assertRaises(ProcessLookupError):
                os.kill(descendant, 0)

    def test_readiness_waits_for_every_gate_without_charging_agent_time(self) -> None:
        attempts = {"server": 0, "broker": 0, "player": 0}
        def probe(name: str):
            def inner() -> bool:
                attempts[name] += 1
                return attempts[name] >= 2
            return inner
        wait_for_readiness({name: probe(name) for name in attempts}, timeout_seconds=1, interval_seconds=.001)
        self.assertTrue(all(count >= 2 for count in attempts.values()))

    def test_agent_lifecycle_timeout_is_unscored_and_tree_is_terminated(self) -> None:
        class TimedOutProcess:
            pid = 123
            def wait(self, timeout: float) -> int:
                raise subprocess.TimeoutExpired(["agent"], timeout)
        stopped = []
        status, exit_data = run_agent_attempt(
            ("agent",), {}, timeout_seconds=.01,
            starter=lambda command, **kwargs: TimedOutProcess(),
            terminator=lambda process: stopped.append(process), clock=lambda: 10.0,
        )
        self.assertEqual(status, "agent_timeout")
        self.assertEqual(exit_data["kind"], "timeout")
        self.assertEqual(len(stopped), 1)
