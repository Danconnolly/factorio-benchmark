#!/usr/bin/env python3
"""Provision and score one isolated legal smelting baseline attempt."""
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
SCENARIO = ROOT / "scenarios" / "smelt-one-iron-plate.v1.json"
BASELINE = ROOT / "fixtures" / "smelt-one-iron-plate-baseline.zip"

POLICY = r'''
import json, os, pathlib
from factorio_player_mcp.rcon import FactorioRconSender
from factorio_player_mcp.service import ActorService
run=pathlib.Path(os.environ['BENCHMARK_RUN_DIR'])
s=ActorService(FactorioRconSender(host='127.0.0.1', port=int(os.environ['FACTORIO_RCON_PORT']), password=os.environ['FACTORIO_RCON_PASSWORD']))
initial=s.observe_actor(); assert initial.get('status') == 'completed'
local=s.observe_local(radius=10)
placed=s.place(item='stone-furnace', x=2, y=0, direction='north')
ore=s.interact_inventory(x=2, y=0, item='iron-ore', count=1, operation='deposit', slot='input')
coal=s.interact_inventory(x=2, y=0, item='coal', count=1, operation='deposit', slot='fuel')
waited=s.wait(ticks=600)
plate=s.interact_inventory(x=2, y=0, item='iron-plate', count=1, operation='withdraw', slot='output')
final=s.observe_actor()
steps={'observe_actor_initial':initial,'observe_local':local,'place_furnace':placed,'deposit_ore':ore,'deposit_coal':coal,'wait':waited,'withdraw_plate':plate,'observe_actor_final':final}
assert all(value.get('status') == 'completed' for value in steps.values())
assert plate.get('transferred_count') == 1
assert any(item.get('name') == 'iron-plate' and item.get('count', 0) >= 1 for item in final.get('inventory', []))
trace={'tool_calls':len(steps),'initial_tick':initial['tick'],'final_tick':final['tick'],'game_tick_delta':final['tick']-initial['tick'],'steps':steps}
(run/'legal-run-trace.json').write_text(json.dumps(trace, sort_keys=True)+'\n')
'''

EXPORT = r'''
import json, os, pathlib
from factorio_rcon import RCONClient
run=pathlib.Path(os.environ['BENCHMARK_RUN_DIR'])
password=(run/'evaluator-rcon-password').read_text()
command="/silent-command local p=game.get_player('otaci'); rcon.print(helpers.table_to_json({scenario_id='smelt-one-iron-plate',factorio_version='2.1.17',dedicated_player={name=p.name,inventory=p.get_main_inventory().get_contents()}}))"
projection=json.loads(RCONClient('127.0.0.1', int(os.environ['FACTORIO_EVALUATOR_RCON_PORT']), password).send_command(command))
(run/'evaluator-only-final-state.v1.json').write_text(json.dumps(projection, sort_keys=True)+'\n')
'''


