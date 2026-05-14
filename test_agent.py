import unittest
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch

from mini_hermes.agent import MiniAgent
from mini_hermes.cli import build_parser, load_dotenv
from mini_hermes.web import get_session_agent, reset_session


class MiniAgentTests(unittest.TestCase):
    def test_fake_model_reads_file(self):
        agent = MiniAgent(fake=True)

        result = agent.run("读一下 README.md")

        self.assertIn("工具结果", result)
        self.assertIn("Mini Hermes Agent", result)

    def test_fake_model_lists_files(self):
        agent = MiniAgent(fake=True)

        result = agent.run("list files")

        self.assertIn("工具结果", result)
        self.assertIn("README.md", result)

    def test_unknown_tool_is_returned_as_tool_error(self):
        agent = MiniAgent(fake=True)

        agent.valid_tool_names.clear()
        result = agent.run("读一下 README.md")

        self.assertIn("unknown tool", result)

    def test_agent_emits_trace_events_for_tool_loop(self):
        events = []
        agent = MiniAgent(fake=True, trace_callback=events.append)

        result = agent.run("读一下 README.md")

        event_types = [event["type"] for event in events]
        self.assertIn("user_message", event_types)
        self.assertIn("build_api_kwargs", event_types)
        self.assertIn("model_response", event_types)
        self.assertIn("tool_call", event_types)
        self.assertIn("tool_result", event_types)
        self.assertIn("final_response", event_types)
        self.assertIn("工具结果", result)

    def test_trace_event_payloads_are_snapshots(self):
        events = []
        agent = MiniAgent(fake=True, trace_callback=events.append)

        agent.run("读一下 README.md")

        user_event = events[0]
        self.assertEqual(2, len(user_event["data"]["messages"]))

    def test_fake_agent_emits_stream_deltas_for_final_response(self):
        deltas = []
        agent = MiniAgent(fake=True, stream_callback=deltas.append)

        result = agent.run("读一下 README.md")

        self.assertGreater(len(deltas), 1)
        self.assertEqual("".join(deltas), result)

    def test_load_dotenv_reads_current_directory_without_overriding_env(self):
        with TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "OPENAI_API_KEY=from-file\n"
                "OPENAI_BASE_URL=http://example.test/v1\n"
                "OPENAI_MODEL=file-model\n",
                encoding="utf-8",
            )

            with patch.dict("os.environ", {"OPENAI_MODEL": "existing-model"}, clear=True):
                load_dotenv(env_path)

                import os

                self.assertEqual(os.environ["OPENAI_API_KEY"], "from-file")
                self.assertEqual(os.environ["OPENAI_BASE_URL"], "http://example.test/v1")
                self.assertEqual(os.environ["OPENAI_MODEL"], "existing-model")

    def test_cli_parser_accepts_unquoted_multi_word_message(self):
        args = build_parser().parse_args(["读一下", "README.md"])

        self.assertEqual(args.message, ["读一下", "README.md"])

    def test_cli_parser_accepts_chat_mode(self):
        args = build_parser().parse_args(["--chat", "--fake", "读一下", "README.md"])

        self.assertTrue(args.chat)
        self.assertTrue(args.fake)
        self.assertEqual(args.message, ["读一下", "README.md"])

    def test_empty_model_response_is_retried_before_final_response(self):
        class EmptyThenContentClient:
            def __init__(self):
                self.calls = 0

            def create(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    content = ""
                else:
                    content = "重试后拿到了有效回答。"
                message = SimpleNamespace(content=content, tool_calls=[])
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        events = []
        agent = MiniAgent(fake=True, trace_callback=events.append)
        agent.client = EmptyThenContentClient()

        result = agent.run("读一下 README.md")

        self.assertEqual("重试后拿到了有效回答。", result)
        self.assertEqual(2, agent.client.calls)
        self.assertIn("empty_response_retry", [event["type"] for event in events])

    def test_real_agent_streams_first_model_response_when_callback_is_set(self):
        class StreamingClient:
            def __init__(self):
                self.stream_requested = False

            def create(self, **kwargs):
                self.stream_requested = kwargs.get("stream") is True
                if self.stream_requested:
                    return iter([
                        SimpleNamespace(
                            choices=[SimpleNamespace(
                                finish_reason=None,
                                delta=SimpleNamespace(content="你好", tool_calls=[]),
                            )],
                        ),
                        SimpleNamespace(
                            choices=[SimpleNamespace(
                                finish_reason="stop",
                                delta=SimpleNamespace(content="，世界", tool_calls=[]),
                            )],
                        ),
                    ])
                message = SimpleNamespace(content="not streamed", tool_calls=[])
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        deltas = []
        agent = MiniAgent(fake=False, api_key="test-key", stream_callback=deltas.append)
        agent.client = StreamingClient()

        result = agent.run("你好")

        self.assertTrue(agent.client.stream_requested)
        self.assertEqual(["你好", "，世界"], deltas)
        self.assertEqual("你好，世界", result)

    def test_streaming_failure_falls_back_to_non_streaming_response(self):
        class FailingStreamClient:
            def __init__(self):
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)
                if kwargs.get("stream") is True:
                    raise RuntimeError("<!doctype html><title>Unable to connect</title>")
                message = SimpleNamespace(content="fallback answer", tool_calls=[])
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        events = []
        deltas = []
        agent = MiniAgent(
            fake=False,
            api_key="test-key",
            trace_callback=events.append,
            stream_callback=deltas.append,
        )
        agent.client = FailingStreamClient()

        result = agent.run("你好")

        self.assertEqual("fallback answer", result)
        self.assertEqual([], deltas)
        self.assertEqual([True, None], [call.get("stream") for call in agent.client.calls])
        self.assertIn("streaming_fallback", [event["type"] for event in events])

    def test_run_turn_preserves_history_between_turns(self):
        class EchoMessageCountClient:
            def __init__(self):
                self.message_counts = []

            def create(self, **kwargs):
                self.message_counts.append(len(kwargs["messages"]))
                content = f"message count: {len(kwargs['messages'])}"
                message = SimpleNamespace(content=content, tool_calls=[])
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        agent = MiniAgent(fake=True)
        agent.client = EchoMessageCountClient()

        first = agent.run_turn("第一轮")
        second = agent.run_turn("第二轮")

        self.assertEqual("message count: 2", first)
        self.assertEqual("message count: 4", second)
        self.assertEqual(["system", "user", "assistant", "user", "assistant"], [
            message["role"] for message in agent.messages
        ])

    def test_web_session_reuses_same_agent_history(self):
        session_id = "unit-test-session"
        reset_session(session_id)

        agent = get_session_agent(session_id, fake=True)
        agent.run_turn("第一轮")

        same_agent = get_session_agent(session_id, fake=True)
        same_agent.run_turn("第二轮")

        self.assertIs(agent, same_agent)
        self.assertGreaterEqual(len(same_agent.messages), 5)
        self.assertEqual("第二轮", same_agent.messages[-2]["content"])

        reset_session(session_id)


if __name__ == "__main__":
    unittest.main()
