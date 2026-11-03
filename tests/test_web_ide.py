import json
import sys
import threading
from importlib.machinery import ModuleSpec
from types import ModuleType
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from f2orge.desktop import DesktopSession
from f2orge.errors import ForgeError
from f2orge.web_ide import _LoopbackServer, _handler, serve_desktop_ide


def test_browser_ide_serves_offline_assets_and_local_kernel():
    server = _LoopbackServer(("127.0.0.1", 0), _handler(DesktopSession()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(f"{base_url}/") as response:
            page = response.read().decode("utf-8")
            assert response.status == 200 and "F²ORGE" in page
            assert 'value="micropython"' in page and 'value="ti-basic"' in page
            assert response.headers["Content-Security-Policy"]
        with urlopen(f"{base_url}/app.css") as response:
            styles = response.read().decode("utf-8")
            assert response.status == 200 and "body.dark" in styles
            assert "fonts.googleapis.com" not in styles
            assert "--accent: #dd7a35" in styles
            assert "--panel: #fcfaf5" in styles
            assert "--page: #111214" in styles
            assert ".app-shell { border-radius: 8px; }" in styles
            assert "linear-gradient(to right, transparent 99px, #d6cec2 100px)" in styles
        with urlopen(f"{base_url}/app.js") as response:
            script = response.read().decode("utf-8")
            assert response.status == 200 and "function compileGraph()" in script
            assert "https://" not in script
            assert "Shared variables create a circular dependency" in script
            assert 'node.kind === "Script"' in script
            assert "function startResize" in script
            assert "Share this variable?" in script
            assert "async function showPlot" in script
            assert 'id="charts-panel"' in page
            assert 'id="chart-csv"' in page
            assert '"/api/chart"' in script

        with urlopen(f"{base_url}/brand.svg") as response:
            assert response.headers["Content-Type"].startswith("image/svg+xml")
            assert "F²" in response.read().decode("utf-8")
        with urlopen(f"{base_url}/chart3d.js") as response:
            assert response.headers["Content-Type"].startswith("text/javascript")
            assert "function draw()" in response.read().decode("utf-8")
        payload = json.dumps({"source": "force = 150 kg * 9.81 m/s^2\nforce\n", "target": "python"}).encode("utf-8")
        request = Request(f"{base_url}/api/transpile", payload, {"Content-Type": "application/json"})
        with urlopen(request) as response:
            result = json.loads(response.read())
        assert result["success"] is True and result["target"] == "python"
        assert "unit-safety checks are not retained" in result["output"]
        assert "force = ((150.0 * 1.0) * (9.81 * 1.0))" in result["output"]

        for target, expected in (
            ("micropython", "import math"),
            ("ti-basic", ":ClrHome"),
        ):
            payload = json.dumps({
                "source": "value = sqrt(9)\nvalue\n",
                "target": target,
            }).encode("utf-8")
            request = Request(f"{base_url}/api/transpile", payload, {"Content-Type": "application/json"})
            with urlopen(request) as response:
                result = json.loads(response.read())
            assert result["success"] is True and result["target"] == target
            assert expected in result["output"]

        payload = json.dumps({
            "source": "time = <0 s, 1 s, 2 s>\nposition = <0 m, 3 m, 8 m>\n",
        }).encode("utf-8")
        request = Request(f"{base_url}/api/execute", payload, {"Content-Type": "application/json"})
        with urlopen(request) as response:
            assert json.loads(response.read())["success"] is True
        payload = json.dumps({"command": "plot(time, position)"}).encode("utf-8")
        request = Request(f"{base_url}/api/plot", payload, {"Content-Type": "application/json"})
        with urlopen(request) as response:
            result = json.loads(response.read())
        assert result["success"] is True
        assert result["title"] == "position (m) vs time (s)"
        assert "<svg " in result["svg"] and "<polyline " in result["svg"]

        chart_table = {
            "columns": [
                {"name": "time", "unit": "s"}, {"name": "distance", "unit": "m"},
                {"name": "height", "unit": "m"},
            ],
            "rows": [["0", "0", "1"], ["1", "3", "2"], ["2", "8", "4"]],
        }
        payload = json.dumps({
            "table": chart_table, "type": "scatter", "x": "time", "y": ["distance"],
        }).encode("utf-8")
        request = Request(f"{base_url}/api/chart", payload, {"Content-Type": "application/json"})
        with urlopen(request) as response:
            result = json.loads(response.read())
        assert result["success"] is True
        assert "<circle " in result["svg"] and "<svg " in result["output"]

        payload = json.dumps({
            "table": chart_table, "type": "scatter3d", "x": "time",
            "axes": ["time", "distance", "height"],
        }).encode("utf-8")
        request = Request(f"{base_url}/api/chart", payload, {"Content-Type": "application/json"})
        with urlopen(request) as response:
            result = json.loads(response.read())
        assert result["success"] is True and "<canvas" in result["output"]
        assert result["previewUrl"].startswith("/api/chart-preview/")
        with urlopen(f"{base_url}{result['previewUrl']}") as response:
            preview = response.read().decode("utf-8")
            assert response.headers["Content-Security-Policy"].endswith("frame-ancestors 'self'")
            assert '<script src="/chart3d.js"></script>' in preview

        payload = json.dumps({
            "table": chart_table, "type": "line", "x": "missing", "y": ["distance"],
        }).encode("utf-8")
        request = Request(f"{base_url}/api/chart", payload, {"Content-Type": "application/json"})
        try:
            urlopen(request)
        except HTTPError as error:
            assert error.code == 400
            assert "unknown column 'missing'" in json.loads(error.read())["output"]
        else:
            raise AssertionError("invalid chart columns should be rejected")

        request = Request(f"{base_url}/api/clear", b"{}", {"Content-Type": "application/json"})
        with urlopen(request) as response:
            assert json.loads(response.read())["success"] is True

        payload = json.dumps({"source": "eq Force { F = m * a }\n", "target": "cpp"}).encode("utf-8")
        request = Request(f"{base_url}/api/transpile", payload, {"Content-Type": "application/json"})
        try:
            urlopen(request)
        except HTTPError as error:
            assert error.code == 400
            assert "Cannot transpile" in json.loads(error.read())["output"]
        else:
            raise AssertionError("unsupported code should be rejected by the converter")

        payload = json.dumps({"source": "mass = 150 kg\nmass * 9.81 m/s^2"}).encode("utf-8")
        request = Request(f"{base_url}/api/execute", payload, {"Content-Type": "application/json"})
        with urlopen(request) as response:
            result = json.loads(response.read())
        assert result["success"] is True
        assert result["output"] == "1471.5 N"
        assert result["variables"] == [
            {"name": "ans", "value": "1471.5 N"},
            {"name": "mass", "value": "150 kg"},
        ]

        request = Request(f"{base_url}/api/execute", payload, {"Content-Type": "text/plain"})
        try:
            urlopen(request)
        except HTTPError as error:
            assert error.code == 415
        else:
            raise AssertionError("non-JSON execution requests should be rejected")

        request = Request(f"{base_url}/api/state", headers={"Host": "localhost.evil"})
        try:
            urlopen(request)
        except HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError("non-loopback Host header should be rejected")

        payload = json.dumps({"source": "not executed = 1"}).encode("utf-8")
        request = Request(
            f"{base_url}/api/execute", payload,
            {"Content-Type": "application/json", "Origin": "http://attacker.invalid"},
        )
        try:
            urlopen(request)
        except HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError("cross-origin execution requests should be rejected")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_desktop_ide_embeds_the_local_browser_ide(monkeypatch):
    fake_webview = ModuleType("webview")
    fake_webview.__spec__ = ModuleSpec("webview", loader=None, is_package=True)
    fake_webview.__path__ = []
    errors_module = ModuleType("webview.errors")
    errors_module.__spec__ = ModuleSpec("webview.errors", loader=None)
    state = {}

    def create_window(title, url, **options):
        state["url"] = url
        state["window_options"] = (title, options)

    def start():
        with urlopen(state["url"]) as response:
            page = response.read().decode("utf-8")
        assert response.status == 200 and "F²ORGE" in page
        assert state["window_options"] == (
            "F²ORGE — Engineering IDE",
            {"width": 1360, "height": 900, "min_size": (960, 640)},
        )

    fake_webview.create_window = create_window
    fake_webview.start = start
    errors_module.WebViewException = type("WebViewException", (Exception,), {})
    fake_webview.errors = errors_module
    monkeypatch.setitem(sys.modules, "webview", fake_webview)
    monkeypatch.setitem(sys.modules, "webview.errors", errors_module)
    serve_desktop_ide()


def test_desktop_ide_reports_missing_webview_dependency(monkeypatch):
    monkeypatch.setitem(sys.modules, "webview", None)
    try:
        serve_desktop_ide()
    except ForgeError as error:
        assert error.title == "Cannot start desktop IDE"
        assert 'pip install "f2orge[desktop]"' in error.hint
    else:
        raise AssertionError("desktop IDE should report its missing webview dependency")


def test_desktop_ide_reports_webview_startup_errors(monkeypatch):
    class WebViewException(Exception):
        pass

    fake_webview = ModuleType("webview")
    fake_webview.__spec__ = ModuleSpec("webview", loader=None, is_package=True)
    fake_webview.__path__ = []
    errors_module = ModuleType("webview.errors")
    errors_module.__spec__ = ModuleSpec("webview.errors", loader=None)
    errors_module.WebViewException = WebViewException
    fake_webview.errors = errors_module

    def create_window(*_args, **_kwargs):
        return None

    def start():
        raise WebViewException("no supported runtime")

    fake_webview.create_window = create_window
    fake_webview.start = start
    monkeypatch.setitem(sys.modules, "webview", fake_webview)
    monkeypatch.setitem(sys.modules, "webview.errors", errors_module)
    try:
        serve_desktop_ide()
    except ForgeError as error:
        assert error.title == "Cannot start desktop IDE"
        assert "no supported runtime" in error.message
    else:
        raise AssertionError("desktop IDE should report webview startup errors")
