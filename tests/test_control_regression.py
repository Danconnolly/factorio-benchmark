"""Tests for the reusable full-surface player-control regression plan."""

from __future__ import annotations

import ast
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
    def test_runner_does_not_retry_a_mutating_policy_after_partial_failure(self) -> None:
        tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        policy_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "run_policy"
        ]

        self.assertEqual(len(policy_calls), 1)
        current = policy_calls[0]
        while not isinstance(current, ast.Module):
            current = parents[current]
            self.assertNotIsInstance(current, ast.While)

    def test_policy_accepts_a_native_craft_that_completes_before_queue_observation(self) -> None:
        policy = build_policy()

        self.assertIn('assert crafted.get("queued_count") in (0, 1), crafted', policy)

    def test_runner_selects_the_factorio_2_0_control_fixture(self) -> None:
        runner_source = RUNNER.read_text(encoding="utf-8")

        self.assertIn('player-control-test-baseline.v2.zip', runner_source)
        self.assertIn('player-control-test-baseline.v2.json', runner_source)

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
