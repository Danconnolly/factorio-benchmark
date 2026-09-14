#!/usr/bin/env python3
"""Run an external agent through the constrained FastMCP broker.

This runner intentionally fails closed.  It only scores a zero-exit attempt
whose broker-generated measurements are valid; no agent-written trace exists.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from factorio_benchmark.agent_runner import (  # noqa: E402
    AgentRunConfiguration, build_agent_environment, build_agent_mcp_config,
    build_graphical_client_environment,
    build_run_manifest, index_retained_artifacts, parse_runner_arguments,
    run_agent_attempt, start_isolated_process, terminate_process_tree, validate_agent_configuration,
    validate_trusted_measurements, wait_for_readiness,
)
from factorio_benchmark.evaluator import evaluate_final_state  # noqa: E402
from factorio_benchmark.run_artifacts import sha256_file, validate_pinned_archive  # noqa: E402

SCENARIO = ROOT / "scenarios" / "smelt-one-iron-plate.v1.json"
BASELINE = ROOT / "fixtures" / "smelt-one-iron-plate-baseline.zip"
BROKER = ROOT / "scripts" / "factorio_constrained_broker.py"
CONTROL_PORT, EVALUATOR_PORT, BROKER_PORT = 27015, 27016, 38123

EXPORT = r'''import json, os, pathlib
from factorio_rcon import RCONClient
run=pathlib.Path(os.environ['BENCHMARK_RUN_DIR'])
command="/silent-command local p=game.get_player('otaci'); rcon.print(helpers.table_to_json({scenario_id='smelt-one-iron-plate',factorio_version='2.1.17',dedicated_player={name=p.name,inventory=p.get_main_inventory().get_contents()}}))"
projection=json.loads(RCONClient('127.0.0.1', int(os.environ['FACTORIO_EVALUATOR_RCON_PORT']), os.environ['FACTORIO_EVALUATOR_RCON_PASSWORD']).send_command(command))
(run/'evaluator-only-final-state.v1.json').write_text(json.dumps(projection, sort_keys=True)+'\n')'''


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def stop(process: subprocess.Popen[bytes] | None) -> None:
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=20)


def socket_ready(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=.2):
            return True
    except OSError:
        return False


def main() -> None:
    args = parse_runner_arguments()
    configuration = AgentRunConfiguration(args.model_id, args.agent_command)
    try:
        validate_agent_configuration(configuration)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    # This checks the supplied (not this development) interpreter before any
    # Factorio process or credential is created.
    supported = subprocess.run([str(args.control_python), str(BROKER), "--check-runtime"], capture_output=True, text=True)
    if supported.returncode:
        raise SystemExit(f"constrained broker unsupported: {supported.stdout}{supported.stderr}".strip())

    scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))
    run = args.runs_dir / args.run_name
    if run.exists():
        raise SystemExit("run directory already exists")
    run.mkdir(parents=True)
    status, agent_exit = "provisioning_failed", {"kind": "not_started"}
    measurements = score = None
    projection_name = None
    final_digest = None
    server = client = broker = agent = evaluator = None
    prompt_sha = ""
    failure: Exception | None = None
    try:
        baseline_hash = validate_pinned_archive(BASELINE, scenario["world"]["starting_save_sha256"], "baseline")
        mod_hash = validate_pinned_archive(args.mod_archive, scenario["world"]["enabled_mods"][0]["sha256"], "control mod archive")
        shutil.copy2(BASELINE, run / "final-save.zip")
        shutil.copytree(args.client_template, run / "client", ignore=shutil.ignore_patterns(".lock", "temp", "saves"))
        for directory in (run / "client" / "mods", run / "server-mods"):
            directory.mkdir(parents=True, exist_ok=True)
            shutil.copy2(args.mod_archive, directory / args.mod_archive.name)
            (directory / "mod-list.json").write_text(json.dumps({"mods": [{"name": "base", "enabled": True}, {"name": "factorio-player-mcp", "enabled": True}]}) + "\n")
        settings = {"name": "Local player-control benchmark", "description": "isolated benchmark", "tags": ["benchmark"], "max_players": 1, "visibility": {"public": False, "lan": False}, "username": "", "password": "", "token": "", "game_password": "", "require_user_verification": False, "allow_commands": "false", "autosave_interval": 0, "autosave_slots": 1, "afk_autokick_interval": 0, "auto_pause": False, "auto_pause_when_players_connect": False, "only_admins_can_pause_the_game": True, "autosave_only_on_server": True, "non_blocking_saving": False}
        write_json(run / "server-settings.json", settings)
        (run / "server-adminlist.json").write_text('["otaci"]\n')
        factorio_root = args.factorio.parents[2]
        (run / "client-config.ini").write_text(f"[path]\nread-data={factorio_root / 'data'}\nwrite-data={run / 'client'}\n[general]\nlocale=auto\n[other]\ncheck-updates=false\n")
        control_password = secrets.token_urlsafe(32)  # never written to an artifact
        server = subprocess.Popen([str(args.factorio), "--mod-directory", str(run / "server-mods"), "--start-server", str(run / "final-save.zip"), "--server-settings", str(run / "server-settings.json"), "--server-adminlist", str(run / "server-adminlist.json"), "--port", "34197", "--rcon-bind", f"127.0.0.1:{CONTROL_PORT}", "--rcon-password", control_password, "--console-log", str(run / "server.log")])
        broker_env = os.environ.copy() | {"FACTORIO_RCON_HOST": "127.0.0.1", "FACTORIO_RCON_PORT": str(CONTROL_PORT), "FACTORIO_RCON_PASSWORD": control_password}
        broker = start_isolated_process([str(args.control_python), str(BROKER), "--port", str(BROKER_PORT), "--measurements", str(run / "broker-measurements.json"), "--transcript", str(run / "broker-transcript.jsonl")], env=broker_env, stdout=(run / "broker.stdout.log").open("w"), stderr=(run / "broker.stderr.log").open("w"))
        client = subprocess.Popen([str(args.factorio), "--config", str(run / "client-config.ini"), "--mod-directory", str(run / "client" / "mods"), "--mp-connect", "127.0.0.1:34197", "--disable-audio", "--force-graphics-preset", "very-low", "--video-memory-usage", "low", "--max-texture-size", "2048", "--window-size", "640x480"], env=build_graphical_client_environment(os.environ))
        # Gates finish before the measured agent interval.  The server/player
        # checks are broker observations, and the socket check proves the real
        # FastMCP Streamable HTTP listener is accepting connections.
        def observed() -> bool:
            probe = subprocess.run([str(args.control_python), "-c", "from factorio_player_mcp.rcon import FactorioRconSender; from factorio_player_mcp.service import ActorService; import os; assert ActorService(FactorioRconSender(host='127.0.0.1',port=int(os.environ['FACTORIO_RCON_PORT']),password=os.environ['FACTORIO_RCON_PASSWORD'])).observe_actor().get('status') == 'completed'"], env=broker_env)
            return probe.returncode == 0
        wait_for_readiness({"server": observed, "broker": lambda: socket_ready(BROKER_PORT), "dedicated_player": observed}, timeout_seconds=120, interval_seconds=1)
        config = build_agent_mcp_config(f"http://127.0.0.1:{BROKER_PORT}/mcp")
        write_json(run / "agent-mcp.json", config)
        prompt = "Use only the supplied constrained Factorio MCP connection to attempt the scenario. Do not write accounting files; the benchmark broker records calls and ticks.\n"
        (run / "agent-prompt.txt").write_text(prompt, encoding="utf-8")
        prompt_sha = hashlib.sha256(prompt.encode()).hexdigest()
        agent_env = build_agent_environment(base_environment=os.environ, prompt_path=str(run / "agent-prompt.txt"), mcp_config_path=str(run / "agent-mcp.json"))
        with (run / "agent.stdout.log").open("w") as stdout, (run / "agent.stderr.log").open("w") as stderr:
            # The helper establishes a new session and terminates its entire
            # tree in its finally block before this function can evaluate.
            status, agent_exit = run_agent_attempt(configuration.agent_command, agent_env, timeout_seconds=scenario["budgets"]["wall_clock_seconds"], stdout=stdout, stderr=stderr)
        measurement_path = run / "broker-measurements.json"
        if status == "completed_pending_budget":
            try:
                measurements = validate_trusted_measurements(json.loads(measurement_path.read_text()), tool_call_budget=scenario["budgets"]["tool_calls"], tick_budget=scenario["budgets"]["game_ticks"])
                measurements["wall_clock_seconds"] = agent_exit["wall_clock_seconds"]
                if measurements["wall_clock_seconds"] > scenario["budgets"]["wall_clock_seconds"]:
                    raise ValueError("runner wall-clock budget exceeded")
                status = "completed_eligible"
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
                status = "agent_budget_ineligible"
                (run / "measurement-error.txt").write_text(str(error) + "\n")
        stop(broker); broker = None
        stop(client); client = None
        stop(server); server = None
        final_digest = sha256_file(run / "final-save.zip")
        if status == "completed_eligible":
            shutil.copy2(run / "final-save.zip", run / "final-save-after-control.zip")
            shutil.copy2(run / "final-save.zip", run / "evaluator-input.zip")
            evaluator_password = secrets.token_urlsafe(32)  # process env only
            evaluator = subprocess.Popen([str(args.factorio), "--mod-directory", str(run / "server-mods"), "--start-server", str(run / "evaluator-input.zip"), "--server-settings", str(run / "server-settings.json"), "--server-adminlist", str(run / "server-adminlist.json"), "--port", "34198", "--rcon-bind", f"127.0.0.1:{EVALUATOR_PORT}", "--rcon-password", evaluator_password, "--console-log", str(run / "evaluator-server.log")])
            export_env = os.environ.copy() | {"BENCHMARK_RUN_DIR": str(run), "FACTORIO_EVALUATOR_RCON_PORT": str(EVALUATOR_PORT), "FACTORIO_EVALUATOR_RCON_PASSWORD": evaluator_password}
            wait_for_readiness({"evaluator": lambda: subprocess.run([str(args.control_python), "-c", EXPORT], env=export_env).returncode == 0}, timeout_seconds=60, interval_seconds=1)
            projection_name = "evaluator-only-final-state.v1.json"
            score = evaluate_final_state(SCENARIO, run / projection_name)
    except Exception as error:
        failure = error
        status = "runner_failed" if status == "provisioning_failed" else f"{status}_runner_failed"
        (run / "runner-error.txt").write_text(str(error) + "\n", encoding="utf-8")
    finally:
        terminate_process_tree(agent)
        stop(broker); stop(client); stop(server); stop(evaluator)
        artifacts = index_retained_artifacts(run, [path.relative_to(run).as_posix() for path in run.rglob("*") if path.is_file()])
        manifest = build_run_manifest(scenario_id=scenario.get("scenario_id", "smelt-one-iron-plate"), model_id=args.model_id, agent_command=args.agent_command, prompt_sha256=prompt_sha, control_metadata={"protocol": "FastMCP Streamable HTTP", "broker": "factorio_constrained_broker", "agent_has_rcon_credentials": False, "evaluator_access": False}, terminal_status=status, agent_exit=agent_exit, artifacts=artifacts, trusted_measurements=measurements, evaluator_projection=projection_name, score=score)
        manifest["baseline_sha256"] = locals().get("baseline_hash")
        manifest["control_mod_sha256"] = locals().get("mod_hash")
        manifest["final_save_sha256"] = final_digest
        write_json(run / "run-manifest.json", manifest)
        print(json.dumps(manifest, sort_keys=True))
    if failure:
        raise SystemExit(str(failure))


if __name__ == "__main__":
    main()
