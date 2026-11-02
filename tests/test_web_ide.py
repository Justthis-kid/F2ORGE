import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from f2orge.desktop import DesktopSession
from f2orge.web_ide import _LoopbackServer, _handler


def test_browser_ide_serves_offline_assets_and_local_kernel():
    server = _LoopbackServer(("127.0.0.1", 0), _handler(DesktopSession()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(f"{base_url}/") as response:
            page = response.read().decode("utf-8")
            assert response.status == 200 and "F²ORGE" in page
            assert response.headers["Content-Security-Policy"]
        with urlopen(f"{base_url}/app.css") as response:
            styles = response.read().decode("utf-8")
            assert response.status == 200 and "body.dark" in styles
            assert "fonts.googleapis.com" not in styles
            assert "--accent: #dd7a35" in styles
            assert "--panel: #fcfaf5" in styles
            assert "--page: #111214" in styles
        with urlopen(f"{base_url}/app.js") as response:
            script = response.read().decode("utf-8")
            assert response.status == 200 and "function compileGraph()" in script
            assert "https://" not in script
            assert "Shared variables create a circular dependency" in script
            assert 'node.kind === "Script"' in script
            assert "function startResize" in script
            assert "Share this variable?" in script

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
