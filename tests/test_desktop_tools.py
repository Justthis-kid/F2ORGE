import sys
from types import ModuleType

from f2orge.desktop_tools import show_html_window


def test_native_tool_window_embeds_offline_html(monkeypatch):
    state = {}
    fake_webview = ModuleType("webview")
    errors = ModuleType("webview.errors")
    errors.WebViewException = type("WebViewException", (Exception,), {})
    fake_webview.errors = errors
    fake_webview.create_window = lambda title, **kwargs: state.update(title=title, **kwargs)
    fake_webview.start = lambda: state.update(started=True)
    monkeypatch.setitem(sys.modules, "webview", fake_webview)
    monkeypatch.setitem(sys.modules, "webview.errors", errors)

    show_html_window("Force calculator", "<html>offline</html>")

    assert state == {
        "title": "Force calculator",
        "html": "<html>offline</html>",
        "width": 1024,
        "height": 760,
        "min_size": (640, 480),
        "started": True,
    }
