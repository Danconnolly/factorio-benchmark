# First end-to-end baseline status

Status recorded: 2026-09-13

## Completed and verified

- `smelt-one-iron-plate.v1` is a deterministic Factorio `2.1.17` scenario with a fixed seed, dedicated player `otaci`, a `40`-tool-call budget, a `3600`-tick budget, and a `300`-second wall-clock budget.
- `fixtures/smelt-one-iron-plate-baseline.zip` is a real pinned baseline save. Its SHA-256 is `a8deaf1a1b85b50febbf3dba52007efa8a01f91238883dd5d3d43148b2efef8e`; `unzip -t` passes.
- The fixture metadata pins `factorio-player-mcp` version `0.1.15` and its archive SHA-256, and records the temporary VM-only provisioning boundary.
- The independent evaluator validates scenario ID, Factorio version, fixed player identity, and the required final player inventory count. It has no MCP, RCON, or agent-control dependency.
- Fixture-level evaluator tests cover success, failure, and scenario mismatch.

## Control layer reached

`factorio-player-mcp` has a constrained typed MCP surface for actor/local observation, craft, wait, movement, mining, placement, rotation, and bounded inventory interaction. The control contract forbids arbitrary Lua/RCON, teleportation, item spawning, direct entity mutation, forced research, evaluator access, and full-map dumps.

Its focused and full unit tests pass locally. A local, uncommitted repair corrects furnace input inventory lookup for Factorio 2.1 and handles zero-item inventory transfers without crashing. That repair has not yet been versioned, packaged, deployed, or exercised against this baseline fixture.

## Outstanding end-to-end gate

A prior live attempt established that the automated connected player and typed observation path work. The attempt could not finish the legal smelting sequence because inventory interaction on the fresh scenario furnace returned an empty RCON payload instead of structured JSON while depositing ore.

Before this scenario can be claimed as a completed benchmark result:

1. Version, package, and deploy the pending `factorio-player-mcp` inventory-interaction repair.
2. Run the complete legal scripted sequence through MCP -> typed host bridge -> RCON -> fixed Factorio mod: place furnace, deposit ore and coal, wait for smelting, then withdraw or otherwise retain one iron plate in the player inventory.
3. Provision every attempt from a read-only baseline copy and save only to a distinct run artifact. The prior server lifecycle could modify the supplied starting ZIP on shutdown.
4. Export the evaluator-only final-state projection after the MCP endpoint stops and confirm that offline re-evaluation succeeds reproducibly.

Until all four steps are complete, this repository contains a tested, pinned scenario and independent evaluator foundation, not a completed end-to-end benchmark baseline.
