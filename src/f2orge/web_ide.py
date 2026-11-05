"""Loopback-only browser IDE backed by the local F²ORGE interpreter."""
from __future__ import annotations

import json
import secrets
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
    "/brand.ico": ("brand.ico", "image/x-icon"),
    "/favicon.ico": ("brand.ico", "image/x-icon"),
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
    worksheets = [
        session.interpreter.worksheet_schema(name)
        for name in sorted(session.interpreter.worksheets)
    ]
    return {"variables": variables, "equations": equations, "worksheets": worksheets}


def _handler(session: DesktopSession):
    session_lock = threading.RLock()
    chart_previews: Dict[str, str] = {}

    class BrowserIDEHandler(BaseHTTPRequestHandler):
        server_version = "F2ORGE-IDE"

        def _send(self, status: int, content_type: str, payload: bytes, *, embeddable: bool = False) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            frame_policy = "frame-ancestors 'self'" if embeddable else "frame-ancestors 'none'"
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                             f"connect-src 'self'; img-src 'self' data: blob:; base-uri 'none'; {frame_policy}")
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
            if self.path == "/chart3d.js":
                from .charts import THREE_D_SCRIPT

                self._send(200, "text/javascript; charset=utf-8", THREE_D_SCRIPT.encode("utf-8"))
                return
            preview_prefix = "/api/chart-preview/"
            if self.path.startswith(preview_prefix):
                with session_lock:
                    preview = chart_previews.get(self.path[len(preview_prefix):])
                if preview is None:
                    self._send(404, "text/plain; charset=utf-8", b"Chart preview expired")
                else:
                    self._send(
                        200,
                        "text/html; charset=utf-8",
                        preview.encode("utf-8"),
                        embeddable=True,
                    )
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
            if self.path not in (
                "/api/execute", "/api/transpile", "/api/plot", "/api/chart", "/api/worksheet",
            ):
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
                if self.path == "/api/chart":
                    if not isinstance(data, dict):
                        self._json(400, {"success": False, "output": "Expected a chart object"})
                        return
                    chart_type, table, x_name = data.get("type"), data.get("table"), data.get("x")
                    if not isinstance(chart_type, str) or not isinstance(x_name, str):
                        self._json(400, {"success": False, "output": "Chart type and x column are required"})
                        return
                    y_names = data.get("y")
                    axes = data.get("axes")
                elif self.path == "/api/worksheet":
                    if not isinstance(data, dict):
                        self._json(400, {"success": False, "output": "Expected a worksheet request"})
                        return
                    worksheet_name = data.get("name")
                    worksheet_values = data.get("inputs", {})
                    if not isinstance(worksheet_name, str) or not isinstance(worksheet_values, dict):
                        self._json(400, {"success": False, "output": "Expected a worksheet name and inputs object"})
                        return
                else:
                    field = "command" if self.path == "/api/plot" else "source"
                    source = data.get(field) if isinstance(data, dict) else None
                    if not isinstance(source, str):
                        self._json(400, {"success": False, "output": f"Expected a {field} string"})
                        return
                if self.path == "/api/transpile":
                    target = data.get("target")
                    if target not in ("python", "micropython", "cpp", "ti-basic"):
                        self._json(
                            400,
                            {"success": False, "output": "Choose Python, C++, MicroPython, or TI-84 BASIC"},
                        )
                        return
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                self._json(400, {"success": False, "output": "Invalid JSON request"})
                return
            if self.path == "/api/chart":
                from .charts import (
                    ChartError,
                    render_3d_html,
                    render_3d_preview_html,
                    render_table_html,
                    render_table_svg,
                )

                try:
                    if chart_type.endswith("3d"):
                        if not isinstance(axes, list) or len(axes) != 3 or not all(
                            isinstance(axis, str) for axis in axes
                        ):
                            raise ChartError("select three columns for the 3D axes")
                        output = render_3d_html(table, chart_type, axes[0], axes[1], axes[2])
                        preview = render_3d_preview_html(table, chart_type, axes[0], axes[1], axes[2])
                        svg = ""
                        preview_id = secrets.token_urlsafe(18)
                        with session_lock:
                            chart_previews[preview_id] = preview
                            while len(chart_previews) > 8:
                                chart_previews.pop(next(iter(chart_previews)))
                    else:
                        svg = render_table_svg(table, chart_type, x_name, y_names)
                        output = render_table_html(svg, f"{chart_type.title()} table chart")
                        preview_id = ""
                    self._json(200, {
                        "success": True,
                        "output": output,
                        "previewUrl": f"/api/chart-preview/{preview_id}" if preview_id else "",
                        "svg": svg,
                    })
                except ChartError as err:
                    self._json(400, {"success": False, "output": err.format()})
                return
            if self.path == "/api/worksheet":
                from .plot import render_svg

                try:
                    with session_lock:
                        result = session.interpreter.evaluate_worksheet(worksheet_name, worksheet_values)
                    for graph in result["graphs"]:
                        graph["svg"] = render_svg(
                            f"{graph['output']} vs {graph['variable']}",
                            graph["xLabel"],
                            graph["yLabel"],
                            [("", graph["points"])],
                        )
                except ForgeError as err:
                    self._json(400, {"success": False, "output": err.format()})
                    return
                self._json(200, {"success": True, **result})
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
