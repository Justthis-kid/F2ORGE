"""`forge ide` must open an IDE on every machine, even without the optional webview."""
import pytest

from f2orge import cli
from f2orge.errors import ForgeError
from helpers import forge


def test_ide_offers_a_choice_of_interfaces():
    parser = cli.build_parser()
    args = parser.parse_args(["ide"])
    assert args.ui == "auto"
    for choice in ("auto", "webview", "tk", "browser"):
        assert parser.parse_args(["ide", "--ui", choice]).ui == choice


def test_auto_falls_back_to_the_tkinter_editor_when_the_webview_is_missing(monkeypatch, capsys):
    import f2orge.desktop
    import f2orge.web_ide

    opened = []

    def no_webview():
        raise ForgeError("the desktop webview is not installed", title="Cannot start desktop IDE")

    monkeypatch.setattr(f2orge.web_ide, "serve_desktop_ide", no_webview)
    monkeypatch.setattr(f2orge.desktop, "launch_desktop_ide", lambda: opened.append("tk"))

    assert cli.main(["ide"]) == 0
    assert opened == ["tk"]
    assert "trying the Tkinter editor" in capsys.readouterr().err


def test_auto_opens_the_browser_ide_when_neither_window_can_start(monkeypatch):
    import f2orge.desktop
    import f2orge.web_ide

    used = []

    def unavailable():
        raise ForgeError("no window here", title="Cannot start desktop IDE")

    monkeypatch.setattr(f2orge.web_ide, "serve_desktop_ide", unavailable)
    monkeypatch.setattr(f2orge.desktop, "launch_desktop_ide", unavailable)
    monkeypatch.setattr(f2orge.web_ide, "serve_browser_ide", lambda: used.append("browser"))

    assert cli.main(["ide"]) == 0
    assert used == ["browser"]


def test_an_explicit_ui_does_not_fall_back(monkeypatch, capsys):
    import f2orge.web_ide

    def no_webview():
        raise ForgeError("the desktop webview is not installed", title="Cannot start desktop IDE")

    monkeypatch.setattr(f2orge.web_ide, "serve_desktop_ide", no_webview)
    assert cli.main(["ide", "--ui", "webview"]) == 1
    assert "Cannot start desktop IDE" in capsys.readouterr().err


def test_the_tkinter_ide_has_the_new_nodes_and_commands():
    import inspect

    import f2orge.desktop

    source = inspect.getsource(f2orge.desktop.launch_desktop_ide)
    for feature in ('"Call"', '"Compare"', '"Output2"', '":trace"', '":profile"'):
        assert feature in source, feature


def test_ide_help_describes_the_fallback():
    r = forge("ide", "--help")
    assert r.returncode == 0
    assert "webview" in r.stdout and "Tkinter" in r.stdout
