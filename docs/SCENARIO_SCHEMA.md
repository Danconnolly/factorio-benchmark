# Scenario schema

Scenario files are strict JSON contracts. The runner calls
`factorio_benchmark.scenario.load_scenario()` before it starts Factorio or
creates credentials. Unsupported versions, missing fields, wrong types, and
unknown fields are rejected with a path-specific `ValueError`.

## Version 3.0.0

Top-level fields are `scenario_version`, `scenario_id`, `factorio_version`,
`control`, `world`, `initial_state_assertions`, `budgets`, `agent_task`, `goal`, and
`evaluator`. `world` pins the relative baseline-save path and SHA-256 plus each
supported `factorio-player-mcp` control mod's name, version, and SHA-256; exactly
one such mod is supported. `initial_state_assertions` records the exact initial
inventory and researched technologies, which the runner independently verifies
before agent control; `budgets` records positive call, tick,
and wall-clock limits.

`agent_task` is the complete public text provided to the agent. It is data, not
an instruction executed by the runner.

## Supported vocabulary

Only these declarative forms are currently supported:

- Goal: `{"kind": "player_inventory_item_count", "item": "iron-plate", "required_count": 1}`.
- Projection: `{"kind": "dedicated_player_inventory", "output": "evaluator-only-final-state.v1.json"}`.

The projection implementation is selected by its `kind` in trusted Python; a
scenario cannot provide Lua, Python, shell, command, transport, or evaluator
strings. The schema is closed: any such field is unsupported and fails
preflight. Add a new schema version and validator support before adding a new
goal or projection vocabulary item.
