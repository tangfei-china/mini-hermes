from __future__ import annotations

import json
import os
import time
from typing import Any, Callable

from .fake_model import FakeModel
from .skills import Skill, SkillLoader, build_skill_catalog_prompt
from .tools import ToolRegistry, build_default_registry


class MiniAgent:
    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        registry: ToolRegistry | None = None,
        fake: bool = False,
        max_iterations: int = 5,
        max_empty_response_retries: int = 3,
        trace_callback: Callable[[dict[str, Any]], None] | None = None,
        stream_callback: Callable[[str], None] | None = None,
        skill_loader: SkillLoader | None = None,
    ) -> None:
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self.skill_loader = skill_loader or SkillLoader()
        self.registry = registry or build_default_registry(self.skill_loader)
        self.tools = self.registry.schemas()
        self.valid_tool_names = self.registry.names()
        self.max_iterations = max_iterations
        self.max_empty_response_retries = max_empty_response_retries
        self.fake = fake
        self.trace_callback = trace_callback
        self.stream_callback = stream_callback
        self.active_skills: list[Skill] = []
        self.catalog_prompt = build_skill_catalog_prompt(self.skill_loader.list_skills())
        self.messages: list[dict[str, Any]] = self._initial_messages()
        self._trace_run_started_perf = 0.0
        self._trace_run_started_wall_ms = 0.0

        if fake:
            self.client = FakeModel()
        else:
            from openai import OpenAI

            self.client = OpenAI(
                api_key=api_key or os.getenv("OPENAI_API_KEY"),
                base_url=base_url or os.getenv("OPENAI_BASE_URL") or None,
            ).chat.completions

    def run(self, user_message: str) -> str:
        self.reset()
        return self.run_turn(user_message)

    def reset(self) -> None:
        self.messages = self._initial_messages()

    def run_turn(self, user_message: str) -> str:
        self._start_trace_run()
        self.messages.append({"role": "user", "content": user_message})
        empty_response_retries = 0
        self._emit_skills_trace()
        self._emit_trace("user_message", {"content": user_message, "messages": self.messages})

        for iteration in range(1, self.max_iterations + 1):
            build_started = time.perf_counter()
            api_kwargs = self._build_api_kwargs(self.messages)
            self._emit_trace(
                "build_api_kwargs",
                {"iteration": iteration, "api_kwargs": api_kwargs},
                started_perf=build_started,
                ended_perf=time.perf_counter(),
            )
            model_started = time.perf_counter()
            response = self._call_model(api_kwargs)
            model_ended = time.perf_counter()
            assistant_message = response.choices[0].message
            model_duration_ms = round(max(0.0, (model_ended - model_started) * 1000))
            message_content = assistant_message.content or ""
            usage = self._usage_summary(
                getattr(response, "usage", None),
                messages=api_kwargs["messages"],
                output_text=message_content,
                duration_ms=model_duration_ms,
            )
            self._emit_trace(
                "model_response",
                {
                    "iteration": iteration,
                    "message": self._assistant_to_dict(assistant_message)
                    if getattr(assistant_message, "tool_calls", None)
                    else {"role": "assistant", "content": assistant_message.content or ""},
                    "usage": usage,
                },
                started_perf=model_started,
                ended_perf=model_ended,
            )

            if getattr(assistant_message, "tool_calls", None):
                assistant_dict = self._assistant_to_dict(assistant_message)
                self.messages.append(assistant_dict)
                for tool_call in assistant_message.tool_calls:
                    self.messages.append(self._execute_tool_call(tool_call))
                continue

            final = assistant_message.content or ""
            if not final.strip():
                if empty_response_retries < self.max_empty_response_retries:
                    empty_response_retries += 1
                    retry_message = {
                        "role": "user",
                        "content": (
                            "Your last response was empty. Continue the task now: "
                            "answer with visible content, or call a tool if a tool is needed."
                        ),
                    }
                    self.messages.append(retry_message)
                    self._emit_trace(
                        "empty_response_retry",
                        {
                            "iteration": iteration,
                            "attempt": empty_response_retries,
                            "max_attempts": self.max_empty_response_retries,
                            "message": retry_message,
                            "messages": self.messages,
                        },
                    )
                    continue

                final = (
                    "Model returned an empty response after "
                    f"{self.max_empty_response_retries} retries."
                )

            self.messages.append({"role": "assistant", "content": final})
            self._emit_stream_text(final)
            self._emit_trace(
                "final_response",
                {"content": final, "messages": self.messages, "usage": usage},
            )
            return final

        final = "Reached max_iterations before a final answer."
        usage = self._usage_summary(
            None,
            messages=self.messages,
            output_text=final,
            duration_ms=None,
        )
        self._emit_stream_text(final)
        self.messages.append({"role": "assistant", "content": final})
        self._emit_trace(
            "final_response",
            {"content": final, "messages": self.messages, "usage": usage},
        )
        return final

    def _system_message(self) -> dict[str, Any]:
        return {
            "role": "system",
            "content": (
                "You are Mini Hermes. Use tools when they help answer the user. "
                "If the user asks to read, list, inspect, or run local files, call "
                "the appropriate tool instead of guessing. After tool results, give "
                "a short final answer. Never return an empty response."
            ),
        }

    def _initial_messages(self) -> list[dict[str, Any]]:
        messages = [self._system_message()]
        if self.catalog_prompt:
            messages.append({
                "role": "system",
                "content": self.catalog_prompt,
            })
        return messages

    def _emit_skills_trace(self) -> None:
        if not self.active_skills:
            return
        self._emit_trace(
            "skills_loaded",
            {
                "skills": [skill.summary() for skill in self.active_skills],
                "missing": [],
            },
        )

    def _handle_loaded_skill_tool(self, tool_name: str, result_content: str) -> None:
        if tool_name != "skill_view":
            return
        try:
            payload = json.loads(result_content)
        except json.JSONDecodeError:
            return
        slug = payload.get("slug")
        if not slug or payload.get("error"):
            return
        if any(skill.slug == slug for skill in self.active_skills):
            return
        skill = self.skill_loader.find(str(slug))
        if skill is None:
            return
        self.active_skills.append(skill)
        self._emit_skills_trace()

    def _build_api_kwargs(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": messages,
            "tools": self.tools,
        }

    def _call_model(self, api_kwargs: dict[str, Any]):
        if self.stream_callback is not None and not self.fake:
            try:
                return self._call_model_streaming(api_kwargs)
            except Exception as exc:
                self._emit_trace(
                    "streaming_fallback",
                    {
                        "error": self._clean_error_message(exc),
                        "model": api_kwargs.get("model"),
                    },
                )
        return self.client.create(**api_kwargs)

    def _call_model_streaming(self, api_kwargs: dict[str, Any]):
        from types import SimpleNamespace

        stream = self.client.create(
            **api_kwargs,
            stream=True,
            stream_options={"include_usage": True},
        )
        content_parts: list[str] = []
        tool_calls: dict[int, dict[str, Any]] = {}
        finish_reason = None
        usage = None

        for chunk in stream:
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage is not None:
                usage = chunk_usage
            if not getattr(chunk, "choices", None):
                continue
            choice = chunk.choices[0]
            finish_reason = choice.finish_reason or finish_reason
            delta = choice.delta

            if getattr(delta, "content", None):
                content_parts.append(delta.content)
                self.stream_callback(delta.content)

            for tool_delta in getattr(delta, "tool_calls", None) or []:
                index = tool_delta.index if tool_delta.index is not None else 0
                item = tool_calls.setdefault(
                    index,
                    {
                        "id": "",
                        "name": "",
                        "arguments": "",
                    },
                )
                if getattr(tool_delta, "id", None):
                    item["id"] = tool_delta.id
                if getattr(tool_delta, "function", None):
                    if getattr(tool_delta.function, "name", None):
                        item["name"] += tool_delta.function.name
                    if getattr(tool_delta.function, "arguments", None):
                        item["arguments"] += tool_delta.function.arguments

        calls = [
            SimpleNamespace(
                id=item["id"] or f"call_{index}",
                function=SimpleNamespace(
                    name=item["name"],
                    arguments=item["arguments"],
                ),
            )
            for index, item in sorted(tool_calls.items())
        ]
        message = SimpleNamespace(
            content="".join(content_parts),
            tool_calls=calls,
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
            usage=usage,
        )

    def _usage_summary(
        self,
        usage: Any,
        *,
        messages: list[dict[str, Any]],
        output_text: str,
        duration_ms: int | None,
    ) -> dict[str, Any]:
        input_tokens = self._read_usage_int(
            usage,
            "input_tokens",
            "prompt_tokens",
            "prompt_token_count",
        )
        output_tokens = self._read_usage_int(
            usage,
            "output_tokens",
            "completion_tokens",
            "completion_token_count",
        )
        total_tokens = self._read_usage_int(usage, "total_tokens", "total_token_count")
        source = "api" if any(value is not None for value in (input_tokens, output_tokens, total_tokens)) else "estimated"

        if input_tokens is None:
            input_tokens = self._estimate_messages_tokens(messages)
        if output_tokens is None:
            output_tokens = self._estimate_text_tokens(output_text)
        if total_tokens is None:
            total_tokens = input_tokens + output_tokens

        summary: dict[str, Any] = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "source": source,
        }
        if duration_ms and duration_ms > 0 and output_tokens > 0:
            summary["tokens_per_second"] = round(output_tokens / (duration_ms / 1000), 1)
        return summary

    def _read_usage_int(self, usage: Any, *names: str) -> int | None:
        if usage is None:
            return None
        for name in names:
            value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    def _estimate_messages_tokens(self, messages: list[dict[str, Any]]) -> int:
        total = 0
        for message in messages:
            total += self._estimate_text_tokens(str(message.get("content") or ""))
            for tool_call in message.get("tool_calls") or []:
                total += self._estimate_text_tokens(json.dumps(tool_call, ensure_ascii=False))
        return total

    def _estimate_text_tokens(self, text: str) -> int:
        stripped = str(text or "").strip()
        if not stripped:
            return 0
        ascii_count = 0
        non_ascii_count = 0
        for char in stripped:
            if char.isspace():
                ascii_count += 1
            elif ord(char) < 128:
                ascii_count += 1
            else:
                non_ascii_count += 1
        return max(1, round((ascii_count / 4) + non_ascii_count))

    def _assistant_to_dict(self, assistant_message: Any) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": assistant_message.content,
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in assistant_message.tool_calls
            ],
        }

    def _execute_tool_call(self, tool_call: Any) -> dict[str, Any]:
        name = tool_call.function.name
        raw_args = tool_call.function.arguments or "{}"
        self._emit_trace(
            "tool_call",
            {
                "id": tool_call.id,
                "name": name,
                "arguments": raw_args,
            },
        )
        tool_started = time.perf_counter()
        try:
            arguments = json.loads(raw_args)
        except json.JSONDecodeError as exc:
            result = json.dumps({"error": f"invalid JSON arguments: {exc}"}, ensure_ascii=False)
        else:
            if name not in self.valid_tool_names:
                result = json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False)
            else:
                result = self.registry.dispatch(name, arguments)

        tool_message = {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": name,
            "content": result,
        }
        self._emit_trace(
            "tool_result",
            tool_message,
            started_perf=tool_started,
            ended_perf=time.perf_counter(),
        )
        self._handle_loaded_skill_tool(name, result)
        return tool_message

    def _start_trace_run(self) -> None:
        self._trace_run_started_perf = time.perf_counter()
        self._trace_run_started_wall_ms = time.time() * 1000

    def _trace_timing(
        self,
        started_perf: float | None = None,
        ended_perf: float | None = None,
    ) -> dict[str, int]:
        if not self._trace_run_started_perf:
            self._start_trace_run()
        if started_perf is None:
            started_perf = time.perf_counter()
        if ended_perf is None:
            ended_perf = started_perf
        started_delta_ms = max(0.0, (started_perf - self._trace_run_started_perf) * 1000)
        ended_delta_ms = max(started_delta_ms, (ended_perf - self._trace_run_started_perf) * 1000)
        return {
            "started_at": round(self._trace_run_started_wall_ms + started_delta_ms),
            "ended_at": round(self._trace_run_started_wall_ms + ended_delta_ms),
            "duration_ms": round(max(0.0, (ended_perf - started_perf) * 1000)),
            "offset_ms": round(started_delta_ms),
        }

    def _emit_trace(
        self,
        event_type: str,
        data: dict[str, Any],
        *,
        started_perf: float | None = None,
        ended_perf: float | None = None,
    ) -> None:
        if self.trace_callback is None:
            return
        snapshot = json.loads(json.dumps(data, ensure_ascii=False))
        self.trace_callback({
            "type": event_type,
            **self._trace_timing(started_perf, ended_perf),
            "data": snapshot,
        })

    def _emit_stream_text(self, text: str) -> None:
        if self.stream_callback is None:
            return
        if self.fake:
            for start in range(0, len(text), 24):
                self.stream_callback(text[start:start + 24])

    def _clean_error_message(self, exc: Exception) -> str:
        text = str(exc).strip()
        lowered = text.lower()
        if "<!doctype html" in lowered or "<html" in lowered:
            if "unable to connect" in lowered:
                return "Upstream returned an HTML error page: unable to connect."
            return "Upstream returned an HTML error page instead of a model response."
        return text or exc.__class__.__name__
