import asyncio
import json
import unittest

from factorio_benchmark.session import CallbackRequest, validate_callback_result


class SessionCallbackTests(unittest.TestCase):
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
