from __future__ import annotations

import argparse
import os
from pathlib import Path

from .agent import MiniAgent


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a tiny Hermes-style agent.")
    parser.add_argument("message", nargs="*", default=["读一下 README.md"])
    parser.add_argument("--fake", action="store_true", help="Use deterministic fake model.")
    parser.add_argument("--chat", action="store_true", help="Keep one multi-turn conversation in the terminal.")
    parser.add_argument("--model", default=None, help="Model name for OpenAI-compatible API.")
    parser.add_argument("--base-url", default=None, help="OpenAI-compatible base URL.")
    return parser


def main() -> None:
    load_dotenv()

    args = build_parser().parse_args()
    message = " ".join(args.message)

    agent = MiniAgent(fake=args.fake, model=args.model, base_url=args.base_url)
    if not args.chat:
        print(agent.run(message))
        return

    if message:
        print(agent.run_turn(message))

    while True:
        try:
            next_message = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not next_message:
            continue
        if next_message in {"/exit", "/quit"}:
            return
        if next_message == "/reset":
            agent.reset()
            print("Conversation reset.")
            continue
        print(agent.run_turn(next_message))


if __name__ == "__main__":
    main()
