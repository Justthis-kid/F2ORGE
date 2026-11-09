import pytest

from f2orge.desktop import DesktopSession
from f2orge.errors import ForgeError
from f2orge.interpreter import Interpreter
from helpers import TempDir, forge, run


def test_plot_statement_records_series_with_units():
    plots = []
    interp = Interpreter(out=lambda _line: None,
                         plotter=lambda title, x, y, points: plots.append((title, x, y, points)))
    interp.run("t = linspace(0 s, 2 s, 3)\nv = 3 m/s * t\nplot(t, v)\n", "plot.forge")
    assert plots == [("v (m) vs t (s)", "t (s)", "v (m)", [(0.0, 0.0), (1.0, 3.0), (2.0, 6.0)])]
    assert interp.plots[0]["title"] == "v (m) vs t (s)"


def test_plot_statement_without_x_uses_sample_index():
    plots = []
    interp = Interpreter(out=lambda _line: None,
                         plotter=lambda title, x, y, points: plots.append((title, x, y, points)))
    interp.run("v = <1 m, 2 m, 4 m>\nplot(v)\n", "plot.forge")
    assert plots == [("v (m) vs Index", "Index", "v (m)", [(1, 1.0), (2, 2.0), (3, 4.0)])]


def test_plot_statement_prints_a_summary_without_a_plotter():
    assert run("v = <1 m, 2 m>\nplot(v)\n") == ["Plot: v (m) vs Index (2 points)"]


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("plot(3 m)\n", "needs a vector"),
        ("plot(<1, 2>, <1, 2, 3>)\n", "same length"),
        ("plot(<1 m, 2 s>, <1 m, 2 m>)\n", "matching units"),
        ("plot(<1 m>)\n", "at least two points"),
    ],
)
def test_plot_statement_reports_invalid_data(source, message):
    with pytest.raises(ForgeError, match=message) as caught:
        run(source)
    assert caught.value.title == "Cannot plot"


def test_desktop_session_collects_plots_from_a_run():
    session = DesktopSession()
    output, success = session.execute("v = <1 m, 2 m>\nplot(v)")
    assert success and output == ""
    assert session.plots[0]["points"] == [(1, 1.0), (2, 2.0)]
    session.clear()
    assert session.plots == []


def test_run_command_writes_a_graph_for_each_plot_statement():
    with TempDir() as directory:
        program = directory / "motion.forge"
        program.write_text("t = linspace(0 s, 1 s, 3)\nplot(t, 2 m/s * t)\nplot(t)\n", encoding="utf-8")
        result = forge("run", str(program), "--plot-format", "html")
        assert result.returncode == 0, result.stderr
        first = directory / "motion-plot-1.html"
        second = directory / "motion-plot-2.html"
        assert first.is_file() and second.is_file()
        assert "<svg" in first.read_text(encoding="utf-8")
        assert "Wrote" in result.stdout
