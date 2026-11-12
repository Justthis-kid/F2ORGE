"""Calculus: trapz(), symbolic diff(), and limit()."""
import pytest

from f2orge.errors import ForgeEvalError, UnitError
from helpers import error_of, run


def test_trapz_integrates_sampled_data_with_units():
    assert run("trapz(<0 m, 1 m, 2 m>, <0 N, 5 N, 0 N>)") == ["5 J"]
    assert run("trapz(<0 s, 1 s, 2 s>, <0 m/s, 2 m/s, 4 m/s>)") == ["4 m"]
    assert run("trapz(<0, 1, 2>)") == ["2"]


def test_trapz_needs_matching_lengths_and_units():
    assert "same length" in error_of("trapz(<1, 2>, <1, 2, 3>)").message
    assert isinstance(error_of("trapz(<1 m, 2 s>, <1, 2>)"), UnitError)
    assert "at least two" in error_of("trapz(<1>)").message


@pytest.mark.parametrize("src,expected", [
    ("diff(x^2)", "2 * x"),
    ("diff(sin(x))", "cos(x)"),
    ("diff(cos(x))", "-sin(x)"),
    ("diff(exp(x))", "exp(x)"),
    ("diff(ln(x))", "1 / x"),
    ("diff(sqrt(x))", "1 / (2 * sqrt(x))"),
    ("diff(x^3 + 2*x)", "3 * x^2 + 2"),
    ("diff(x * sin(x))", "sin(x) + x * cos(x)"),
])
def test_symbolic_differentiation(src, expected):
    assert run(src) == [expected]


def test_diff_keeps_its_numeric_meaning_for_vectors():
    assert run("diff(<1, 4, 9>)") == ["<3, 5>"]


@pytest.mark.parametrize("src,expected", [
    ("limit(sin(x)/x, 0)", "1"),
    ("limit((1 - cos(x)) / x^2, 0)", "0.5"),
    ("limit((x^2 - 1) / (x - 1), 1)", "2"),
    ("limit(x^2 + 1, 3)", "10"),
    ("limit(x, 2)", "2"),
])
def test_limits(src, expected):
    assert run(src) == [expected]


def test_a_limit_that_does_not_exist_is_reported():
    err = error_of("limit(1 / x, 0)")
    assert isinstance(err, ForgeEvalError) and "does not exist" in err.message
