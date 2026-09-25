"""Strict, declarative scenario loading and validation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "3.0.0"
GOAL_KINDS = frozenset({"player_inventory_item_count"})
PROJECTION_KINDS = frozenset({"dedicated_player_inventory"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SCENARIO_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _fail(path: str, message: str) -> None:
    raise ValueError(f"scenario {path}: {message}")


def _object(value: object, path: str, *, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    unknown = set(value) - fields
    missing = fields - set(value)
    if missing:
        _fail(path, f"is missing required field(s): {', '.join(sorted(missing))}")
    if unknown:
        _fail(path, f"contains unsupported field(s): {', '.join(sorted(unknown))}")
    return value


def _string(value: object, path: str, *, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value:
        _fail(path, "must be a non-empty string")
    if pattern is not None and not pattern.fullmatch(value):
        _fail(path, "has an invalid format")
    return value


def _nonnegative_integer(value: object, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _fail(path, "must be a non-negative integer")
    return value


def _positive_integer(value: object, path: str) -> int:
    value = _nonnegative_integer(value, path)
    if value == 0:
        _fail(path, "must be a positive integer")
    return value


def _validate_inventory(value: object, path: str) -> None:
    if not isinstance(value, list):
        _fail(path, "must be an array")
    for index, entry in enumerate(value):
        item = _object(entry, f"{path}[{index}]", fields={"name", "count"})
        _string(item["name"], f"{path}[{index}].name")
        _nonnegative_integer(item["count"], f"{path}[{index}].count")


def validate_scenario(value: object) -> dict[str, Any]:
    """Validate the complete v3 declarative contract and return it unchanged.

    The allow-list is deliberately closed: scenario files describe data only,
    never commands, scripts, transport configuration, or evaluator code.
    """
    scenario = _object(value, "", fields={
        "scenario_version", "scenario_id", "factorio_version", "control", "world",
        "initial_state_assertions", "budgets", "agent_task", "goal", "evaluator",
    })
    if scenario["scenario_version"] != SCHEMA_VERSION:
        _fail("scenario_version", f"must be supported version {SCHEMA_VERSION}")
    _string(scenario["scenario_id"], "scenario_id", pattern=_SCENARIO_ID)
    _string(scenario["factorio_version"], "factorio_version")

    control = _object(scenario["control"], "control", fields={"repository", "protocol_version", "dedicated_player_name"})
    for name in control:
        _string(control[name], f"control.{name}")

    world = _object(scenario["world"], "world", fields={"seed", "starting_save", "starting_save_sha256", "enabled_mods"})
    _nonnegative_integer(world["seed"], "world.seed")
    starting_save = _string(world["starting_save"], "world.starting_save")
    if Path(starting_save).is_absolute() or ".." in Path(starting_save).parts:
        _fail("world.starting_save", "must be a relative artifact path")
    _string(world["starting_save_sha256"], "world.starting_save_sha256", pattern=_SHA256)
    if not isinstance(world["enabled_mods"], list) or not world["enabled_mods"]:
        _fail("world.enabled_mods", "must be a non-empty array")
    for index, mod_value in enumerate(world["enabled_mods"]):
        mod = _object(mod_value, f"world.enabled_mods[{index}]", fields={"name", "version", "sha256"})
        _string(mod["name"], f"world.enabled_mods[{index}].name")
        _string(mod["version"], f"world.enabled_mods[{index}].version")
        _string(mod["sha256"], f"world.enabled_mods[{index}].sha256", pattern=_SHA256)

    state = _object(scenario["initial_state_assertions"], "initial_state_assertions", fields={"player_inventory", "technologies"})
    _validate_inventory(state["player_inventory"], "initial_state_assertions.player_inventory")
    if not isinstance(state["technologies"], list) or not all(isinstance(item, str) and item for item in state["technologies"]):
        _fail("initial_state_assertions.technologies", "must be an array of non-empty strings")

    budgets = _object(scenario["budgets"], "budgets", fields={"tool_calls", "game_ticks", "wall_clock_seconds"})
    for name in budgets:
        _positive_integer(budgets[name], f"budgets.{name}")
    _string(scenario["agent_task"], "agent_task")

    goal = _object(scenario["goal"], "goal", fields={"kind", "item", "required_count"})
    if goal["kind"] not in GOAL_KINDS:
        _fail("goal.kind", f"must be one of: {', '.join(sorted(GOAL_KINDS))}")
    _string(goal["item"], "goal.item")
    _positive_integer(goal["required_count"], "goal.required_count")

    evaluator = _object(scenario["evaluator"], "evaluator", fields={"version", "projection", "agent_access"})
    _string(evaluator["version"], "evaluator.version")
    if evaluator["agent_access"] is not False:
        _fail("evaluator.agent_access", "must be false")
    projection = _object(evaluator["projection"], "evaluator.projection", fields={"kind", "output"})
    if projection["kind"] not in PROJECTION_KINDS:
        _fail("evaluator.projection.kind", f"must be one of: {', '.join(sorted(PROJECTION_KINDS))}")
    output = _string(projection["output"], "evaluator.projection.output")
    if Path(output).name != output or not output.endswith(".json"):
        _fail("evaluator.projection.output", "must be a JSON filename")
    return scenario


def load_scenario(path: Path) -> dict[str, Any]:
    """Load a scenario file and fail with an actionable validation error."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"cannot read scenario {path}: {error.strerror}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"scenario {path} is not valid JSON: {error.msg}") from error
    return validate_scenario(value)
