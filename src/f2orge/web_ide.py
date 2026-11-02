"""Loopback-only browser IDE backed by the local F²ORGE interpreter."""
from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from typing import Dict
from urllib.parse import urlsplit

from .desktop import DesktopSession
from .errors import ForgeError

_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/brand.svg": ("brand.svg", "image/svg+xml"),
}


def _workspace(session: DesktopSession) -> Dict[str, object]:
    variables = [
        {"name": name, "value": str(value)}
        for name, value in sorted(session.interpreter.variables.items())
    ]
    equations = [
        {
            "name": name,
            "signature": f"{', '.join(equation.inputs)} -> {', '.join(equation.outputs)}",
        }
        for name, equation in sorted(session.interpreter.equations.items())
    ]
    return {"variables": variables, "equations": equations}


def _handler(session: DesktopSession):
    session_lock = threading.RLock()

    class BrowserIDEHandler(BaseHTTPRequestHandler):
        server_version = "F2ORGE-IDE"

        def _send(self, status: int, content_type: str, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                             "connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _local_host(self) -> bool:
            host = self.headers.get("Host", "").lower()
            return host in ("localhost", "127.0.0.1", f"localhost:{self.server.server_port}",
                            f"127.0.0.1:{self.server.server_port}")

        def _same_origin(self) -> bool:
            origin = self.headers.get("Origin")
            if origin is None:
                return True
            try:
                parsed = urlsplit(origin)
                return (
                    parsed.scheme == "http"
                    and parsed.hostname in ("localhost", "127.0.0.1")
                    and parsed.port == self.server.server_port
                    and not parsed.username
                    and not parsed.password
                )
            except ValueError:
                return False

        def _json(self, status: int, data: Dict[str, object]) -> None:
            self._send(status, "application/json; charset=utf-8",
                       json.dumps(data).encode("utf-8"))

        def do_GET(self) -> None:
            if not self._local_host():
                self._send(403, "text/plain; charset=utf-8", b"Loopback requests only")
                return
            if self.path == "/api/state":
                with session_lock:
                    state = _workspace(session)
                self._json(200, state)
                return
            asset = _ASSETS.get(self.path)
            if asset is None:
                self._send(404, "text/plain; charset=utf-8", b"Not found")
                return
            filename, content_type = asset
            try:
                payload = files("f2orge").joinpath("web", filename).read_bytes()
            except OSError:
                self._send(500, "text/plain; charset=utf-8", b"IDE assets are unavailable")
                return
            self._send(200, content_type, payload)

        def do_POST(self) -> None:
            if not self._local_host() or not self._same_origin():
                self._send(403, "text/plain; charset=utf-8", b"Loopback requests only")
                return
            if self.path == "/api/clear":
                with session_lock:
                    session.clear()
                    state = _workspace(session)
                self._json(200, {"success": True, **state})
                return
            if self.path not in ("/api/execute", "/api/transpile", "/api/plot"):
                self._send(404, "text/plain; charset=utf-8", b"Not found")
                return
            if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
                self._json(415, {"success": False, "output": "Expected application/json"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size > 1_000_000:
                    self._json(413, {"success": False, "output": "Request is too large"})
                    return
                data = json.loads(self.rfile.read(size).decode("utf-8"))
                field = "command" if self.path == "/api/plot" else "source"
                source = data.get(field) if isinstance(data, dict) else None
                if not isinstance(source, str):
                    self._json(400, {"success": False, "output": f"Expected a {field} string"})
                    return
                if self.path == "/api/transpile":
                    target = data.get("target")
                    if target not in ("python", "cpp"):
                        self._json(400, {"success": False, "output": "Target must be 'python' or 'cpp'"})
                        return
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                self._json(400, {"success": False, "output": "Invalid JSON request"})
                return
            if self.path == "/api/transpile":
                from .transpile import transpile

                try:
                    generated = transpile(source, target, "<IDE editor>")
                except ForgeError as err:
                    self._json(400, {"success": False, "output": err.format()})
                    return
                self._json(200, {"success": True, "output": generated, "target": target})
                return
            if self.path == "/api/plot":
                from .plot import render_svg

                try:
                    with session_lock:
                        x_label, y_label, points = session.plot_data(source)
                    title = f"{y_label} vs {x_label}"
                    svg = render_svg(title, x_label, y_label, [("", points)])
                except ForgeError as err:
                    self._json(400, {"success": False, "output": err.format()})
                    return
                self._json(200, {
                    "success": True,
                    "title": title,
                    "xLabel": x_label,
                    "yLabel": y_label,
                    "svg": svg,
                })
                return
            with session_lock:
                output, success = session.execute(source)
                state = _workspace(session)
            self._json(200, {"success": success, "output": output, **state})

        def log_message(self, _format: str, *_args) -> None:
            return

    return BrowserIDEHandler


class _LoopbackServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve_desktop_ide() -> None:
    """Run the browser IDE in an embedded desktop webview on a local-only server."""
    try:
        import webview
        from webview.errors import WebViewException
    except ModuleNotFoundError as err:
        if err.name != "webview":
            raise
        raise ForgeError(
            "the desktop webview is not installed",
            title="Cannot start desktop IDE",
            hint='Install the desktop extra with: pip install "f2orge[desktop]".',
        ) from err

    server = _LoopbackServer(("127.0.0.1", 0), _handler(DesktopSession()))
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    url = f"http://127.0.0.1:{server.server_port}/"
    try:
        webview.create_window(
            "F²ORGE — Engineering IDE",
            url,
            width=1360,
            height=900,
            min_size=(960, 640),
        )
        webview.start()
    except (OSError, RuntimeError, WebViewException) as err:
        raise ForgeError(
            f"cannot start the desktop webview: {err}",
            title="Cannot start desktop IDE",
            hint="Check that a supported WebView runtime is installed and available.",
        ) from err
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)


def serve_browser_ide(port: int = 8765, open_browser: bool = True) -> None:
    """Serve the browser IDE on loopback; the server is never exposed on the LAN."""
    server = _LoopbackServer(("127.0.0.1", port), _handler(DesktopSession()))
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"F²ORGE Browser IDE: {url}")
    print("Local only. Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.35, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping F²ORGE Browser IDE.")
    finally:
        server.server_close()
