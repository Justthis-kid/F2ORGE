"""solveODE(): numerical integration of ordinary differential equations."""
from helpers import TempDir, error_of, forge, run

FALL = """def accel(t, v) { return -9.81 m/s^2 }
fall = solveODE(accel, 20 m/s, 0 s, 4 s)
"""


def test_free_fall_matches_the_analytic_solution():
    out = run(FALL + "n = count(fall[1])\nfall[1][n - 1]\nfall[0][n - 1]\nfall[1][0]")
    assert out[0] == "-19.24 m/s"  # 20 - 9.81 * 4
    assert out[1] == "4 s"
    assert out[2] == "20 m/s"


def test_the_solution_is_dense_enough_to_plot():
    assert int(run(FALL + "count(fall[0])")[0]) >= 100


def test_exponential_decay():
    out = run("def dv(t, v) { return -0.5 1/s * v }\nr = solveODE(dv, 10 m/s, 0 s, 2 s)\n"
              "n = count(r[1])\nr[1][n - 1]")
    assert out[0].startswith("3.678794")  # 10 * e^-1


def test_a_bare_expression_is_the_derivative():
    out = run("fall = solveODE(4 m/s^2, 0 m/s, 0 s, 2 s)\nn = count(fall[1])\nfall[1][n - 1]")
    assert out == ["8 m/s"]


def test_inverse_units_are_written_directly():
    assert run("0.5 1/s") == ["0.5 1/s"]
    assert run("5 1/(m*s)") == ["5 1/(m*s)"]
    assert run("0.5 1/s * 10 m/s") == ["5 m/s²"]


def test_a_solution_can_be_plotted_with_named_axes():
    out = run(FALL + "plot(fall[0], fall[1])")[0]
    assert out.startswith("Plot: fall[1] (m/s) vs fall[0] (s)")


def test_solveODE_reports_bad_arguments():
    assert "start and end times" in error_of("solveODE(-1, 0 m, 0 s, 1 m)").message
    assert "end time different" in error_of("solveODE(-1, 0, 0 s, 0 s)").message
    assert "derivative in" in error_of(
        "def bad(t, v) { return 1 N }\nr = solveODE(bad, 10 m/s, 0 s, 1 s)").message


PLATE = """grid = [[100 C, 100 C, 100 C, 100 C, 100 C],
        [0 C, 0 C, 0 C, 0 C, 0 C],
        [0 C, 0 C, 0 C, 0 C, 0 C],
        [0 C, 0 C, 0 C, 0 C, 0 C],
        [0 C, 0 C, 0 C, 0 C, 0 C]]
steady = solvePDE(grid)
"""


def test_solvePDE_relaxes_a_plate_to_its_steady_temperature():
    # A 100 C left edge and 0 C elsewhere: the midpoint of an n-cell plate is 100 * 4/16 = 25 C.
    assert run(PLATE + "steady[2][2]") == ["25 C"]
    assert run(PLATE + "steady[0][0]") == ["100 C"]      # the edge holds its value
    assert run(PLATE + "steady[4][4]") == ["0 C"]


def test_a_steady_field_plots_as_a_heatmap():
    assert "Heatmap" in run(PLATE + 'plot(steady, kind = "heatmap")')[0]


def test_solvePDE_needs_a_square_matrix():
    assert "square grid" in error_of("solvePDE([[1, 2, 3], [4, 5, 6]])").message
    assert "square matrix" in error_of("solvePDE(<1, 2>)").message


def test_write_a_course_diagram_from_a_solution():
    with TempDir() as d:
        (d / "fall.forge").write_text(
            "def accel(t, v) { return -9.81 m/s^2 }\n"
            'fall = solveODE(accel, 20 m/s, 0 s, 4 s)\n'
            'plot(fall[0], fall[1])\n', encoding="utf-8")
        result = forge("run", str(d / "fall.forge"))
        assert result.returncode == 0
        assert (d / "fall-plot.svg").is_file()
