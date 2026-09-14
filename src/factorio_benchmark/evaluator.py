"""Offline scoring for versioned Factorio benchmark scenarios."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{path} is not valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _item_count(inventory: object, item_name: str) -> int:
    if not isinstance(inventory, list):
        raise ValueError("dedicated_player.inventory must be an array")
    total = 0
    for entry in inventory:
        if not isinstance(entry, dict):
            raise ValueError("inventory entries must be objects")
        if entry.get("name") == item_name:
            count = entry.get("count")
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError("inventory item counts must be non-negative integers")
            total += count
    return total


def evaluate_final_state(scenario_path: Path, final_state_path: Path) -> dict[str, object]:
    """Score an evaluator-only final-state projection for one scenario.

    The projection must be produced after the agent-facing MCP endpoint is shut
    down. This function deliberately has no access to the control transport.
    """
    scenario = _load_object(scenario_path)
    final_state = _load_object(final_state_path)

    scenario_id = scenario.get("scenario_id")
    if not isinstance(scenario_id, str) or not scenario_id:
        raise ValueError("scenario_id must be a non-empty string")
    if final_state.get("scenario_id") != scenario_id:
        raise ValueError("final_state scenario_id does not match scenario")
    if final_state.get("factorio_version") != scenario.get("factorio_version"):
        raise ValueError("final_state factorio_version does not match scenario")

    control = scenario.get("control")
    if not isinstance(control, dict):
        raise ValueError("scenario control must be an object")
    dedicated_player = final_state.get("dedicated_player")
    if not isinstance(dedicated_player, dict):
        raise ValueError("final_state dedicated_player must be an object")
    if dedicated_player.get("name") != control.get("dedicated_player_name"):
        raise ValueError("final_state dedicated player does not match scenario")

    goal = scenario.get("goal")
    if not isinstance(goal, dict) or goal.get("kind") != "player_inventory_item_count":
        raise ValueError("unsupported scenario goal")
    item = goal.get("item")
    required_count = goal.get("required_count")
    if not isinstance(item, str) or not item:
        raise ValueError("goal item must be a non-empty string")
    if not isinstance(required_count, int) or isinstance(required_count, bool) or required_count < 1:
        raise ValueError("goal required_count must be a positive integer")

    actual_count = _item_count(dedicated_player.get("inventory"), item)
    success = actual_count >= required_count
    evaluator = scenario.get("evaluator")
    if not isinstance(evaluator, dict):
        raise ValueError("scenario evaluator must be an object")
    evaluator_version = evaluator.get("version")
    if not isinstance(evaluator_version, str) or not evaluator_version:
        raise ValueError("scenario evaluator version must be a non-empty string")
    return {
        "evaluator_version": evaluator_version,
        "scenario_id": scenario_id,
        "termination_reason": "success" if success else "goal_not_met",
        "score": 1.0 if success else 0.0,
        "predicate": {"item": item, "required_count": required_count, "actual_count": actual_count},
    }
