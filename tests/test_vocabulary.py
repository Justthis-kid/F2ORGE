"""Tests for the newer vocabulary: complex numbers, cross products, calculus, statistics, units."""
import pytest

from f2orge.errors import ForgeError, UnitError
from helpers import error_of, run


@pytest.mark.parametrize("src,expected", [
    ("cross(<1, 0, 0>, <0, 1, 0>)", "<0, 0, 1>"),
    ("cross(<2 m, 0 m, 0 m>, <0 N, 3 N, 0 N>)", "<0 J, 0 J, 6 J>"),
    ("sqrt(-1)", "i"),
    ("sqrt(-9 m^2)", "3i m"),
    ("abs(3 + 4i)", "5"),
    ("conj(3 + 4i)", "3 - 4i"),
    ("imag(3 + 4i)", "4"),
    ("db(100)", "20 dB"),
    ("dbm(1 W)", "30 dBm"),
    ("convert 3000 rpm -> rad/s", "314.1592654 rad/s"),
    ("pH(1e-7 mol/L)", "7"),
    ("fromPH(7)", "1e-07 mol/L"),
])
def test_newer_vocabulary(src, expected):
    assert run(src) == [expected]


def test_complex_quantities_keep_their_units():
    assert run("Z = 3 ohm + 4i ohm\nabs(Z)\narg(Z)")[0] == "5 Ω"
    assert run("Z = 3 ohm + 4i ohm\nconj(Z)") == ["3 Ω - 4i Ω"]


def test_statistics_functions():
    assert run("std(<2, 4, 4, 4, 5, 5, 7, 9>)")[0].startswith("2.13808")
    assert run("pstd(<2, 4, 4, 4, 5, 5, 7, 9>)")[0].startswith("2")
    assert run("median(<3, 1, 2>)") == ["2"]
    assert run("percentile(<1, 2, 3, 4, 5>, 75)") == ["4"]
    assert run("percentile(<1, 2, 3, 4, 5>, 0.75)") == ["4"]
    assert run("linreg(<1, 2, 3>, <2, 4, 7>)")[0].startswith("<2.5, -0.666")


def test_calculus_functions_accept_functions_and_expressions():
    assert run("integrate(x^2, 0 m, 1 m)")[0].startswith("0.3333")
    assert run("def f(x) { return x^2 }\nintegrate(f, 0 m, 1 m)")[0].startswith("0.3333")
    assert run("derivative(x^2, 2)") == ["4"]
    assert run("fzero(x^2 - 4, 0, 10)") == ["2"]
    assert run("minimize(x^2 + 1, -5, 5)")[0].startswith("<") and run("minimize(x^2 + 1, -5, 5)")[0].endswith(", 1>")
    assert run("surface(x*y, <1, 2>, <3, 4>)") == ["[[3, 6], [4, 8]]"]


def test_indexing_is_zero_based_and_supports_slices():
    assert run("v = <10, 20, 30>\nv[1]") == ["20"]
    assert run("v = <10, 20, 30>\nv[0:2]") == ["<10, 20>"]
    assert run("M = [[1, 2], [3, 4]]\nM[:, 0]") == ["[[1], [3]]"]
    assert run("M = [[1, 2], [3, 4]]\nM[0:2, 0]") == ["[[1], [3]]"]
    assert run("M = [[1, 2]]\nM.T") == ["[[1], [2]]"]


def test_linear_system_helper_and_determinant():
    assert run("det([[1, 2], [3, 4]])") == ["-2"]
    assert run("solve_system([[1, 1], [1, -1]], <10, 2>)") == ["<6, 4>"]
    assert run("inverse([[2 m, 0 m], [0 m, 4 m]])") == ["[[0.5 1/m, 0 1/m], [0 1/m, 0.25 1/m]]"]


def test_logarithmic_and_angular_units_are_their_own_kind():
    assert run("1 rad/s")[0].endswith("rad/s")
    assert run("1 / 1 s")[0].endswith("1/s")
    with pytest.raises(ForgeError):
        run("1 rad/s + 1 Hz")
    with pytest.raises(UnitError):
        run("db(100) + 1")


def test_pH_reports_a_concentration_in_molars():
    assert run("pH(0.01 mol/L)") == ["2"]
    assert run("fromPH(2)") == ["0.01 mol/L"]


# ---- magnitude comparisons -------------------------------------------------------------------
@pytest.mark.parametrize("src,expected", [
    ("compare_mag(3, 2 m)", "1"),
    ("compare_mag(2 m, 3)", "-1"),
    ("compare_mag(1 m, 1 m)", "0"),
    ("compare_mag(2 km, 1500 m)", "1"),      # units are converted before sizes are compared
    ("less_mag(3, 2 m)", "false"),
    ("less_equal_mag(2 m, 2)", "true"),
    ("greater_mag(5 s, 3 kg)", "true"),
    ("greater_equal_mag(1, 1)", "true"),
    ("compare_mag(3 + 4i, 4 + 3i)", "0"),    # complex values compare by magnitude
])
def test_magnitude_comparisons_ignore_units(src, expected):
    assert run(src) == [expected]


def test_plain_comparisons_still_check_units():
    err = error_of("3 < 2 m")
    assert isinstance(err, UnitError) and "cannot compare" in err.message
