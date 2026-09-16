from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from factorio_benchmark.evaluator import evaluate_final_state
from factorio_benchmark.run_artifacts import validate_legal_trace, validate_pinned_archive


ROOT = Path(__file__).parents[1]
SCENARIO = ROOT / "scenarios" / "smelt-one-iron-plate.v1.json"


class FinalStateEvaluatorTests(unittest.TestCase):
    def evaluate(self, state: dict[str, object]) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as directory:
            final_state = Path(directory) / "final-state.json"
            final_state.write_text(json.dumps(state), encoding="utf-8")
            return evaluate_final_state(SCENARIO, final_state)

    def test_scenario_pins_the_vm_runner_identity(self) -> None:
        scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))

        self.assertEqual(scenario["control"]["dedicated_player_name"], "otaci")

    def test_scenario_pins_the_verified_control_archive(self) -> None:
        scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))

        control_mod = scenario["world"]["enabled_mods"][0]
        self.assertEqual(control_mod["name"], "factorio-player-mcp")
        self.assertEqual(control_mod["version"], "0.1.17")
        self.assertEqual(control_mod["sha256"], "69bea415dc435e83312cbb8c9f11adfebeaec16fdf05591699b5191abff399a1")

    def test_scores_success_from_the_final_evaluator_state(self) -> None:
        result = self.evaluate(
            {
                "scenario_id": "smelt-one-iron-plate",
                "factorio_version": "2.1.17",
                "dedicated_player": {"name": "otaci", "inventory": [{"name": "iron-plate", "count": 1}]},
            }
        )

        self.assertEqual(result["termination_reason"], "success")
        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["predicate"], {"item": "iron-plate", "required_count": 1, "actual_count": 1})

    def test_scores_failure_without_the_required_final_item(self) -> None:
        result = self.evaluate(
            {
                "scenario_id": "smelt-one-iron-plate",
                "factorio_version": "2.1.17",
                "dedicated_player": {"name": "otaci", "inventory": [{"name": "iron-ore", "count": 1}]},
            }
        )

        self.assertEqual(result["termination_reason"], "goal_not_met")
        self.assertEqual(result["score"], 0.0)

    def test_rejects_a_state_for_a_different_scenario(self) -> None:
        with self.assertRaisesRegex(ValueError, "scenario_id"):
            self.evaluate(
                {
                    "scenario_id": "other",
                    "factorio_version": "2.1.17",
                    "dedicated_player": {"name": "otaci", "inventory": []},
                }
            )

    def test_validates_trace_against_declared_call_and_tick_budgets(self) -> None:
        result = validate_legal_trace(
            {
                "tool_calls": 8,
                "initial_tick": 100,
                "final_tick": 714,
                "game_tick_delta": 614,
                "wall_clock_seconds": 4.5,
                "steps": {
                    "observe_actor_final": {
                        "inventory": [{"name": "iron-plate", "count": 1}],
                    }
                },
            },
            tool_call_budget=40,
            tick_budget=3600,
            wall_clock_budget=300,
        )

        self.assertEqual(result, {"tool_calls": 8, "game_tick_delta": 614, "wall_clock_seconds": 4.5})

    def test_rejects_trace_that_exceeds_the_tick_budget(self) -> None:
        with self.assertRaisesRegex(ValueError, "tick budget"):
            validate_legal_trace(
                {"tool_calls": 1, "initial_tick": 1, "final_tick": 3602, "game_tick_delta": 3601, "wall_clock_seconds": 1, "steps": {}},
                tool_call_budget=40,
                tick_budget=3600,
                wall_clock_budget=300,
            )

    def test_rejects_trace_that_exceeds_the_wall_clock_budget(self) -> None:
        with self.assertRaisesRegex(ValueError, "wall-clock budget"):
            validate_legal_trace(
                {"tool_calls": 1, "initial_tick": 1, "final_tick": 2, "game_tick_delta": 1, "wall_clock_seconds": 301, "steps": {}},
                tool_call_budget=40,
                tick_budget=3600,
                wall_clock_budget=300,
            )

    def test_rejects_an_archive_with_a_different_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "control-mod.zip"
            archive.write_bytes(b"unexpected archive")

            with self.assertRaisesRegex(ValueError, "control mod archive hash"):
                validate_pinned_archive(archive, "0" * 64, "control mod archive")

    def test_rejects_a_scenario_without_evaluator_metadata(self) -> None:
        scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))
        del scenario["evaluator"]
        with tempfile.TemporaryDirectory() as directory:
            scenario_path = Path(directory) / "scenario.json"
            final_state = Path(directory) / "final-state.json"
            scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
            final_state.write_text(json.dumps({"scenario_id": "smelt-one-iron-plate", "factorio_version": "2.1.17", "dedicated_player": {"name": "otaci", "inventory": []}}), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "scenario evaluator"):
                evaluate_final_state(scenario_path, final_state)


if __name__ == "__main__":
    unittest.main()
