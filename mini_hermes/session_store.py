from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class SessionStore:
    """Tiny JSON-backed session store for the learning web UI."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(".mini_hermes") / "sessions.json"

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        data = self._read()
        sessions = sorted(
            data.get("sessions", []),
            key=lambda session: session.get("updated_at", 0),
            reverse=True,
        )
        return [
            {key: value for key, value in session.items() if key != "messages"}
            for session in sessions[:limit]
        ]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        for session in self._read().get("sessions", []):
            if session.get("id") == session_id:
                return dict(session)
        return None

    def save_session(
        self,
        session_id: str,
        *,
        messages: list[dict[str, Any]],
        model: str,
        fake: bool,
        usage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = self._read()
        sessions = data.setdefault("sessions", [])
        existing = next((item for item in sessions if item.get("id") == session_id), None)
        now = time.time()
        user_messages = [
            message for message in messages
            if message.get("role") == "user" and message.get("content")
        ]
        assistant_messages = [
            message for message in messages
            if message.get("role") == "assistant" and message.get("content")
        ]
        title = self._snippet(user_messages[0]["content"] if user_messages else session_id, 48)
        preview_source = (
            assistant_messages[-1]["content"]
            if assistant_messages
            else user_messages[-1]["content"] if user_messages else ""
        )
        session = {
            "id": session_id,
            "title": title,
            "preview": self._snippet(preview_source, 96),
            "model": model,
            "fake": fake,
            "created_at": existing.get("created_at", now) if existing else now,
            "updated_at": now,
            "message_count": len([
                message for message in messages
                if message.get("role") in {"user", "assistant"}
            ]),
            "usage": usage or (existing or {}).get("usage"),
            "messages": messages,
        }
        if existing is None:
            sessions.append(session)
        else:
            existing.clear()
            existing.update(session)
        self._write(data)
        return dict(session)

    def delete_session(self, session_id: str) -> bool:
        data = self._read()
        sessions = data.get("sessions", [])
        next_sessions = [session for session in sessions if session.get("id") != session_id]
        if len(next_sessions) == len(sessions):
            return False
        data["sessions"] = next_sessions
        self._write(data)
        return True

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"sessions": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"sessions": []}
        if not isinstance(data, dict):
            return {"sessions": []}
        if not isinstance(data.get("sessions"), list):
            data["sessions"] = []
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(self.path)

    def _snippet(self, text: str, max_chars: int) -> str:
        compact = " ".join(str(text or "").split())
        if len(compact) <= max_chars:
            return compact
        return compact[:max_chars - 1].rstrip() + "…"
