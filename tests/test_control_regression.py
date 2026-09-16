"""Tests for the reusable full-surface player-control regression plan."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from factorio_benchmark.control_regression import CONTROL_REGRESSION_STEPS, build_policy


REPOSITORY_ROOT = Path(__file__).parents[1]
RUNNER = REPOSITORY_ROOT / "scripts" / "run_player_control_regression.py"


class ControlRegressionTests(unittest.TestCase):
    def test_plan_covers_every_public_capability_and_structured_rejections(self) -> None:
        step_names = [step["name"] for step in CONTROL_REGRESSION_STEPS]
        self.assertEqual(
            step_names,
            [
                "observe_actor_initial",
                "observe_local_initial",
                "reject_unknown_recipe",
                "reject_unreachable_inventory",
                "reject_uncharted_placement",
                "craft_gear",
                "wait_for_craft",
                "place_furnace",
                "deposit_wood",
                "withdraw_wood",
                "move_northwest",
                "move_east",
                "move_to_coal",
                "mine_coal",
                "move_to_drill_location",
                "place_drill",
                "rotate_drill",
                "wait_final",
                "observe_actor_final",
                "observe_local_final",
            ],
        )
        required = {"observe_actor", "observe_local", "craft", "wait", "move", "mine", "place", "rotate", "interact_inventory"}
        self.assertTrue(required.issubset({step["operation"] for step in CONTROL_REGRESSION_STEPS}))
        self.assertEqual(
            {step["expected_reason"] for step in CONTROL_REGRESSION_STEPS if "expected_reason" in step},
            {"recipe_not_available", "inventory_target_unavailable", "placement_not_charted"},
        )

    def test_policy_records_all_steps_and_enforces_outcomes(self) -> None:
        policy = build_policy()

        self.assertIn("steps = {}", policy)
        self.assertIn("assert_result", policy)
        self.assertIn("player-control-regression-trace.json", policy)
        for step in CONTROL_REGRESSION_STEPS:
            self.assertIn(step["name"], policy)
    def test_runner_accepts_only_explicit_isolated_inputs(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(RUNNER), "--help"],
            capture_output=True,
            check=True,
            text=True,
        )

        self.assertIn("--factorio", completed.stdout)
        self.assertIn("--control-python", completed.stdout)
        self.assertIn("--mod-archive", completed.stdout)
        self.assertIn("--client-template", completed.stdout)
        self.assertIn("--runs-dir", completed.stdout)


if __name__ == "__main__":
    unittest.main()
