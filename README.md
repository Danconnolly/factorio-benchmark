# Factorio benchmark

A separate benchmark repository for player-constrained Factorio scenarios and
independent evaluators. It does not contain an agent-facing MCP server, RCON
credentials, or evaluator access reachable from an agent.

## Control regression fixture

`fixtures/player-control-test-baseline.zip` is the versioned general-purpose
save used for live `factorio-player-mcp` acceptance tests. Its companion
metadata records the Factorio version, SHA-256, size, and intended control
surface. It is deliberately separate from the future scenario-specific save.

## First scenario

`scenarios/smelt-one-iron-plate.v1.json` pins a deterministic early-game task:
produce one iron plate from one iron ore, coal, and a stone furnace within fixed
call, tick, and wall-clock budgets.

The manifest declares the intended Factorio version (`2.1.17`), dedicated
player identity, control protocol version, seed, starting inventory, budgets,
goal, and evaluator version. The referenced baseline save is a pinned artifact generated from a real
Factorio instance. Its provenance and the verified live control gate are
recorded in [`docs/BASELINE_STATUS.md`](docs/BASELINE_STATUS.md).

## Independent evaluator

`factorio_benchmark.evaluator.evaluate_final_state()` scores an evaluator-only
final-state projection after the agent-facing MCP endpoint has stopped. It
validates the scenario ID, game version, configured player identity, and the
final player-inventory predicate. It has no control transport dependency.

Run its tests with:

    PYTHONPATH=src python3 -m unittest discover -s tests -v

## Verified baseline gate

The pinned baseline has passed a legal scripted MCP run using a separate copied
run save. After control stopped, an evaluator-only projection from that final
save passed offline scoring. The run bundle, final save, projection, and score
are retained outside this repository as recorded in
[`docs/BASELINE_STATUS.md`](docs/BASELINE_STATUS.md).

## External-agent runner

`scripts/run_smelt_agent.py` provisions the isolated server/client arrangement
and invokes one external agent process. The included concrete adapter,
`scripts/openai_mcp_agent.py`, connects an OpenAI-compatible Chat Completions
model to the constrained MCP broker; its default configuration is endpoint
`http://ollama.boodle.info:11434/v1` and API model `qwen3.8:latest`.
Ollama accepts that runnable alias at its API endpoint; retain the
digest-qualified pinned identity separately in the runner's `--model-id`.
Before provisioning, the script asks the supplied control Python runtime to
confirm it has FastMCP Streamable HTTP and the `factorio-player-mcp`
ActorService. Without that exact runtime capability it fails closed.

The runner owns a `factorio_constrained_broker.py` process. The agent receives
`BENCHMARK_AGENT_PROMPT` and an MCP configuration pointing to that broker's
loopback Streamable HTTP endpoint; it receives neither an RCON password nor an
evaluator credential. The broker exposes only actor observation, local
observation, placement, inventory interaction, and waiting—never generic RCON,
Lua, command, or evaluation tools. It produces the call/tick measurement and
transcript itself; agent-reported accounting is ignored.

For example (do not run this until the paths and agent executable are real):

    python3 scripts/run_smelt_agent.py --factorio /path/to/bin/x64/factorio --control-python /path/to/control-venv/bin/python --mod-archive /path/to/factorio-player-mcp_0.1.16.zip --client-template /path/to/factorio-user-data --runs-dir /path/to/runs --model-id example-model --agent-command '["/path/to/agent", "--its-options"]'

`--agent-command` is a JSON argv array, so runner flags cannot be consumed as
agent arguments. Server, broker, and player readiness are bounded gates before
agent wall-clock timing begins. The agent starts in a new session and its whole
process group is terminated before an evaluator password is created. A nonzero,
timeout, malformed, or budget-ineligible attempt is explicitly unscored with a
zero result; only a valid broker measurement permits evaluator startup. The
manifest indexes retained final saves, evaluator files, logs, transcript, and
measurements with digests, while credentials exist only in process memory.

For the included adapter, the API and recorded model strings are intentionally
different:

    python3 scripts/run_smelt_agent.py --factorio /path/to/bin/x64/factorio --control-python /path/to/control-venv/bin/python --mod-archive /path/to/factorio-player-mcp_0.1.16.zip --client-template /path/to/factorio-user-data --runs-dir /path/to/runs --model-id qwen3.8:latest@sha256:22130167c4c20e20c7b71454612966ca8e8171e9b3cc8ab6ce8aa6cbfec79643 --agent-command '["python3", "scripts/openai_mcp_agent.py", "--model", "qwen3.8:latest", "--max-turns", "12"]'
