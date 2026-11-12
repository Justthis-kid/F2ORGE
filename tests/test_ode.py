"""dsolve(): numerical integration of ordinary differential equations."""
from helpers import TempDir, error_of, forge, run

FALL = """def accel(t, v) { return -9.81 m/s^2 }
fall = dsolve(accel, 20 m/s, 0 s, 4 s)
"""


def test_free_fall_matches_the_analytic_solution():
    out = run(FALL + "n = count(fall[1])\nfall[1][n - 1]\nfall[0][n - 1]\nfall[1][0]")
    assert out[0] == "-19.24 m/s"  # 20 - 9.81 * 4
    assert out[1] == "4 s"
    assert out[2] == "20 m/s"


def test_the_solution_is_dense_enough_to_plot():
    assert int(run(FALL + "count(fall[0])")[0]) >= 100


def test_exponential_decay():
    out = run("def dv(t, v) { return -0.5 1/s * v }\nr = dsolve(dv, 10 m/s, 0 s, 2 s)\n"
              "n = count(r[1])\nr[1][n - 1]")
    assert out[0].startswith("3.678794")  # 10 * e^-1


def test_a_bare_expression_is_the_derivative():
    out = run("fall = dsolve(4 m/s^2, 0 m/s, 0 s, 2 s)\nn = count(fall[1])\nfall[1][n - 1]")
    assert out == ["8 m/s"]


def test_inverse_units_are_written_directly():
    assert run("0.5 1/s") == ["0.5 1/s"]
    assert run("5 1/(m*s)") == ["5 1/(m*s)"]
    assert run("0.5 1/s * 10 m/s") == ["5 m/s²"]


def test_a_solution_can_be_plotted():
    assert run(FALL + "plot(fall[0], fall[1])")[0].startswith("Plot:")


def test_dsolve_reports_bad_arguments():
    assert "start and end times" in error_of("dsolve(-1, 0 m, 0 s, 1 m)").message
    assert "end time different" in error_of("dsolve(-1, 0, 0 s, 0 s)").message


def test_write_a_course_diagram_from_a_solution():
    with TempDir() as d:
        (d / "fall.forge").write_text(
            "def accel(t, v) { return -9.81 m/s^2 }\n"
            'fall = dsolve(accel, 20 m/s, 0 s, 4 s)\n'
            'plot(fall[0], fall[1])\n', encoding="utf-8")
        result = forge("run", str(d / "fall.forge"))
        assert result.returncode == 0
        assert (d / "fall-plot.svg").is_file()
