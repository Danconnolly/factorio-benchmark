# First end-to-end baseline status

Status recorded: 2026-09-13

## Completed and verified

- `smelt-one-iron-plate.v1` is a deterministic Factorio `2.1.17` scenario with a fixed seed, dedicated player `otaci`, a `40`-tool-call budget, a `3600`-tick budget, and a `300`-second wall-clock budget.
- `fixtures/smelt-one-iron-plate-baseline.zip` is the unchanged, pinned baseline save. Its SHA-256 is `a8deaf1a1b85b50febbf3dba52007efa8a01f91238883dd5d3d43148b2efef8e`; `unzip -t` passes.
- The fixture metadata and scenario pin `factorio-player-mcp` `0.1.16`, archive SHA-256 `5af055cb47b063bfc99426e7756196d321661db030fea18bbde608a496c96338`.
- The release archive has the required `factorio-player-mcp_0.1.16/` top-level directory and contains `info.json`, `control.lua`, `settings.lua`, and the English locale file.
- The independent evaluator validates scenario ID, Factorio version, fixed player identity, and the required final player inventory count. Its pure scoring function has no MCP or RCON dependency.
- Fixture-level evaluator tests cover success, failure, and scenario mismatch.
- The control layer has focused and full unit-test coverage for its constrained typed surface, including the Factorio 2.1 furnace input lookup and zero-item inventory-transfer rejection.

## Verified end-to-end baseline run

- Run bundle: `/home/daniel/factorio-benchmark-runs/smelt-one-iron-plate-v1-0.1.16-budget-valid`.
- The provisioner copied the immutable fixture to a run-local `final-save.zip`; the fixture hash was identical before and after the run.
- A real graphical client connected as `otaci` to a Factorio `2.1.17` server loading `factorio-player-mcp` `0.1.16`.
- The legal typed control sequence completed through the host bridge and fixed mod interface: actor observation; local observation; place stone furnace at `(2, 0)`; deposit one iron ore into input; deposit one coal into fuel; wait `600` ticks; withdraw one iron plate from output; final actor observation. It used `8` tool calls and `614` ticks from initial to final observation, within the `40`-call and `3600`-tick budgets.
- The final agent-visible observation reported one `iron-plate` in `otaci`'s inventory.
- The control server and client stopped before evaluator export. A separate evaluator-only server read a copy of the final save; it had no agent-facing MCP endpoint. Its projection is `evaluator-only-final-state.v1.json` in the run bundle.
- Offline `evaluate_final_state()` returned `score: 1.0`, `termination_reason: success`, and predicate `iron-plate >= 1` with actual count `1`.
- The preserved final save SHA-256 is `a6501f7c06e5f4b714a7fe514faf0ae97a24a01f8dac7e99c4573840019ca5eb`.

This establishes the first reproducible, independently scored legal scripted baseline. Agent-model comparisons remain future work and must use fresh isolated copies of the pinned baseline and equivalent run artifacts.

## Additional independently verified live run

Status recorded: 2026-09-14

- Run bundle: `/home/daniel/factorio-benchmark-runs/live-verify-20260914-115242` (it remains outside this repository).
- Factorio `2.1.17` build `87315` used the pinned baseline with SHA-256 `a8deaf1a1b85b50febbf3dba52007efa8a01f91238883dd5d3d43148b2efef8e` and `factorio-player-mcp` `0.1.16`, archive SHA-256 `5af055cb47b063bfc99426e7756196d321661db030fea18bbde608a496c96338`.
- A graphical Wayland client loaded that mod and joined as `otaci`.
- The trace contains `8` calls over `612` ticks and `10.268663110997295` seconds. The evaluator projection records one `iron-plate` for `otaci`.
- Offline evaluation returned score `1.0` with `termination_reason: success`.
- The final controlled-save SHA-256 is `ffb361f8cbf46d46dd28110c9bfe297a07464ce34d3ac8a9ea08d7b9d0703045`.

This is an additional live verification; it does not resolve known robustness or reproducibility limitations.

## Successful OpenAI-compatible Qwen agent run

Status recorded: 2026-09-14

- The first attempt at `/home/daniel/factorio-benchmark-runs/smelt-openai-qwen3.8-pinned-20260914` exited nonzero; it is retained as an unscored attempt. The recorded retry below is the successful run.
- Run bundle: `/home/daniel/factorio-benchmark-runs/smelt-openai-qwen3.8-pinned-20260914-retry1` (it remains outside this repository).
- The concrete OpenAI-compatible adapter used model `qwen3.8:latest@sha256:22130167c4c20e20c7b71454612966ca8e8171e9b3cc8ab6ce8aa6cbfec79643`.
- The trusted broker recorded `7` calls across `1,348` ticks, with agent wall-clock time `90.43782821200148` seconds.
- The final controlled-save SHA-256 is `eab3c1f6d8dcc3a72cb32627770e9012e4acc91e4241053aea84fd89a9f57cf2`.
- Offline evaluation returned score `1.0` with `termination_reason: success`.

## Authoritative Qwen final validation

Status recorded: 2026-09-14

- Run bundle: `/home/daniel/factorio-benchmark-runs/smelt-openai-qwen3.8-pinned-20260914-api-alias-correction` (it remains outside this repository).
- The API model alias was `qwen3.8:latest`; the recorded pinned manifest identity was `qwen3.8:latest@sha256:22130167c4c20e20c7b71454612966ca8e8171e9b3cc8ab6ce8aa6cbfec79643`.
- This validates the corrected API alias while preserving the pinned manifest identity.
- The trusted broker recorded `7` calls across `1,317` ticks, with agent wall-clock time `32.37159557500854` seconds.
- The final controlled-save SHA-256 is `a786e279bce6938d20aef96c333cde6bfac2aa30f40c9e0f1f24e212663b079a`.
- The standalone `offline-evaluator-result.json` is retained and digest-indexed in the run manifest; it records score `1.0` with `termination_reason: success`.
