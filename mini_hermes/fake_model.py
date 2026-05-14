from __future__ import annotations

import json
from types import SimpleNamespace


def _message(content: str = "", tool_calls: list | None = None) -> SimpleNamespace:
    return SimpleNamespace(content=content, tool_calls=tool_calls or [])


def _tool_call(name: str, arguments: dict, call_id: str = "call_1") -> SimpleNamespace:
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=name,
            arguments=json.dumps(arguments, ensure_ascii=False),
        ),
    )


class FakeModel:
    """Small deterministic model for learning and tests.

    It imitates an OpenAI chat client enough for MiniAgent:
    first call asks for a tool, second call summarizes the tool result.
    """

    def create(self, **kwargs):
        messages = kwargs["messages"]
        has_tool_result = any(message.get("role") == "tool" for message in messages)
        loaded_skill = any(
            message.get("role") == "tool"
            and message.get("name") == "skill_view"
            and "systematic-debugging" in message.get("content", "")
            for message in messages
        )
        if not has_tool_result:
            user_text = messages[-1]["content"].lower()
            if "debug" in user_text or "bug" in user_text or "报错" in user_text or "排查" in user_text:
                msg = _message(tool_calls=[_tool_call("skill_view", {"name": "systematic-debugging"})])
            elif "list" in user_text or "列" in user_text:
                msg = _message(tool_calls=[_tool_call("list_files", {"path": "."})])
            elif "shell" in user_text or "命令" in user_text:
                msg = _message(tool_calls=[_tool_call("run_shell", {"command": "pwd"})])
            else:
                msg = _message(tool_calls=[_tool_call("read_file", {"path": "README.md"})])
        elif loaded_skill and not any(
            message.get("role") == "tool" and message.get("name") == "read_file"
            for message in messages
        ):
            msg = _message(tool_calls=[_tool_call("read_file", {"path": "README.md"}, call_id="call_2")])
        else:
            last_tool = next(message for message in reversed(messages) if message.get("role") == "tool")
            try:
                payload = json.loads(last_tool["content"])
            except json.JSONDecodeError:
                summary = last_tool["content"]
            else:
                if "error" in payload:
                    summary = payload["error"]
                elif "content" in payload:
                    summary = payload["content"]
                elif "files" in payload:
                    summary = "\n".join(
                        item if isinstance(item, str) else item.get("path", item.get("name", str(item)))
                        for item in payload["files"]
                    )
                else:
                    summary = json.dumps(payload, ensure_ascii=False)
            msg = _message(content=f"我已经拿到工具结果：\n{summary[:600]}")

        return SimpleNamespace(
            choices=[SimpleNamespace(message=msg, finish_reason="tool_calls" if msg.tool_calls else "stop")]
        )
