import asyncio
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from factorio_benchmark.session import CallbackRequest, run_callback_attempt, validate_callback_result
from factorio_benchmark.smelt_session import (
    SmeltSessionRuntime, run_smelt_callback_session, run_smelt_session,
)


class SessionCallbackTests(unittest.TestCase):
    def test_callback_session_builds_callback_namespace_without_provisioning(self) -> None:
        runtime = SmeltSessionRuntime(
            factorio=Path("/factorio/bin/x64/factorio"),
            control_python=Path("/usr/bin/python3"),
            mod_archive=Path("/mods/factorio-player-mcp.zip"),
            client_template=Path("/client-template"),
            runs_dir=Path("/runs"),
            run_name="callback-run",
        )

        async def callback(request):
            return {"answer": "done"}

        with patch("factorio_benchmark.smelt_session.run_smelt_session") as run:
            run.return_value = {"terminal_status": "completed"}
            result = run_smelt_callback_session(
                runtime=runtime, model_id="test-model", callback=callback,
            )

        self.assertEqual(result, {"terminal_status": "completed"})
        args = run.call_args.args[0]
        self.assertEqual(args, Namespace(
            factorio=runtime.factorio, control_python=runtime.control_python,
            mod_archive=runtime.mod_archive, client_template=runtime.client_template,
            runs_dir=runtime.runs_dir, run_name=runtime.run_name, model_id="test-model",
            agent_command=("in-process-callback",),
        ))
        self.assertIs(run.call_args.kwargs["callback"], callback)

    def test_callback_request_contains_only_prompt_and_constrained_mcp(self) -> None:
        request = CallbackRequest(
            prompt="goal", mcp_config={"mcpServers": {"factorio": {
                "transport": "streamable-http", "url": "http://127.0.0.1:38123/mcp"}}},
        )
        encoded = json.dumps(request.as_dict()).lower()
        self.assertNotIn("rcon", encoded)
        self.assertNotIn("password", encoded)
        self.assertNotIn("evaluator", encoded)

    def test_callback_result_requires_mapping_and_does_not_trust_agent_score(self) -> None:
        self.assertEqual(validate_callback_result({"answer": "done", "score": 1}), {"answer": "done"})
        with self.assertRaisesRegex(ValueError, "mapping"):
            validate_callback_result("done")

    def test_callback_timeout_cancels_access_before_evaluation(self) -> None:
        cancelled = asyncio.Event()

        async def callback(request):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        status, exit_data, result = asyncio.run(run_callback_attempt(
            callback, CallbackRequest("goal", {}), timeout_seconds=.01,
        ))
        self.assertEqual(status, "agent_callback_timeout")
        self.assertEqual(exit_data["kind"], "timeout")
        self.assertIsNone(result)
        self.assertTrue(cancelled.is_set())

    def test_callback_exception_is_a_structured_unscored_outcome(self) -> None:
        async def callback(request):
            raise RuntimeError("agent bridge failed")

        status, exit_data, result = asyncio.run(run_callback_attempt(
            callback, CallbackRequest("goal", {}), timeout_seconds=1,
        ))
        self.assertEqual(status, "agent_callback_error")
        self.assertEqual(exit_data["kind"], "callback_error")
        self.assertIsNone(result)

    def test_session_allocates_fresh_loopback_ports_for_every_factorio_role(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "src" / "factorio_benchmark" / "smelt_session.py").read_text(encoding="utf-8")

        self.assertNotIn("CONTROL_PORT", source)
        self.assertNotIn("EVALUATOR_PORT", source)
        self.assertGreaterEqual(source.count("allocate_loopback_port()"), 3)

    def test_provisioning_failure_returns_written_manifest_after_run_directory_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = Namespace(
                factorio=root / "factorio", control_python=Path(sys.executable),
                mod_archive=root / "mod.zip", client_template=root / "client",
                runs_dir=root / "runs", run_name="failed", model_id="model",
                agent_command=("agent",),
            )
            with patch("factorio_benchmark.smelt_session.subprocess.run") as check, patch(
                "factorio_benchmark.smelt_session.validate_pinned_archive",
                side_effect=ValueError("bad baseline"),
            ):
                check.return_value.returncode = 0
                result = run_smelt_session(args)
            manifest = root / "runs" / "failed" / "run-manifest.json"
            self.assertTrue(manifest.is_file())
            self.assertEqual(result["terminal_status"], "runner_failed")
            self.assertFalse(result["eligible_for_scoring"])
            self.assertEqual(result["run_bundle_path"], str((root / "runs" / "failed").resolve()))
            self.assertEqual(len(result["run_manifest_sha256"]), 64)
