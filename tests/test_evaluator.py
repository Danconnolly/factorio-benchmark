from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from factorio_benchmark.evaluator import evaluate_final_state
from factorio_benchmark.run_artifacts import validate_legal_trace


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
        self.assertEqual(control_mod["version"], "0.1.16")
        self.assertEqual(control_mod["sha256"], "5af055cb47b063bfc99426e7756196d321661db030fea18bbde608a496c96338")

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
                "steps": {
                    "observe_actor_final": {
                        "inventory": [{"name": "iron-plate", "count": 1}],
                    }
                },
            },
            tool_call_budget=40,
            tick_budget=3600,
        )

        self.assertEqual(result, {"tool_calls": 8, "game_tick_delta": 614})

    def test_rejects_trace_that_exceeds_the_tick_budget(self) -> None:
        with self.assertRaisesRegex(ValueError, "tick budget"):
            validate_legal_trace(
                {"tool_calls": 1, "initial_tick": 1, "final_tick": 3602, "game_tick_delta": 3601, "steps": {}},
                tool_call_budget=40,
                tick_budget=3600,
            )


if __name__ == "__main__":
    unittest.main()
