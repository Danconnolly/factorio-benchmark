"""Installed-wheel regression coverage for benchmark-owned runtime assets."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]


class InstalledWheelAssetTests(unittest.TestCase):
    def test_wheel_resolves_packaged_assets_and_preflights_physical_broker(self) -> None:
        """A fresh install must not depend on a sibling source checkout."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wheel_dir = root / "wheel"
            venv = root / "venv"
            subprocess.run(
                ["uv", "build", "--wheel", "--out-dir", str(wheel_dir)],
                cwd=REPOSITORY_ROOT, check=True, capture_output=True, text=True,
            )
            wheel = next(wheel_dir.glob("factorio_benchmark-*.whl"))
            subprocess.run(
                ["uv", "venv", "--python", sys.executable, str(venv)],
                check=True, capture_output=True, text=True,
            )
            python = venv / "bin" / "python"
            subprocess.run(
                ["uv", "pip", "install", "--python", str(python), str(wheel)],
                check=True, capture_output=True, text=True,
            )
            smoke = r'''
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from factorio_benchmark.assets import runtime_assets
from factorio_benchmark import smelt_session

assets = runtime_assets()
assert assets.broker.is_file(), assets.broker
assert assets.scenario.is_file(), assets.scenario
assert assets.baseline.is_file(), assets.baseline
assert "site-packages/scripts" not in str(assets.broker), assets.broker
calls = []
class Result:
    returncode = 0
    stdout = ""
    stderr = ""
def checked(command, **kwargs):
    calls.append(command)
    return Result()
async def callback(request):
    return {"answer": "unreached"}
with tempfile.TemporaryDirectory() as directory, patch(
    "factorio_benchmark.smelt_session.subprocess.run", side_effect=checked,
):
    result = smelt_session.run_smelt_callback_session(
        runtime=smelt_session.SmeltSessionRuntime(
            factorio=Path("/missing/factorio"), control_python=Path("/control/python"),
            mod_archive=Path("/missing/mod.zip"), client_template=Path("/missing/client"),
            runs_dir=Path(directory), run_name="preflight",
        ), model_id="smoke", callback=callback,
    )
assert calls[0] == ["/control/python", str(assets.broker), "--check-runtime"], calls
assert result["terminal_status"] == "runner_failed", result
print(json.dumps({"broker": str(assets.broker), "scenario": str(assets.scenario), "baseline": str(assets.baseline)}))
'''
            result = subprocess.run(
                [str(python), "-I", "-c", smoke], check=True, capture_output=True, text=True,
            )
            paths = json.loads(result.stdout)
            for path in paths.values():
                self.assertIn("site-packages/factorio_benchmark", path)
