from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from factorio_benchmark.evaluator import evaluate_final_state


ROOT = Path(__file__).parents[1]
SCENARIO = ROOT / "scenarios" / "smelt-one-iron-plate.v1.json"


class FinalStateEvaluatorTests(unittest.TestCase):
    def evaluate(self, state: dict[str, object]) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as directory:
            final_state = Path(directory) / "final-state.json"
            final_state.write_text(json.dumps(state), encoding="utf-8")
            return evaluate_final_state(SCENARIO, final_state)

    def test_scores_success_from_the_final_evaluator_state(self) -> None:
        result = self.evaluate(
            {
                "scenario_id": "smelt-one-iron-plate",
                "factorio_version": "2.1.17",
                "dedicated_player": {"name": "benchmark-player", "inventory": [{"name": "iron-plate", "count": 1}]},
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
                "dedicated_player": {"name": "benchmark-player", "inventory": [{"name": "iron-ore", "count": 1}]},
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
                    "dedicated_player": {"name": "benchmark-player", "inventory": []},
                }
            )


if __name__ == "__main__":
    unittest.main()
