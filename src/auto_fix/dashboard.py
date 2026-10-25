"""Local web dashboard for workflow run history and, with ``--config``, run controls."""

from __future__ import annotations

import getpass
import json
import secrets
import shutil
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

from auto_fix import artifacts, health, history, jobs
from auto_fix.actions import Actions
from auto_fix.config import load_settings
from auto_fix.jobs import JobError
from auto_fix.schedules import ScheduleStore
from auto_fix.triage import TriageStore
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
BODY_LIMIT = 64 * 1024
LOG_LIMIT = 200_000
TOKEN_META = b'<meta name="auto-fix-token" content="">'


class Handler(BaseHTTPRequestHandler):
    root: Path
    shown_root: str
    loopback_only: bool
    # Set only when the dashboard was started with --config; otherwise it stays read-only.
    actions: Actions | None
    config: Path | None
    token: str
    # TeamCity build configurations from the config: the Repairs project's workflows.
    build_types: list[str]
    schedules: ScheduleStore

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

    def _json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        if data is None:
            self._send(HTTPStatus.NOT_FOUND, b'{"error": "not found"}', "application/json")
            return
        body = redact(json.dumps(data, ensure_ascii=False, default=str)).encode("utf-8")
        self._send(status, body, "application/json")

    def _error(self, status: HTTPStatus, message: str, fields: dict[str, str] | None = None):
        self._json({"error": message, "fields": fields or {}}, status)

    def _host_allowed(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        if self.loopback_only and host not in LOOPBACK:
            # Rejecting foreign Host headers prevents DNS-rebinding reads of local evidence.
            self._send(HTTPStatus.FORBIDDEN, b"Forbidden host", "text/plain")
            return False
        return True

    def authorize(self) -> str:
        """The user acting through this request. A team setup replaces this with a login."""
        return getpass.getuser()

    def do_GET(self) -> None:  # noqa: N802 - stdlib signature
        if not self._host_allowed():
            return
        url = urlsplit(self.path)
        query = {key: values[0] for key, values in parse_qs(url.query).items()}
        run_id = query.get("id", "")
        if url.path in {"/", "/index.html"}:
            page = files("auto_fix").joinpath("dashboard.html").read_bytes()
            if self.actions:
                # Only this page can read the token, so other sites cannot forge actions.
                page = page.replace(
                    TOKEN_META, f'<meta name="auto-fix-token" content="{self.token}">'.encode()
                )
            self._send(HTTPStatus.OK, page, "text/html")
        elif url.path == "/api/runs":
            try:
                found = history.run_page(
                    self.root,
                    page=int(query.get("page", "1")),
                    page_size=int(query.get("page_size", "25")),
                    **{
                        key: query.get(key, "")
                        for key in ("workflow", "status", "q", "since", "until")
                    },
                    sort=query.get("sort") or "-started",
                )
            except ValueError as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self._json({"root": self.shown_root, **found})
        elif url.path == "/api/tests":
            if query.get("name"):
                self._json(history.runs_for_test(self.root, query["name"]))
            else:
                self._json(history.failing_tests(self.root, query.get("q", "")))
        elif url.path == "/api/metrics":
            try:
                self._json(history.metrics(self.root, int(query.get("days", "30"))))
            except ValueError as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
        elif url.path == "/api/settings":
            self._json(
                {
                    "root": self.shown_root,
                    "config_path": str(self.config) if self.config else "",
                    "config": health.describe(load_settings(self.config)) if self.config else None,
                    "runner": jobs.runner_state(self.actions.state_dir) if self.actions else None,
                }
            )
        elif url.path == "/api/run":
            detail = history.run_detail(self.root, run_id)
            if detail is not None and self.actions:
                detail["controls"] = self.actions.available(run_id)
            self._json(detail)
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
        elif url.path == "/api/download":
            found = artifacts.download(self.root, run_id, query.get("path", ""))
            if found is None:
                self._send(HTTPStatus.NOT_FOUND, b"Artifact not found", "text/plain")
                return
            handle, kind, filename = found
            with handle:
                length = handle.seek(0, 2)
                handle.seek(0)
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(length))
                self.send_header(
                    "Content-Disposition", "attachment; filename*=UTF-8''" + quote(filename)
                )
                for key, value in SECURITY_HEADERS.items():
                    self.send_header(key, value)
                self.end_headers()
                shutil.copyfileobj(handle, self.wfile, length=1024 * 1024)
        elif url.path == "/api/workflows":
            self._json(
                {
                    "actions": self.actions is not None,
                    "user": self.authorize() if self.actions else "",
                    "workflows": jobs.WORKFLOWS if self.actions else {},
                    "build_types": self.build_types,
                }
            )
        elif url.path == "/api/schedules":
            self._json({"schedules": self.schedules.all(), "timezone": self.schedules.timezone})
        elif url.path == "/api/jobs":
            if not self.actions:
                self._json({"jobs": [], "runner": {"alive": False, "waiting": ""}})
                return
            shown = [
                job
                for job in self.actions.store.all()
                if job.get("status") in {"running", "queued", "failed"}
            ]
            self._json({"jobs": shown, "runner": jobs.runner_state(self.actions.state_dir)})
        elif url.path == "/api/batches":
            try:
                page, page_size = int(query.get("page", "1")), int(query.get("page_size", "25"))
                if page < 1 or not 1 <= page_size <= 100:
                    raise ValueError("Invalid history page")
            except ValueError as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            store = self.actions.store if self.actions else jobs.JobStore(self.root, create=False)
            batches = sorted(
                [job for job in store.all(include_dismissed=True) if job["kind"] == "batch"],
                key=lambda job: job["created"],
                reverse=True,
            )
            pages = max(1, (len(batches) + page_size - 1) // page_size)
            page = min(page, pages)
            self._json(
                {
                    "batches": [
                        store.batch_summary(job["id"])
                        for job in batches[(page - 1) * page_size : page * page_size]
                    ],
                    "total": len(batches),
                    "page": page,
                    "pages": pages,
                }
            )
        elif url.path == "/api/jobs/log" and self.actions:
            try:
                job = self.actions.store.get(query.get("id", ""))
            except JobError:
                job = None
            log = self.actions.store.dir / f"{job['id']}.log" if job else None
            if log is None or not log.is_file():
                self._send(HTTPStatus.NOT_FOUND, b"No log yet", "text/plain")
                return
            data = log.read_bytes()[-LOG_LIMIT:]
            text = redact(data.decode("utf-8", errors="replace")).encode("utf-8")
            self._send(HTTPStatus.OK, text, "text/plain")
        else:
            self._send(HTTPStatus.NOT_FOUND, b"Not found", "text/plain")

    def _body(self) -> dict[str, Any] | None:
        """The JSON body of an allowed write request, or None after an error response."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= BODY_LIMIT:
            self.close_connection = True
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Request too large")
            return None
        # Read the body before any refusal: answering first makes Windows reset the socket.
        raw = self.rfile.read(length)
        if not self.actions:
            self._error(HTTPStatus.FORBIDDEN, "Read-only dashboard: start it with --config")
            return None
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{self.headers.get('Host', '')}":
            self._error(HTTPStatus.FORBIDDEN, "Cross-site request refused")
            return None
        if not secrets.compare_digest(self.headers.get("X-Auto-Fix-Token", ""), self.token):
            self._error(HTTPStatus.FORBIDDEN, "Missing or wrong dashboard token; reload the page")
            return None
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Expected JSON")
            return None
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            body = None
        if not isinstance(body, dict):
            self._error(HTTPStatus.BAD_REQUEST, "Expected a JSON object")
            return None
        return body

    def do_POST(self) -> None:  # noqa: N802 - stdlib signature
        if not self._host_allowed():
            return
        body = self._body()
        if body is None or self.actions is None:
            return
        by = self.authorize()
        store, path = self.actions.store, urlsplit(self.path).path
        try:
            if path == "/api/jobs":
                kind = str(body.get("kind", ""))
                if kind not in jobs.WORKFLOWS:
                    raise JobError(f"Unknown workflow: {kind}")
                self._json({"job": store.add(kind, body.get("params") or {}, by)})
            elif path == "/api/jobs/preview":
                kind = str(body.get("kind", ""))
                if kind not in jobs.WORKFLOWS:
                    raise JobError(f"Unknown workflow: {kind}")
                params = jobs.validate(kind, body.get("params") or {}, self.actions.state_dir)
                self._json({"command": jobs.command(kind, params, self.config)})
            elif path == "/api/jobs/remove":
                store.remove(str(body.get("id", "")))
                self._json({"ok": True})
            elif path == "/api/jobs/stop":
                self._json(self.actions.stop_job(str(body.get("id", "")), by))
            elif path == "/api/jobs/move":
                store.move(str(body.get("id", "")), int(body.get("delta", 0)))
                self._json({"ok": True})
            elif path == "/api/runs/triage":
                run_id = str(body.get("run", ""))
                if run_id not in history.discover_runs(self.root):
                    raise JobError("Unknown run")
                record = TriageStore(self.root).update(
                    run_id,
                    str(body.get("action", "")),
                    by,
                    note=str(body.get("note") or ""),
                    until=str(body.get("until") or ""),
                    rating=str(body.get("rating") or ""),
                )
                self._json({"triage": record})
            elif path == "/api/health":
                self._json({"checks": health.check(load_settings(self.config))})
            elif path == "/api/schedules/preview":
                self._json({"upcoming": self.schedules.preview(body)})
            elif path == "/api/runs/action":
                done = self.actions.perform(
                    str(body.get("run", "")), str(body.get("action", "")), by, body.get("step")
                )
                self._json(done)
            elif path == "/api/schedules":
                self._json({"schedule": self.schedules.save(body, by, str(body.get("id", "")))})
            elif path == "/api/schedules/toggle":
                self.schedules.toggle(str(body.get("id", "")), body.get("enabled"))
                self._json({"ok": True})
            elif path == "/api/schedules/remove":
                self.schedules.remove(str(body.get("id", "")))
                self._json({"ok": True})
            else:
                self._send(HTTPStatus.NOT_FOUND, b"Not found", "text/plain")
        except JobError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc), exc.fields)
        except (TypeError, ValueError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))


def serve(
    root: Path, host: str = "127.0.0.1", port: int = 8765, config: Path | None = None
) -> ThreadingHTTPServer:
    # Show the directory as given (mapped drives intact); containment checks use resolved paths.
    attributes = {
        "root": root.resolve(),
        "shown_root": str(root.absolute()),
        "loopback_only": host in LOOPBACK,
        "actions": Actions(root.resolve()) if config else None,
        "config": config.resolve() if config else None,
        "token": secrets.token_urlsafe(32),
        "build_types": list(load_settings(config).teamcity.build_types) if config else [],
        "schedules": ScheduleStore(
            root.resolve(), load_settings(config).timezone if config else "Europe/Paris"
        ),
    }
    handler = type("DashboardHandler", (Handler,), attributes)
    return ThreadingHTTPServer((host, port), handler)


def run_dashboard(
    root: Path, host: str, port: int, config: Path | None = None, runner: bool = True
) -> int:
    if not root.exists():
        if not config:
            print(f"No run history at {root}")
            return 2
        root.mkdir(parents=True)
    server = serve(root, host, port, config)
    shown = f"[{host}]" if ":" in host else host
    mode = "with run controls" if config else "read-only"
    print(
        f"Auto Fix dashboard ({mode}) for {root.absolute()} at http://{shown}:{server.server_port}/"
    )
    worker = None
    if config and runner:
        worker = jobs.Runner(config, root.resolve())
        worker.start_thread()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if worker:
            worker.stop()
        server.server_close()
    return 0
