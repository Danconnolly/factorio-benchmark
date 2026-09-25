from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from factorio_benchmark.scenario import load_scenario, validate_scenario


ROOT = Path(__file__).parents[1]
SCENARIO = ROOT / "scenarios" / "smelt-one-iron-plate.v3.json"


class ScenarioSchemaTests(unittest.TestCase):
    def read_scenario(self) -> dict[str, object]:
        return json.loads(SCENARIO.read_text(encoding="utf-8"))

    def test_loads_the_versioned_declarative_contract(self) -> None:
        scenario = load_scenario(SCENARIO)

        self.assertEqual(scenario["scenario_version"], "3.0.0")
        self.assertEqual(scenario["goal"]["kind"], "player_inventory_item_count")
        self.assertEqual(scenario["evaluator"]["projection"]["kind"], "dedicated_player_inventory")
        self.assertIn("broker records calls and ticks", scenario["agent_task"])

    def test_rejects_unsupported_schema_version_before_runtime(self) -> None:
        scenario = self.read_scenario()
        scenario["scenario_version"] = "4.0.0"

        with self.assertRaisesRegex(ValueError, "scenario_version.*supported version"):
            validate_scenario(scenario)

    def test_rejects_unknown_executable_and_command_fields(self) -> None:
        for field in ("python", "shell_command", "lua", "evaluator_command"):
            with self.subTest(field=field):
                scenario = self.read_scenario()
                scenario[field] = "print('not executable')"
                with self.assertRaisesRegex(ValueError, f"unsupported field.*{field}"):
                    validate_scenario(scenario)

    def test_rejects_unsupported_goal_and_projection_vocabulary(self) -> None:
        scenario = self.read_scenario()
        scenario["goal"]["kind"] = "arbitrary_python"
        with self.assertRaisesRegex(ValueError, "goal.kind"):
            validate_scenario(scenario)

        scenario = self.read_scenario()
        scenario["evaluator"]["projection"]["kind"] = "shell"
        with self.assertRaisesRegex(ValueError, "projection.kind"):
            validate_scenario(scenario)

    def test_rejects_invalid_digest_and_unsafe_artifact_path(self) -> None:
        scenario = self.read_scenario()
        scenario["world"]["starting_save_sha256"] = "not-a-digest"
        with self.assertRaisesRegex(ValueError, "starting_save_sha256"):
            validate_scenario(scenario)

        scenario = self.read_scenario()
        scenario["world"]["starting_save"] = "../outside.zip"
        with self.assertRaisesRegex(ValueError, "relative artifact path"):
            validate_scenario(scenario)

    def test_rejects_additional_or_non_control_mods(self) -> None:
        scenario = self.read_scenario()
        scenario["world"]["enabled_mods"].append(dict(scenario["world"]["enabled_mods"][0]))
        with self.assertRaisesRegex(ValueError, "exactly the supported"):
            validate_scenario(scenario)
        scenario = self.read_scenario()
        scenario["world"]["enabled_mods"][0]["name"] = "other-mod"
        with self.assertRaisesRegex(ValueError, "factorio-player-mcp"):
            validate_scenario(scenario)

    def test_load_reports_invalid_json_with_the_file_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.json"
            path.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not valid JSON"):
                load_scenario(path)
