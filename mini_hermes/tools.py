from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def names(self) -> set[str]:
        return set(self._tools)

    def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        if name not in self._tools:
            return json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False)
        try:
            result = self._tools[name].handler(arguments)
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _safe_path(raw_path: str) -> Path:
    base = Path.cwd().resolve()
    path = (base / raw_path).resolve()
    if base != path and base not in path.parents:
        raise ValueError(f"path escapes working directory: {raw_path}")
    return path


def read_file(args: dict[str, Any]) -> dict[str, Any]:
    path = _safe_path(str(args.get("path", "")))
    max_chars = int(args.get("max_chars", 4000))
    text = path.read_text(encoding="utf-8")
    return {
        "path": str(path),
        "content": text[:max_chars],
        "truncated": len(text) > max_chars,
    }


def list_files(args: dict[str, Any]) -> dict[str, Any]:
    raw_path = str(args.get("path", "."))
    path = _safe_path(raw_path)
    files = []
    for child in sorted(path.iterdir()):
        files.append({
            "name": child.name,
            "type": "dir" if child.is_dir() else "file",
        })
    return {"path": str(path), "files": files}


def run_shell(args: dict[str, Any]) -> dict[str, Any]:
    command = str(args.get("command", ""))
    if not command.strip():
        return {"error": "command is required"}
    completed = subprocess.run(
        command,
        shell=True,
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        timeout=10,
    )
    return {
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(Tool(
        name="read_file",
        description="Read a UTF-8 text file under the current working directory.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path to read."},
                "max_chars": {"type": "integer", "description": "Maximum characters to return."},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        handler=read_file,
    ))
    registry.register(Tool(
        name="list_files",
        description="List files in a directory under the current working directory.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative directory path to list."},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        handler=list_files,
    ))
    registry.register(Tool(
        name="run_shell",
        description="Run a short shell command in the current working directory.",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run."},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
        handler=run_shell,
    ))
    return registry

