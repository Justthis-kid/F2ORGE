"""solvePDE(): steady-state fields on a grid."""
from helpers import error_of, run

PLATE = """grid = [[100 degC, 100 degC, 100 degC, 100 degC, 100 degC],
        [0 degC, 0 degC, 0 degC, 0 degC, 0 degC],
        [0 degC, 0 degC, 0 degC, 0 degC, 0 degC],
        [0 degC, 0 degC, 0 degC, 0 degC, 0 degC],
        [0 degC, 0 degC, 0 degC, 0 degC, 0 degC]]
steady = solvePDE(grid)
"""


def test_a_heated_edge_relaxes_into_a_steady_field():
    out = run(PLATE + "steady[2][2]")
    assert out == ["25 °C"]  # a plate held at 100 °C along one edge, solved on the interior


def test_edge_values_are_the_boundary_conditions():
    out = run(PLATE + "steady[0][0]\nsteady[4][4]")
    assert out == ["100 °C", "0 °C"]


def test_the_field_falls_away_from_the_heated_edge():
    values = run(PLATE + "steady[1][1]\nsteady[2][1]\nsteady[3][1]")
    numbers = [float(value.split()[0]) for value in values]
    assert numbers[0] > numbers[1] > numbers[2] > 0


def test_a_uniform_plate_stays_uniform():
    out = run("grid = [[5 m, 5 m, 5 m], [5 m, 5 m, 5 m], [5 m, 5 m, 5 m]]\n"
              "solvePDE(grid)[1][1]")
    assert out == ["5 m"]


def test_the_result_plots_as_a_heatmap():
    out = run("grid = [[9 V, 9 V, 9 V], [0 V, 0 V, 0 V], [0 V, 0 V, 0 V]]\n"
              'plot(solvePDE(grid), kind = "heatmap")')
    assert out[0].startswith("Plot: Heatmap")


def test_solvePDE_checks_its_grid():
    assert "square grid" in error_of("solvePDE([[1, 2, 3], [4, 5, 6]])").message
    assert "at least 3 cells" in error_of("solvePDE([[1, 2], [3, 4]])").message
    assert "square matrix" in error_of("solvePDE(1)").message
