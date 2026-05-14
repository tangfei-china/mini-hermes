import unittest
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch

from mini_hermes.agent import MiniAgent
from mini_hermes.cli import build_parser, load_dotenv
from mini_hermes.skills import SkillLoader, parse_skill_markdown, slugify
from mini_hermes.tools import build_default_registry
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
        self.assertEqual(len(agent._initial_messages()) + 1, len(user_event["data"]["messages"]))

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

    def test_cli_parser_accepts_list_skills_option(self):
        args = build_parser().parse_args(["--list-skills"])

        self.assertTrue(args.list_skills)

    def test_skill_markdown_parser_reads_frontmatter(self):
        skill = parse_skill_markdown(
            Path("/tmp/example/SKILL.md"),
            "---\n"
            "name: careful-debugging\n"
            "description: Debug with evidence first.\n"
            "---\n"
            "\n"
            "# Careful Debugging\n"
            "Find the root cause before fixing.\n",
        )

        self.assertEqual("careful-debugging", skill.name)
        self.assertEqual("careful-debugging", skill.slug)
        self.assertEqual("Debug with evidence first.", skill.description)
        self.assertIn("Find the root cause", skill.content)

    def test_skill_loader_scans_nested_skill_files_and_loads_by_slug(self):
        with TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "software-development" / "debugging"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: Debugging Skill\ndescription: Investigate first.\n---\n"
                "# Debugging Skill\nUse evidence.\n",
                encoding="utf-8",
            )

            loader = SkillLoader(Path(tmpdir))
            skills = loader.list_skills()
            loaded = loader.load(["debugging-skill"])

            self.assertEqual(["Debugging Skill"], [skill.name for skill in skills])
            self.assertEqual(["Debugging Skill"], [skill.name for skill in loaded.loaded])
            self.assertEqual([], loaded.missing)
            self.assertIn("Use evidence.", loaded.prompt)

    def test_skill_loader_reads_and_saves_existing_skill(self):
        with TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "software-development" / "debugging"
            skill_dir.mkdir(parents=True)
            skill_path = skill_dir / "SKILL.md"
            skill_path.write_text(
                "---\nname: Debugging Skill\ndescription: Investigate first.\n---\n"
                "# Debugging Skill\nUse evidence.\n",
                encoding="utf-8",
            )
            loader = SkillLoader(Path(tmpdir))
            updated = (
                "---\nname: Debugging Skill\ndescription: Updated.\n---\n"
                "# Debugging Skill\nUpdated body.\n"
            )

            original = loader.read_markdown("debugging-skill")
            saved = loader.save_existing("debugging-skill", updated)

            self.assertIn("Use evidence.", original)
            self.assertEqual(str(skill_path), str(saved.path))
            self.assertEqual("Updated body.\n", skill_path.read_text(encoding="utf-8").split("# Debugging Skill\n", 1)[1])

    def test_skill_loader_imports_skill_into_custom_directory(self):
        with TemporaryDirectory() as tmpdir:
            loader = SkillLoader(Path(tmpdir))
            markdown = (
                "---\nname: Careful Debugging\ndescription: Debug carefully.\n---\n"
                "# Careful Debugging\nFind the cause.\n"
            )

            skill = loader.import_markdown(markdown)

            self.assertEqual("careful-debugging", skill.slug)
            self.assertEqual(
                Path(tmpdir) / "custom" / "careful-debugging" / "SKILL.md",
                skill.path,
            )
            self.assertIn("Find the cause.", skill.path.read_text(encoding="utf-8"))
            self.assertEqual("careful-debugging", slugify(skill.name))

    def test_skill_loader_deletes_custom_skill(self):
        with TemporaryDirectory() as tmpdir:
            loader = SkillLoader(Path(tmpdir))
            skill = loader.import_markdown(
                "---\nname: Delete Me\ndescription: Temporary.\n---\n"
                "# Delete Me\nTemporary body.\n"
            )

            deleted = loader.delete("delete-me")

            self.assertEqual(str(skill.path), str(deleted))
            self.assertFalse(skill.directory.exists())

    def test_skill_loader_refuses_to_delete_non_custom_skill(self):
        with TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "software-development" / "debugging"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: Debugging Skill\ndescription: Investigate first.\n---\n"
                "# Debugging Skill\nUse evidence.\n",
                encoding="utf-8",
            )
            loader = SkillLoader(Path(tmpdir))

            with self.assertRaises(ValueError):
                loader.delete("debugging-skill")

    def test_default_registry_exposes_skill_tools(self):
        registry = build_default_registry()

        self.assertIn("skills_list", registry.names())
        self.assertIn("skill_view", registry.names())
        payload = registry.dispatch("skill_view", {"name": "systematic-debugging"})

        self.assertIn("systematic-debugging", payload)

    def test_fake_agent_auto_loads_matching_skill(self):
        events = []
        agent = MiniAgent(fake=True, trace_callback=events.append)

        result = agent.run("帮我 debug 一个问题")

        event_types = [event["type"] for event in events]
        self.assertIn("tool_call", event_types)
        self.assertTrue(any(
            event["type"] == "tool_call"
            and event["data"]["name"] == "skill_view"
            for event in events
        ))
        self.assertIn("skills_loaded", event_types)
        self.assertEqual(["systematic-debugging"], [
            skill.slug for skill in agent.active_skills
        ])
        self.assertIn("工具结果", result)

    def test_reset_session_clears_cached_agent(self):
        session_id = "unit-test-reset"
        reset_session(session_id)

        agent = get_session_agent(session_id, fake=True)
        agent.run_turn("第一轮")
        reset_session(session_id)
        fresh = get_session_agent(session_id, fake=True)

        self.assertIsNot(agent, fresh)
        self.assertEqual(["system", "system"], [
            message["role"] for message in fresh.messages
        ])

        reset_session(session_id)

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
        initial_count = len(agent.messages)

        first = agent.run_turn("第一轮")
        second = agent.run_turn("第二轮")

        self.assertEqual(f"message count: {initial_count + 1}", first)
        self.assertEqual(f"message count: {initial_count + 3}", second)
        self.assertEqual(
            ["system"] * initial_count + ["user", "assistant", "user", "assistant"],
            [
            message["role"] for message in agent.messages
            ],
        )

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
