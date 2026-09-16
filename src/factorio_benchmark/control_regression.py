"""Deterministic full-surface policy for the player-control regression fixture."""

from __future__ import annotations

from textwrap import dedent
from typing import Final


CONTROL_REGRESSION_STEPS: Final[tuple[dict[str, str], ...]] = (
    {"name": "observe_actor_initial", "operation": "observe_actor"},
    {"name": "observe_local_initial", "operation": "observe_local"},
    {"name": "reject_unknown_recipe", "operation": "craft", "expected_reason": "recipe_not_available"},
    {"name": "reject_unreachable_inventory", "operation": "interact_inventory", "expected_reason": "inventory_target_unavailable"},
    {"name": "reject_uncharted_placement", "operation": "place", "expected_reason": "placement_not_charted"},
    {"name": "craft_gear", "operation": "craft"},
    {"name": "wait_for_craft", "operation": "wait"},
    {"name": "place_furnace", "operation": "place"},
    {"name": "deposit_wood", "operation": "interact_inventory"},
    {"name": "withdraw_wood", "operation": "interact_inventory"},
    {"name": "move_northwest", "operation": "move"},
    {"name": "move_east", "operation": "move"},
    {"name": "move_to_coal", "operation": "move"},
    {"name": "mine_coal", "operation": "mine"},
    {"name": "move_to_drill_location", "operation": "move"},
    {"name": "place_drill", "operation": "place"},
    {"name": "rotate_drill", "operation": "rotate"},
    {"name": "wait_final", "operation": "wait"},
    {"name": "observe_actor_final", "operation": "observe_actor"},
    {"name": "observe_local_final", "operation": "observe_local"},
)


def build_policy() -> str:
    """Build a self-contained typed-control driver run in the control environment."""
    return dedent(
        r'''
        import json
        import os
        import pathlib

        from factorio_player_mcp.rcon import FactorioRconSender
        from factorio_player_mcp.service import ActorService

        run = pathlib.Path(os.environ["BENCHMARK_RUN_DIR"])
        service = ActorService(FactorioRconSender(
            host="127.0.0.1",
            port=int(os.environ["FACTORIO_RCON_PORT"]),
            password=os.environ["FACTORIO_RCON_PASSWORD"],
        ))
        steps = {}

        def assert_result(name, result, status, reason=None):
            assert result.get("status") == status, (name, result)
            if reason is not None:
                assert result.get("reason") == reason, (name, result)
            steps[name] = result
            return result

        initial = assert_result("observe_actor_initial", service.observe_actor(), "completed")
        assert_result("observe_local_initial", service.observe_local(radius=20), "completed")
        assert_result("reject_unknown_recipe", service.craft(recipe="not-a-recipe", count=1), "rejected", "recipe_not_available")
        assert_result("reject_unreachable_inventory", service.interact_inventory(
            x=-3, y=25, item="wood", count=1, operation="deposit", slot="container"
        ), "rejected", "inventory_target_unavailable")
        assert_result("reject_uncharted_placement", service.place(
            item="stone-furnace", x=1000, y=1000, direction="north"
        ), "rejected", "placement_not_charted")
        crafted = assert_result("craft_gear", service.craft(recipe="iron-gear-wheel", count=1), "completed")
        assert crafted.get("queued_count") == 1, crafted
        assert_result("wait_for_craft", service.wait(ticks=120), "completed")
        assert_result("place_furnace", service.place(item="stone-furnace", x=0, y=25, direction="north"), "completed")
        deposited = assert_result("deposit_wood", service.interact_inventory(
            x=0, y=25, item="wood", count=1, operation="deposit", slot="fuel"
        ), "completed")
        assert deposited.get("transferred_count") == 1, deposited
        withdrawn = assert_result("withdraw_wood", service.interact_inventory(
            x=0, y=25, item="wood", count=1, operation="withdraw", slot="fuel"
        ), "completed")
        assert withdrawn.get("transferred_count") == 1, withdrawn
        assert_result("move_northwest", service.move(x=-3, y=22), "completed")
        assert_result("move_east", service.move(x=12, y=20), "completed")
        assert_result("move_to_coal", service.move(x=14, y=20), "completed")
        mined = assert_result("mine_coal", service.mine(x=15.5, y=20.5, count=1), "completed")
        assert mined.get("mined_count") == 1, mined
        assert_result("move_to_drill_location", service.move(x=8, y=25), "completed")
        assert_result("place_drill", service.place(item="burner-mining-drill", x=16.5, y=20.5, direction="east"), "completed")
        rotated = assert_result("rotate_drill", service.rotate(x=16.5, y=20.5), "completed")
        assert rotated.get("target_name") == "burner-mining-drill", rotated
        assert_result("wait_final", service.wait(ticks=60), "completed")
        final = assert_result("observe_actor_final", service.observe_actor(), "completed")
        assert_result("observe_local_final", service.observe_local(radius=10), "completed")
        trace = {
            "tool_calls": len(steps),
            "initial_tick": initial["tick"],
            "final_tick": final["tick"],
            "game_tick_delta": final["tick"] - initial["tick"],
            "steps": steps,
        }
        (run / "player-control-regression-trace.json").write_text(json.dumps(trace, sort_keys=True) + "\n")
        '''
    ).strip() + "\n"
