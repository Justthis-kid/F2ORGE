"""Optimisation and root finding: fminsearch(), linprog(), fzero()."""
from f2orge.errors import ForgeEvalError
from helpers import error_of, run


def test_fminsearch_finds_a_minimum_of_two_variables():
    out = run("def cost(x, y) { return (x - 3)^2 + (y + 1)^2 }\nfminsearch(cost, <0, 0>)")
    x, y = [float(part.split()[0]) for part in out[0].strip("<>").split(", ")]
    assert abs(x - 3) < 1e-4 and abs(y + 1) < 1e-4


def test_fminsearch_keeps_units_through_a_search():
    out = run("def error(d, v) { return (d / 1 m - 5)^2 + (v / 1 m/s - 2)^2 }\n"
              "fminsearch(error, <0 m, 0 m/s>)")
    assert out[0].endswith("m, 2 m/s>") or ("m" in out[0] and "m/s" in out[0])


def test_fminsearch_accepts_a_bare_expression():
    out = run("fminsearch((x - 2)^2 + (y - 3)^2, <0, 0>)")
    x, y = [float(part.split()[0]) for part in out[0].strip("<>").split(", ")]
    assert abs(x - 2) < 1e-4 and abs(y - 3) < 1e-4


def _best(src):
    """The objective value linprog() reports, the number after the solution vector."""
    return float(run(src)[0].rstrip(">").rsplit(", ", 1)[1])


def test_linprog_maximises_by_default():
    # x + y <= 4 and 2x + y <= 6 with 3x + 2y: the corner (2, 2) gives 10.
    assert _best("linprog(<3, 2>, [[1, 1], [2, 1]], <4, 6>)") == 10.0


def test_linprog_reads_bounds_from_the_last_column():
    assert _best("linprog(<3, 2>, [[1, 1, 4], [2, 1, 6]])") == 10.0


def test_linprog_minimises_when_asked():
    # 2x + y under x + y <= 3 with x, y >= 0: the minimum is 0 at the origin, the maximum 6 at (3, 0).
    assert _best('linprog(<2, 1>, [[1, 1]], <3>, "min")') == 0.0
    assert run('linprog(<2, 1>, [[1, 1]], <3>, "max")') == ["<<3, 0>, 6>"]


def test_linprog_rejects_a_bad_direction():
    assert "max" in error_of('linprog(<1, 2>, [[1, 1]], <3>, "up")').message


def test_fzero_accepts_functions_and_expressions():
    assert run("def f(x) { return x^2 - 4 }\nfzero(f, 1 m, 3 m)") == ["2 m"]
    assert run("fzero(x^2 - 4, 1, 3)") == ["2"]
    assert run("fzero(sin(x), 3, 4)")[0].startswith("3.14159")


def test_fzero_reports_a_bracket_without_a_root():
    err = error_of("fzero(x^2 + 1, -1, 1)")
    assert isinstance(err, ForgeEvalError) and "opposite signs" in err.message