def sha256(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def stop(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=20)


def run_child(command: list[str], env: dict[str, str], timeout: int = 180) -> None:
    completed = subprocess.run(command, env=env, capture_output=True, text=True, timeout=timeout)
    if completed.returncode:
        raise RuntimeError(f"child failed: {completed.stderr.strip()}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--factorio', type=Path, required=True)
    parser.add_argument('--control-python', type=Path, required=True)
    parser.add_argument('--mod-archive', type=Path, required=True)
    parser.add_argument('--client-template', type=Path, required=True)
    parser.add_argument('--runs-dir', type=Path, required=True)
    parser.add_argument('--run-name', default=f"smelt-one-iron-plate-{int(time.time())}")
    args = parser.parse_args()
    scenario = json.loads(SCENARIO.read_text())
    run = args.runs_dir / args.run_name
    if run.exists():
        raise SystemExit(f"run directory already exists: {run}")
    run.mkdir(parents=True)
    baseline_hash = sha256(BASELINE)
    if baseline_hash != scenario['world']['starting_save_sha256']:
        raise SystemExit('baseline hash does not match scenario')
    shutil.copy2(BASELINE, run / 'final-save.zip')
    shutil.copytree(args.client_template, run / 'client', ignore=shutil.ignore_patterns('.lock', 'temp', 'saves'))
    client_mods = run / 'client' / 'mods'; client_mods.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.mod_archive, client_mods / args.mod_archive.name)
    (client_mods / 'mod-list.json').write_text(json.dumps({'mods':[{'name':'base','enabled':True},{'name':'factorio-player-mcp','enabled':True}]})+'\n')
    (run / 'server-settings.json').write_text(json.dumps({'name':'Local player-control benchmark','description':'isolated benchmark','tags':['benchmark'],'max_players':1,'visibility':{'public':False,'lan':False},'username':'','password':'','token':'','game_password':'','require_user_verification':False,'allow_commands':'false','autosave_interval':0,'autosave_slots':1,'afk_autokick_interval':0,'auto_pause':False,'auto_pause_when_players_connect':False,'only_admins_can_pause_the_game':True,'autosave_only_on_server':True,'non_blocking_saving':False})+'\n')
    (run / 'server-adminlist.json').write_text('["otaci"]\n')
    factorio_root = args.factorio.parents[2]
    (run / 'client-config.ini').write_text(f'[path]\nread-data={factorio_root / "data"}\nwrite-data={run / "client"}\n[general]\nlocale=auto\n[other]\ncheck-updates=false\n')
    server_password = secrets.token_urlsafe(32); (run / 'rcon-password').write_text(server_password); os.chmod(run / 'rcon-password', 0o600)
    env = os.environ.copy(); env['BENCHMARK_RUN_DIR'] = str(run); env['FACTORIO_RCON_PORT'] = '27015'; env['FACTORIO_RCON_PASSWORD'] = server_password
    server = client = evaluator = None
    try:
        shutil.copy2(args.mod_archive, factorio_root / 'mods' / args.mod_archive.name)
        server = subprocess.Popen([str(args.factorio),'--start-server',str(run/'final-save.zip'),'--server-settings',str(run/'server-settings.json'),'--server-adminlist',str(run/'server-adminlist.json'),'--port','34197','--rcon-bind','127.0.0.1:27015','--rcon-password',server_password,'--console-log',str(run/'server.log')])
        client_env = env | {
            'XDG_RUNTIME_DIR': os.environ.get('XDG_RUNTIME_DIR', '/run/user/1000'),
            'WAYLAND_DISPLAY': os.environ.get('WAYLAND_DISPLAY', 'wayland-0'),
            'SDL_VIDEODRIVER': 'wayland',
        }
        client = subprocess.Popen([str(args.factorio),'--config',str(run/'client-config.ini'),'--mp-connect','127.0.0.1:34197','--disable-audio','--force-graphics-preset','very-low','--video-memory-usage','low','--max-texture-size','2048','--window-size','640x480'], env=client_env)
        deadline=time.monotonic()+120
        while True:
            try:
                run_child([str(args.control_python),'-c',POLICY], env)
                break
            except RuntimeError:
                if time.monotonic() >= deadline: raise
                time.sleep(2)
        stop(client); client=None; stop(server); server=None
        shutil.copy2(run/'final-save.zip', run/'final-save-after-control.zip'); shutil.copy2(run/'final-save.zip', run/'evaluator-input.zip')
        evaluator_password=secrets.token_urlsafe(32); (run/'evaluator-rcon-password').write_text(evaluator_password); os.chmod(run/'evaluator-rcon-password',0o600)
        evaluator=subprocess.Popen([str(args.factorio),'--start-server',str(run/'evaluator-input.zip'),'--server-settings',str(run/'server-settings.json'),'--server-adminlist',str(run/'server-adminlist.json'),'--port','34198','--rcon-bind','127.0.0.1:27016','--rcon-password',evaluator_password,'--console-log',str(run/'evaluator-server.log')])
        export_env=env | {'FACTORIO_EVALUATOR_RCON_PORT':'27016'}
        deadline=time.monotonic()+60
        while True:
            try:
                run_child([str(args.control_python),'-c',EXPORT], export_env); break
            except RuntimeError:
                if time.monotonic() >= deadline: raise
                time.sleep(1)
        from factorio_benchmark.evaluator import evaluate_final_state
        from factorio_benchmark.run_artifacts import validate_legal_trace
        trace=json.loads((run/'legal-run-trace.json').read_text())
        budgets=validate_legal_trace(trace, tool_call_budget=scenario['budgets']['tool_calls'], tick_budget=scenario['budgets']['game_ticks'])
        result=evaluate_final_state(SCENARIO,run/'evaluator-only-final-state.v1.json')
        (run/'offline-evaluator-result.json').write_text(json.dumps(result,sort_keys=True)+'\n')
        manifest={'scenario':scenario['scenario_id'],'baseline_sha256':baseline_hash,'final_save_sha256':sha256(run/'final-save.zip'),'budgets':budgets,'score':result}
        (run/'run-manifest.json').write_text(json.dumps(manifest,sort_keys=True)+'\n')
        print(json.dumps(manifest,sort_keys=True))
    finally:
        stop(client); stop(server); stop(evaluator)
        for name in ('rcon-password','evaluator-rcon-password'):
            (run/name).unlink(missing_ok=True)

if __name__ == '__main__':
    main()
