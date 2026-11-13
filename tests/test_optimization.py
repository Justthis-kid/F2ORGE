"""fminsearch() for several variables and linprog() for linear programs."""
from helpers import error_of, run


def test_fminsearch_minimises_over_several_variables():
    assert run("def cost(x, y) { return (x - 3)^2 + (y + 1)^2 }\nfminsearch(cost, <0, 0>)") == ["<3, -1>"]
    assert run("fminsearch((x - 3)^2 + (y - 1)^2, <0, 0>)") == ["<3, 1>"]
    assert run("fminsearch((x - 2)^2 + 1, <0>)") == ["<2>"]


def test_fminsearch_keeps_units_through_the_cost():
    out = run("def cost(d, v) { return (d / 1 m - 5)^2 + (v / 1 m/s - 2)^2 }\n"
              "fminsearch(cost, <0 m, 0 m/s>)")
    assert out == ["<5 m, 2 m/s>"]


def test_fminsearch_reports_a_cost_with_units():
    err = error_of("def cost(x, y) { return x^2 * 1 m }\nfminsearch(cost, <0, 0>)")
    assert "no unit" in err.message


def test_linprog_maximises_a_linear_objective():
    assert run("linprog(<3, 2>, [[1, 1], [2, 1]], <4, 6>)") == ["<<2, 2>, 10>"]


def test_linprog_reads_an_augmented_matrix_and_a_minimum():
    assert run("linprog(<3, 2>, [[1, 1, 4], [2, 1, 6]])") == ["<<2, 2>, 10>"]
    assert run('linprog(<1, 2>, [[1, 1]], <3>, "min")') == ["<<0, 0>, 0>"]


def test_linprog_rejects_problems_it_cannot_solve():
    assert "unbounded" in error_of("linprog(<1, 0>, [[-1, 1]], <1>)").message
    assert "non-negative" in error_of("linprog(<1>, [[1]], <-1>)").message
