from __future__ import annotations

import json
import os
import queue
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .agent import MiniAgent
from .cli import load_dotenv
from .skills import SkillLoader


STATIC_DIR = Path(__file__).with_name("static")
SESSIONS: dict[str, MiniAgent] = {}
SESSIONS_LOCK = threading.Lock()


class TraceRun:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append(self, event: dict[str, Any]) -> None:
        self.events.append({
            "step": len(self.events) + 1,
            **event,
        })


def get_session_agent(
    session_id: str,
    fake: bool,
) -> MiniAgent:
    key = f"{'fake' if fake else 'real'}:{session_id}"
    with SESSIONS_LOCK:
        agent = SESSIONS.get(key)
        if agent is None or agent.fake != fake:
            agent = MiniAgent(fake=fake)
            SESSIONS[key] = agent
        return agent


def reset_session(session_id: str) -> None:
    with SESSIONS_LOCK:
        for prefix in ("fake", "real"):
            SESSIONS.pop(f"{prefix}:{session_id}", None)
            session_prefix = f"{prefix}:{session_id}:"
            for key in list(SESSIONS):
                if key.startswith(session_prefix):
                    SESSIONS.pop(key, None)


class MiniHermesWebHandler(BaseHTTPRequestHandler):
    server_version = "MiniHermesWeb/0.1"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        if path == "/app.js":
            self._send_file(STATIC_DIR / "app.js", "text/javascript; charset=utf-8")
            return
        if path == "/styles.css":
            self._send_file(STATIC_DIR / "styles.css", "text/css; charset=utf-8")
            return
        if path == "/favicon.ico":
            self._send_icon()
            return
        if path == "/api/stream":
            self._stream_run()
            return
        if path == "/api/new-session":
            self._send_json({"session_id": uuid.uuid4().hex})
            return
        if path == "/api/skills":
            self._send_json({
                "skills": [skill.summary() for skill in SkillLoader().list_skills()],
            })
            return
        if path.startswith("/api/skills/"):
            slug = path.removeprefix("/api/skills/")
            try:
                loader = SkillLoader()
                skill = loader.find(slug)
                if skill is None:
                    self._send_json({"ok": False, "error": f"skill not found: {slug}"}, status=404)
                    return
                self._send_json({
                    "ok": True,
                    "skill": skill.summary(),
                    "markdown": loader.read_markdown(slug),
                })
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=500)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/skills/save":
            self._save_skill()
            return
        if path == "/api/skills/import":
            self._import_skill()
            return
        if path == "/api/skills/delete":
            self._delete_skill()
            return
        if path != "/api/run":
            self.send_error(404)
            return

        body = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
            message = str(payload.get("message") or "").strip() or "读一下 README.md"
            fake = bool(payload.get("fake", False))
            session_id = str(payload.get("session_id") or uuid.uuid4().hex)
            if payload.get("reset"):
                reset_session(session_id)
            trace = TraceRun()
            agent = get_session_agent(session_id, fake)
            agent.trace_callback = trace.append
            agent.stream_callback = None
            final = agent.run_turn(message)
        except Exception as exc:
            self._send_json(
                {
                    "ok": False,
                    "error": str(exc),
                    "events": trace.events if "trace" in locals() else [],
                },
                status=500,
            )
            return

        self._send_json({
            "ok": True,
            "final": final,
            "events": trace.events,
            "model": agent.model,
            "fake": fake,
            "skills": [skill.summary() for skill in agent.active_skills],
            "session_id": session_id,
        })

    def _read_json_body(self) -> dict[str, Any]:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
        payload = json.loads(body.decode("utf-8") or "{}")
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _save_skill(self) -> None:
        try:
            payload = self._read_json_body()
            slug = str(payload.get("slug") or "").strip()
            markdown = str(payload.get("markdown") or "")
            if not slug:
                raise ValueError("slug is required")
            if not markdown.strip():
                raise ValueError("markdown is required")
            skill = SkillLoader().save_existing(slug, markdown)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        self._send_json({"ok": True, "skill": skill.summary()})

    def _import_skill(self) -> None:
        try:
            payload = self._read_json_body()
            markdown = str(payload.get("markdown") or "")
            if not markdown.strip():
                raise ValueError("markdown is required")
            skill = SkillLoader().import_markdown(markdown)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        self._send_json({"ok": True, "skill": skill.summary()})

    def _delete_skill(self) -> None:
        try:
            payload = self._read_json_body()
            slug = str(payload.get("slug") or "").strip()
            if not slug:
                raise ValueError("slug is required")
            deleted_path = SkillLoader().delete(slug)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        self._send_json({"ok": True, "deleted_path": str(deleted_path)})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _stream_run(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        message = params.get("message", ["读一下 README.md"])[0].strip() or "读一下 README.md"
        fake = params.get("fake", ["0"])[0] in {"1", "true", "yes"}
        session_id = params.get("session_id", [uuid.uuid4().hex])[0].strip() or uuid.uuid4().hex
        if params.get("reset", ["0"])[0] in {"1", "true", "yes"}:
            reset_session(session_id)
        events: queue.Queue[dict[str, Any] | None] = queue.Queue()
        trace = TraceRun()

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def send(event_type: str, payload: dict[str, Any]) -> None:
            events.put({"event": event_type, "payload": payload})

        def trace_callback(event: dict[str, Any]) -> None:
            trace.append(event)
            send("trace", trace.events[-1])

        def stream_callback(delta: str) -> None:
            send("delta", {"text": delta})

        def worker() -> None:
            try:
                agent = get_session_agent(session_id, fake)
                agent.trace_callback = trace_callback
                agent.stream_callback = stream_callback
                final = agent.run_turn(message)
                send("done", {
                    "ok": True,
                    "final": final,
                    "events": trace.events,
                    "model": agent.model,
                    "fake": fake,
                    "skills": [skill.summary() for skill in agent.active_skills],
                    "session_id": session_id,
                })
            except Exception as exc:
                send("run_error", {
                    "ok": False,
                    "error": str(exc),
                    "events": trace.events,
                })
            finally:
                events.put(None)

        threading.Thread(target=worker, daemon=True).start()

        while True:
            item = events.get()
            if item is None:
                break
            self._send_sse(item["event"], item["payload"])

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_icon(self) -> None:
        data = (
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
            "<rect width='32' height='32' rx='7' fill='#008b87'/>"
            "<path d='M8 10h16M8 16h12M8 22h8' stroke='white' stroke-width='3' "
            "stroke-linecap='round'/>"
            "</svg>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_sse(self, event_type: str, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False)
        self.wfile.write(f"event: {event_type}\n".encode("utf-8"))
        self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
        self.wfile.flush()


def main() -> None:
    load_dotenv()
    host = os.getenv("MINI_HERMES_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("MINI_HERMES_WEB_PORT", "8787"))
    server = ThreadingHTTPServer((host, port), MiniHermesWebHandler)
    print(f"Mini Hermes Trace running at http://{host}:{port}")
    server.serve_forever()

if __name__ == "__main__":
    main()
