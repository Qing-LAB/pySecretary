from __future__ import annotations

import json
import queue
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pysecretary.config import SecretaryConfig
from pysecretary.console import ConsoleStatusIndicator
from pysecretary.events import AssistantCommand
from pysecretary.prototype import PrototypeController


STATIC_DIR = Path(__file__).with_name("static")


class PrototypeHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def run_prototype_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    config: SecretaryConfig | None = None,
    controller: PrototypeController | None = None,
) -> None:
    app_controller = controller or PrototypeController(config=config)
    handler = _make_handler(app_controller)
    status_indicator = ConsoleStatusIndicator(app_controller)
    try:
        server = PrototypeHTTPServer((host, port), handler)
    except OSError as exc:
        if exc.errno == 98:
            raise SystemExit(
                f"Port {port} is already in use on {host}. "
                f"Try `scripts/run-prototype-ui.sh --port {port + 1}`."
            ) from exc
        raise
    print(f"pySecretary prototype UI listening at http://{host}:{port}")
    status_indicator.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        app_controller.stop()
    finally:
        status_indicator.stop()
        server.server_close()


def _make_handler(controller: PrototypeController) -> type[BaseHTTPRequestHandler]:
    class PrototypeRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/" or self.path == "/index.html":
                self._send_static_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            elif self.path == "/static/app.js":
                self._send_static_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
            elif self.path == "/static/styles.css":
                self._send_static_file(STATIC_DIR / "styles.css", "text/css; charset=utf-8")
            elif self.path == "/api/state":
                self._send_json(controller.snapshot())
            elif self.path == "/api/events":
                self._stream_events(controller)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            if self.path != "/api/commands":
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            payload = self._read_json()
            command_type = str(payload.get("type", ""))
            command_payload = payload.get("payload", {})
            if not isinstance(command_payload, dict):
                command_payload = {}
            controller.handle_command(AssistantCommand(type=command_type, payload=command_payload))
            self._send_json({"ok": True})

        def log_message(self, format: str, *args: object) -> None:
            return

        def _read_json(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                return {}
            return payload if isinstance(payload, dict) else {}

        def _send_json(self, payload: object) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_static_file(self, path: Path, content_type: str) -> None:
            if not path.exists():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            body = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _stream_events(self, app_controller: PrototypeController) -> None:
            subscriber = app_controller.subscribe()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                self._write_sse("snapshot", app_controller.snapshot())
                while True:
                    try:
                        event = subscriber.get(timeout=15)
                    except queue.Empty:
                        self._write_comment("ping")
                        continue
                    self._write_sse("event", event.to_dict())
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                app_controller.unsubscribe(subscriber)

        def _write_sse(self, event_name: str, payload: object) -> None:
            self.wfile.write(f"event: {event_name}\n".encode("utf-8"))
            self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode("utf-8"))
            self.wfile.flush()

        def _write_comment(self, text: str) -> None:
            self.wfile.write(f": {text}\n\n".encode("utf-8"))
            self.wfile.flush()

    return PrototypeRequestHandler
