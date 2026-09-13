# Factorio benchmark

A separate benchmark repository for player-constrained Factorio scenarios and
independent evaluators. It does not contain an agent-facing MCP server, RCON
credentials, or evaluator access reachable from an agent.

## First scenario

`scenarios/smelt-one-iron-plate.v1.json` pins a deterministic early-game task:
produce one iron plate from one iron ore, coal, and a stone furnace within fixed
call, tick, and wall-clock budgets.

The manifest declares the intended Factorio version (`2.1.17`), dedicated
player identity, control protocol version, seed, starting inventory, budgets,
goal, and evaluator version. The referenced baseline save is an explicit
provisioning artifact still to be generated from a real Factorio instance; this
repository does not fabricate one.

## Independent evaluator

`factorio_benchmark.evaluator.evaluate_final_state()` scores an evaluator-only
final-state projection after the agent-facing MCP endpoint has stopped. It
validates the scenario ID, game version, configured player identity, and the
final player-inventory predicate. It has no control transport dependency.

Run its tests with:

    PYTHONPATH=src python3 -m unittest discover -s tests -v

## Remaining end-to-end gate

Provision the pinned baseline save, export an evaluator-only final-state
projection from the final save, then verify an actual legal scripted run scores
identically when re-evaluated offline. Until that is done, this is a tested
scenario/evaluator foundation, not a completed benchmark run.
