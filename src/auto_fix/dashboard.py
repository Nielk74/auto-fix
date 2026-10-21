"""Local, read-only web dashboard for workflow run history."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from auto_fix import history
from auto_fix.workflow import redact

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


class Handler(BaseHTTPRequestHandler):
    root: Path
    loopback_only: bool

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        pass

    def _send(self, status: HTTPStatus, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: Any) -> None:
        if data is None:
            self._send(HTTPStatus.NOT_FOUND, b'{"error": "not found"}', "application/json")
            return
        body = redact(json.dumps(data, ensure_ascii=False, default=str)).encode("utf-8")
        self._send(HTTPStatus.OK, body, "application/json")

    def do_GET(self) -> None:  # noqa: N802 - stdlib signature
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        if self.loopback_only and host not in LOOPBACK:
            # Rejecting foreign Host headers prevents DNS-rebinding reads of local evidence.
            self._send(HTTPStatus.FORBIDDEN, b"Forbidden host", "text/plain")
            return
        url = urlsplit(self.path)
        query = {key: values[0] for key, values in parse_qs(url.query).items()}
        run_id = query.get("id", "")
        if url.path in {"/", "/index.html"}:
            page = files("auto_fix").joinpath("dashboard.html").read_bytes()
            self._send(HTTPStatus.OK, page, "text/html")
        elif url.path == "/api/runs":
            self._json({"root": str(self.root), "runs": history.list_runs(self.root)})
        elif url.path == "/api/run":
            self._json(history.run_detail(self.root, run_id))
        elif url.path == "/api/state":
            try:
                step = int(query.get("step", ""))
            except ValueError:
                step = -2
            self._json(history.state_at(self.root, run_id, step))
        elif url.path == "/api/file":
            found = history.read_file(self.root, run_id, query.get("path", ""))
            if found is None:
                self._send(HTTPStatus.NOT_FOUND, b"Not found", "text/plain")
            else:
                # Artifacts are only ever served as JSON or plain text, so stored HTML never runs.
                body, kind = found
                text = redact(body.decode("utf-8", errors="replace")).encode("utf-8")
                self._send(HTTPStatus.OK, text, kind)
        else:
            self._send(HTTPStatus.NOT_FOUND, b"Not found", "text/plain")


def serve(root: Path, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    handler = type(
        "DashboardHandler", (Handler,), {"root": root.resolve(), "loopback_only": host in LOOPBACK}
    )
    return ThreadingHTTPServer((host, port), handler)


def run_dashboard(root: Path, host: str, port: int) -> int:
    if not root.exists():
        print(f"No run history at {root}")
        return 2
    server = serve(root, host, port)
    shown = f"[{host}]" if ":" in host else host
    print(f"Auto Fix dashboard for {root.resolve()} at http://{shown}:{server.server_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
