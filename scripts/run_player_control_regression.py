#!/usr/bin/env python3
"""Run the full typed player-control regression against a fresh fixture copy."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from factorio_benchmark.agent_runner import build_graphical_client_environment
from factorio_benchmark.control_regression import build_policy
from factorio_benchmark.run_artifacts import sha256_file, validate_pinned_archive


FIXTURE = ROOT / "fixtures" / "player-control-test-baseline.v2.zip"
FIXTURE_METADATA = ROOT / "fixtures" / "player-control-test-baseline.v2.json"
ACTOR_NAME = "otaci"


def stop(process: subprocess.Popen[bytes] | None) -> None:
    """Stop a Factorio child without leaving its run-local save locked."""
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=20)


def run_policy(control_python: Path, environment: dict[str, str], timeout_seconds: int) -> None:
    """Execute only the checked-in typed policy using the host-only RCON secret."""
    completed = subprocess.run(
        [str(control_python), "-c", build_policy()],
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if completed.returncode:
        raise RuntimeError(f"control regression policy failed: {completed.stderr.strip()}")


def wait_for_actor_ready(control_python: Path, environment: dict[str, str], timeout_seconds: int) -> None:
    """Wait with an observation-only probe before one mutating policy attempt."""
    probe = (
        "from factorio_player_mcp.rcon import FactorioRconSender; "
        "from factorio_player_mcp.service import ActorService; import os; "
        "result=ActorService(FactorioRconSender(host='127.0.0.1',"
        "port=int(os.environ['FACTORIO_RCON_PORT']),"
        "password=os.environ['FACTORIO_RCON_PASSWORD'])).observe_actor(); "
        "assert result.get('status') == 'completed', result"
    )
    deadline = time.monotonic() + timeout_seconds
    while True:
        completed = subprocess.run(
            [str(control_python), "-c", probe], env=environment,
            capture_output=True, text=True,
        )
        if completed.returncode == 0:
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(f"control regression actor did not become ready: {completed.stderr.strip()}")
        time.sleep(2)


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    """Require explicit Factorio, control-runtime, and isolated-data locations."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factorio", type=Path, required=True)
    parser.add_argument("--control-python", type=Path, required=True)
    parser.add_argument("--mod-archive", type=Path, required=True)
    parser.add_argument("--client-template", type=Path, required=True)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--run-name", default=f"player-control-regression-{int(time.time())}")
    parser.add_argument("--game-port", type=int, default=34217)
    parser.add_argument("--rcon-port", type=int, default=27017)
    return parser.parse_args(arguments)


def main() -> None:
    args = parse_arguments()
    if not 1 <= args.game_port <= 65535 or not 1 <= args.rcon_port <= 65535:
        raise SystemExit("ports must be within 1..65535")
    if not args.factorio.is_file() or not args.control_python.is_file() or not args.mod_archive.is_file():
        raise SystemExit("factorio, control-python, and mod-archive must be files")
    if not args.client_template.is_dir():
        raise SystemExit("client-template must be a directory")

    fixture_metadata = json.loads(FIXTURE_METADATA.read_text(encoding="utf-8"))
    fixture_hash = validate_pinned_archive(FIXTURE, fixture_metadata["sha256"], "control regression fixture")
    run = args.runs_dir / args.run_name
    if run.exists():
        raise SystemExit(f"run directory already exists: {run}")
    run.mkdir(parents=True)
    control_mod_hash = sha256_file(args.mod_archive)
    server = client = None
    password_path = run / "rcon-password"
    try:
        shutil.copy2(FIXTURE, run / "final-save.zip")
        shutil.copytree(args.client_template, run / "client", ignore=shutil.ignore_patterns(".lock", "temp", "saves"))
        client_mods = run / "client" / "mods"
        server_mods = run / "server-mods"
        client_mods.mkdir(parents=True, exist_ok=True)
        server_mods.mkdir()
        for mod_directory in (client_mods, server_mods):
            shutil.copy2(args.mod_archive, mod_directory / args.mod_archive.name)
            (mod_directory / "mod-list.json").write_text(
                json.dumps({"mods": [{"name": "base", "enabled": True}, {"name": "factorio-player-mcp", "enabled": True}]}) + "\n",
                encoding="utf-8",
            )
        (run / "server-settings.json").write_text(
            json.dumps({"name": "Player-control regression", "description": "isolated typed-control acceptance", "tags": ["benchmark"], "max_players": 1, "visibility": {"public": False, "lan": False}, "username": "", "password": "", "token": "", "game_password": "", "require_user_verification": False, "allow_commands": "false", "autosave_interval": 0, "autosave_slots": 1, "afk_autokick_interval": 0, "auto_pause": False, "auto_pause_when_players_connect": False, "only_admins_can_pause_the_game": True, "autosave_only_on_server": True, "non_blocking_saving": False}) + "\n",
            encoding="utf-8",
        )
        (run / "server-adminlist.json").write_text(json.dumps([ACTOR_NAME]) + "\n", encoding="utf-8")
        factorio_root = args.factorio.parents[2]
        (run / "client-config.ini").write_text(
            f"[path]\nread-data={factorio_root / 'data'}\nwrite-data={run / 'client'}\n[general]\nlocale=auto\n[other]\ncheck-updates=false\n",
            encoding="utf-8",
        )
        password = secrets.token_urlsafe(32)
        password_path.write_text(password, encoding="utf-8")
        os.chmod(password_path, 0o600)
        environment = os.environ.copy() | {
            "BENCHMARK_RUN_DIR": str(run),
            "FACTORIO_RCON_PORT": str(args.rcon_port),
            "FACTORIO_RCON_PASSWORD": password,
        }
        server = subprocess.Popen([
            str(args.factorio), "--mod-directory", str(server_mods), "--start-server", str(run / "final-save.zip"),
            "--server-settings", str(run / "server-settings.json"), "--server-adminlist", str(run / "server-adminlist.json"),
            "--port", str(args.game_port), "--rcon-bind", f"127.0.0.1:{args.rcon_port}", "--rcon-password", password,
            "--console-log", str(run / "server.log"),
        ])
        client = subprocess.Popen([
            str(args.factorio), "--config", str(run / "client-config.ini"), "--mod-directory", str(client_mods),
            "--mp-connect", f"127.0.0.1:{args.game_port}", "--disable-audio", "--force-graphics-preset", "very-low",
            "--video-memory-usage", "low", "--max-texture-size", "2048", "--window-size", "640x480",
        ], env=build_graphical_client_environment(environment))
        wait_for_actor_ready(args.control_python, environment, timeout_seconds=180)
        started = time.monotonic()
        run_policy(args.control_python, environment, timeout_seconds=150)
        elapsed = time.monotonic() - started
        stop(client)
        client = None
        stop(server)
        server = None
        trace_path = run / "player-control-regression-trace.json"
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        trace["wall_clock_seconds"] = elapsed
        trace_path.write_text(json.dumps(trace, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {
            "fixture_id": fixture_metadata["fixture_id"],
            "fixture_sha256": fixture_hash,
            "factorio_version": fixture_metadata["factorio_version"],
            "control_mod_sha256": control_mod_hash,
            "control_mod_archive": args.mod_archive.name,
            "final_save_sha256": sha256_file(run / "final-save.zip"),
            "trace": {name: trace[name] for name in ("tool_calls", "initial_tick", "final_tick", "game_tick_delta", "wall_clock_seconds")},
            "all_public_capabilities": fixture_metadata["required_control_capabilities"],
        }
        (run / "run-manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(manifest, sort_keys=True))
    finally:
        stop(client)
        stop(server)
        password_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
