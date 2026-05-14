# Repository Guidelines

## Project Structure & Module Organization

This repository is a compact Python package for learning a Hermes-style tool-calling loop.

- `mini_hermes/agent.py` contains `MiniAgent`, the conversation loop, model calls, and tool-call execution.
- `mini_hermes/tools.py` defines the tool registry and built-in tools: `read_file`, `list_files`, and `run_shell`.
- `mini_hermes/fake_model.py` provides deterministic fake responses for local tests and demos.
- `mini_hermes/cli.py` exposes the command-line interface.
- `test_agent.py` holds the current unit tests. The `tests/` directory exists but is currently empty.
- `README.md` documents the learning flow and suggested debugger breakpoints.

## Build, Test, and Development Commands

- `uv sync` creates or updates the local `.venv` from `pyproject.toml` and `uv.lock`.
- `uv run python -m unittest -v` runs the full test suite.
- `uv run mini-hermes --fake "读一下 README.md"` runs the deterministic fake model and needs no API key.
- `uv run mini-hermes "看一下 README.md 里写了什么"` runs the console entry point with OpenAI-compatible settings from `.env`.
- `uv run mini-hermes-web` starts the local trace UI at `http://127.0.0.1:8787`.
- `uv add <package>` adds a dependency and updates `uv.lock`.

For real OpenAI-compatible calls, copy `.env.example` to `.env` and set `OPENAI_API_KEY`, optionally `OPENAI_BASE_URL`, and optionally `OPENAI_MODEL`. The CLI loads `.env` by default without overriding existing shell variables.

## Coding Style & Naming Conventions

Use Python 3.9+ syntax and keep modules small and explicit. Follow the existing style: 4-space indentation, type hints for public function signatures where practical, `snake_case` for functions and variables, and `CamelCase` for classes. Keep tool names stable and lower snake case because model tool schemas expose them directly.

## Testing Guidelines

Tests use the standard library `unittest` framework. Add new tests in `test_agent.py` for small changes, or create `tests/test_*.py` if the suite grows. Prefer `MiniAgent(fake=True)` for deterministic behavior. Cover tool dispatch, trace events, error handling, and message-loop behavior when changing `agent.py`, `tools.py`, or the web trace flow.

## Commit & Pull Request Guidelines

This checkout has no `.git` directory, so no local commit convention can be verified. Use concise, imperative commit messages such as `Add shell tool test` or `Handle invalid tool JSON`. Pull requests should describe the behavior change, list verification commands, mention API/config changes, and include CLI output when user-visible behavior changes.

## Security & Configuration Tips

Do not commit `.env`, API keys, or local `.venv` contents. Keep tool paths constrained to the working directory, and be cautious when modifying `run_shell`, since it executes shell commands from model-supplied arguments.
