import unittest
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch

from mini_hermes.agent import MiniAgent
from mini_hermes.cli import build_parser, load_dotenv
from mini_hermes.skills import SkillLoader, parse_skill_markdown, slugify
from mini_hermes.tools import build_default_registry
from mini_hermes.web import TraceRun, get_session_agent, reset_session


class MiniAgentTests(unittest.TestCase):
    def test_chat_message_renders_assistant_markdown_only(self):
        script = Path(__file__).parent / "tests" / "render_markdown_smoke.js"

        result = subprocess.run(
            ["node", str(script)],
            check=False,
            cwd=Path(__file__).parent,
            text=True,
            capture_output=True,
        )

        self.assertEqual("", result.stderr)
        self.assertEqual("ok\n", result.stdout)
        self.assertEqual(0, result.returncode)

    def test_timeline_renders_duration_labels(self):
        script = Path(__file__).parent / "tests" / "timeline_duration_smoke.js"

        result = subprocess.run(
            ["node", str(script)],
            check=False,
            cwd=Path(__file__).parent,
            text=True,
            capture_output=True,
        )

        self.assertEqual("", result.stderr)
        self.assertEqual("ok\n", result.stdout)
        self.assertEqual(0, result.returncode)

    def test_message_usage_renders_token_counts_and_speed(self):
        script = Path(__file__).parent / "tests" / "message_usage_smoke.js"

        result = subprocess.run(
            ["node", str(script)],
            check=False,
            cwd=Path(__file__).parent,
            text=True,
            capture_output=True,
        )

        self.assertEqual("", result.stderr)
        self.assertEqual("ok\n", result.stdout)
        self.assertEqual(0, result.returncode)

    def test_answer_copy_button_copies_raw_assistant_content(self):
        script = Path(__file__).parent / "tests" / "copy_answer_smoke.js"

        result = subprocess.run(
            ["node", str(script)],
            check=False,
            cwd=Path(__file__).parent,
            text=True,
            capture_output=True,
        )

        self.assertEqual("", result.stderr)
        self.assertEqual("ok\n", result.stdout)
        self.assertEqual(0, result.returncode)

    def test_trace_run_fills_missing_timing_from_event_gaps(self):
        trace = TraceRun()

        trace.append({"type": "user_message", "data": {}})
        time.sleep(0.01)
        trace.append({"type": "model_response", "data": {}})

        first, second = trace.events
        self.assertEqual(1, first["step"])
        self.assertEqual(2, second["step"])
        self.assertIn("duration_ms", first)
        self.assertIn("offset_ms", first)
        self.assertGreaterEqual(second["duration_ms"], 1)
        self.assertGreaterEqual(second["offset_ms"], first["offset_ms"])

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

    def test_trace_events_include_step_timings(self):
        class SlowFinalClient:
            def create(self, **kwargs):
                time.sleep(0.01)
                message = SimpleNamespace(content="timed response", tool_calls=[])
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        events = []
        agent = MiniAgent(fake=True, trace_callback=events.append)
        agent.client = SlowFinalClient()

        agent.run("只回答")

        model_event = next(event for event in events if event["type"] == "model_response")
        self.assertIn("started_at", model_event)
        self.assertIn("ended_at", model_event)
        self.assertIn("duration_ms", model_event)
        self.assertIn("offset_ms", model_event)
        self.assertGreaterEqual(model_event["duration_ms"], 1)
        self.assertGreaterEqual(model_event["ended_at"], model_event["started_at"])
        self.assertGreaterEqual(model_event["offset_ms"], 0)

    def test_final_response_includes_api_usage_and_token_speed(self):
        class SlowUsageClient:
            def create(self, **kwargs):
                time.sleep(0.02)
                message = SimpleNamespace(content="usage response", tool_calls=[])
                usage = SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18)
                return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)

        events = []
        agent = MiniAgent(fake=True, trace_callback=events.append)
        agent.client = SlowUsageClient()

        result = agent.run("只回答")

        self.assertEqual("usage response", result)
        model_event = next(event for event in events if event["type"] == "model_response")
        final_event = next(event for event in events if event["type"] == "final_response")
        usage = final_event["data"]["usage"]
        self.assertEqual({
            "input_tokens": 11,
            "output_tokens": 7,
            "total_tokens": 18,
            "source": "api",
        }, {
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
            "total_tokens": usage["total_tokens"],
            "source": usage["source"],
        })
        self.assertGreater(usage["tokens_per_second"], 0)
        self.assertEqual(usage, model_event["data"]["usage"])

    def test_tool_result_trace_includes_dispatch_duration(self):
        class SlowRegistry:
            def schemas(self):
                return []

            def names(self):
                return {"slow_tool"}

            def dispatch(self, name, arguments):
                time.sleep(0.01)
                return "slow result"

        tool_call = SimpleNamespace(
            id="call_1",
            function=SimpleNamespace(name="slow_tool", arguments="{}"),
        )
        events = []
        agent = MiniAgent(fake=True, registry=SlowRegistry(), trace_callback=events.append)

        result = agent._execute_tool_call(tool_call)

        tool_result = next(event for event in events if event["type"] == "tool_result")
        self.assertEqual("slow result", result["content"])
        self.assertGreaterEqual(tool_result["duration_ms"], 1)
        self.assertGreaterEqual(tool_result["ended_at"], tool_result["started_at"])

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
                self.stream_options = None

            def create(self, **kwargs):
                self.stream_requested = kwargs.get("stream") is True
                self.stream_options = kwargs.get("stream_options")
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
                            usage=SimpleNamespace(
                                prompt_tokens=7,
                                completion_tokens=2,
                                total_tokens=9,
                            ),
                        ),
                    ])
                message = SimpleNamespace(content="not streamed", tool_calls=[])
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        deltas = []
        events = []
        agent = MiniAgent(
            fake=False,
            api_key="test-key",
            trace_callback=events.append,
            stream_callback=deltas.append,
        )
        agent.client = StreamingClient()

        result = agent.run("你好")

        self.assertTrue(agent.client.stream_requested)
        self.assertEqual({"include_usage": True}, agent.client.stream_options)
        self.assertEqual(["你好", "，世界"], deltas)
        self.assertEqual("你好，世界", result)
        final_event = next(event for event in events if event["type"] == "final_response")
        self.assertEqual(7, final_event["data"]["usage"]["input_tokens"])
        self.assertEqual(2, final_event["data"]["usage"]["output_tokens"])
        self.assertEqual(9, final_event["data"]["usage"]["total_tokens"])
        self.assertEqual("api", final_event["data"]["usage"]["source"])

    def test_streaming_usage_chunk_can_arrive_without_choices(self):
        class UsageOnlyFinalChunkClient:
            def create(self, **kwargs):
                if kwargs.get("stream") is True:
                    return iter([
                        SimpleNamespace(
                            choices=[SimpleNamespace(
                                finish_reason="stop",
                                delta=SimpleNamespace(content="done", tool_calls=[]),
                            )],
                        ),
                        SimpleNamespace(
                            choices=[],
                            usage=SimpleNamespace(
                                prompt_tokens=5,
                                completion_tokens=1,
                                total_tokens=6,
                            ),
                        ),
                    ])
                message = SimpleNamespace(content="not streamed", tool_calls=[])
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        events = []
        agent = MiniAgent(
            fake=False,
            api_key="test-key",
            trace_callback=events.append,
            stream_callback=lambda delta: None,
        )
        agent.client = UsageOnlyFinalChunkClient()

        result = agent.run("go")

        self.assertEqual("done", result)
        final_event = next(event for event in events if event["type"] == "final_response")
        self.assertEqual(5, final_event["data"]["usage"]["input_tokens"])
        self.assertEqual(1, final_event["data"]["usage"]["output_tokens"])
        self.assertEqual(6, final_event["data"]["usage"]["total_tokens"])

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
