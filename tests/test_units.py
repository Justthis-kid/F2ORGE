import math

import pytest

from f2orge.dimensions import Dim, describe_full
from f2orge.errors import ForgeError, UnitError
from f2orge.quantity import Quantity
from f2orge.units import Unit, all_unit_names, lookup_unit, units_by_kind
from helpers import error_of, run, run_it


@pytest.mark.parametrize("src,expected", [
    ("convert 10 ft -> m", "3.048 m"),
    ("convert 1 mi -> km", "1.609344 km"),
    ("convert 1 atm -> kPa", "101.325 kPa"),
    ("convert 1 psi -> Pa", "6894.757293 Pa"),
    ("convert 1 kWh -> MJ", "3.6 MJ"),
    ("convert 60 mph -> m/s", "26.8224 m/s"),
    ("convert 1 hp -> W", "745.6998716 W"),
    ("convert 1 L -> m^3", "0.001 m³"),
    ("convert 1 gal -> L", "3.785411784 L"),
    ("convert 180 deg -> rad", "3.141592654 rad"),
    ("convert 1 N -> kg*m/s^2", "1 kg*m/s²"),
    ("convert 1 lb -> g", "453.59237 g"),
    ("convert 1 BTU -> J", "1055.055853 J"),
    ("convert 100 kn -> m/s", "51.44444444 m/s"),
])
def test_conversions(src, expected):
    assert run(src) == [expected]


@pytest.mark.parametrize("src,expected", [
    ("convert 25 degC -> K", "298.15 K"),
    ("convert 300 K -> degC", "26.85 °C"),
    ("convert 32 degF -> degC", "0 °C"),
    ("convert 212 degF -> degC", "100 °C"),
    ("convert 0 degC -> degF", "32 °F"),
    ("convert -40 degC -> degF", "-40 °F"),
    ("(30 degC) - (20 degC)", "10 K"),
    ("20 degC + 5 K", "25 °C"),
])
def test_temperature_scales_are_affine_but_differences_are_not(src, expected):
    assert run(src) == [expected]


@pytest.mark.parametrize("src,expected", [
    ("150 kg * 9.81 m/s^2", "1471.5 N"),
    ("2 N * 3 m", "6 J"),
    ("10 J / 2 s", "5 W"),
    ("5 V / 2 A", "2.5 Ω"),
    ("100 N / 2 m^2", "50 Pa"),
    ("3 m / 2 s", "1.5 m/s"),
    ("10 m / 2 s^2", "5 m/s²"),
    ("1 / 2 s", "0.5 1/s"),
    ("3 A * 2 s", "6 C"),
])
def test_results_simplify_to_named_si_units(src, expected):
    assert run(src) == [expected]


@pytest.mark.parametrize("src,expected", [
    ("2 * 5 ft", "10 ft"), ("5 ft / 2", "2.5 ft"), ("10 kN + 500 N", "10.5 kN"),
    ("30 deg * 2", "60 deg"), ("-(3 m)", "-3 m"),
])
def test_display_unit_survives_scaling_by_plain_numbers(src, expected):
    assert run(src) == [expected]


@pytest.mark.parametrize("src,needles", [
    ("10 kg + 5 m", ["add", "mass (kg)", "length (m)"]),
    ("5 m - 2 s", ["subtract", "time (s)", "length (m)"]),
    ("convert 5 m -> s", ["convert", "length (m)", "time (s)"]),
    ("20 degC + 30 degC", ["two absolute temperatures"]),
    ("2 ^ (3 m)", ["exponent", "length (m)"]),
    ("(3 m)^0.3333", ["cannot raise"]),
    ("sin(5 kg)", ["sin()", "mass (kg)"]),
    ("ln(5 m)", ["ln()", "length (m)"]),
    ("atan2(1 m, 1 s)", ["atan2()"]),
    ("min(1 m, 2 s)", ["min()"]),
])
def test_unit_safety_errors(src, needles):
    err = error_of(src)
    assert isinstance(err, UnitError)
    for needle in needles:
        assert needle in err.message


def test_fractional_powers_of_units():
    assert run("(8 m^3)^(1/3)") == ["2 m"]
    assert run("sqrt(9 m^2/s^2)") == ["3 m/s"]
    assert run("(2 m)^3") == ["8 m³"]


def test_unknown_unit_suggests_close_matches():
    err = error_of("x = 5 secs")
    assert err.title == "Unknown unit" and "'sec'" in err.hint
    err = error_of("x = 2 pi")
    assert "write 2 * pi" in err.hint


def test_unit_names_are_found_exactly_before_prefix_splitting():
    assert lookup_unit("min").scale == 60.0            # the minute, not milli-inch
    assert lookup_unit("mm").scale == pytest.approx(1e-3)
    assert lookup_unit("kg").scale == 1.0              # k + g, with g defined as 1e-3 kg
    assert lookup_unit("MPa").scale == pytest.approx(1e6)
    assert lookup_unit("µm") is not None and lookup_unit("um") is not None
    assert lookup_unit("Ω") is lookup_unit("ohm") or lookup_unit("Ω").dim == lookup_unit("ohm").dim
    assert lookup_unit("foo") is None and lookup_unit("pt") is None


def test_every_registered_unit_round_trips():
    for kind, defs in units_by_kind().items():
        for d in defs:
            unit = Unit.from_atoms([(d.name, 1)])
            for number in (1.0, -3.5, 1234.5678):
                q = Quantity.from_unit(number, unit)
                assert q.magnitude(unit) == pytest.approx(number, rel=1e-12, abs=1e-12), d.name
                assert q.dim == d.dim


def test_dimension_algebra():
    L, T = Dim.of(L=1), Dim.of(T=1)
    assert (L / T) / T == Dim.of(L=1, T=-2)
    assert (L ** 2) ** 0.5 == L
    assert Dim.of(L=3) ** (1 / 3) == L if False else (Dim.of(L=3) ** __import__("fractions").Fraction(1, 3)) == L
    assert describe_full(Dim.of(L=1, M=1, T=-2)) == "force (N)"
    assert describe_full(Dim.of(L=5)).startswith("a quantity measured in")


def test_literals_forms_are_equivalent():
    assert run("9.81 m/s²") == run("9.81 m/s^2") == ["9.81 m/s²"]
    assert run("5 s^-2") == run("5 s⁻²") == ["5 1/s²"]
    assert run("5 W/(m*K)") == ["5 W/(m*K)"] or run("5 W/(m*K)")[0].startswith("5 W/")
    assert run("1_000 m") == ["1000 m"]
    assert run("1e-3 m") == ["0.001 m"]
    assert run("10 m / 2 s") == ["5 m/s"]          # a spaced / divides two quantities
    assert run("5 m*3") == ["15 m"]                 # an adjacent * followed by a number is multiplication


def test_unit_attached_to_a_variable_is_a_helpful_error():
    err = error_of("y = 10 m / s")
    assert "'s' is a unit" in err.hint


def test_ascii_mode_for_limited_terminals():
    from f2orge import units
    units.set_ascii(True)
    try:
        assert run("9.81 m/s^2 * 1 s") == ["9.81 m/s"]
        assert run("convert 1 N -> kg*m/s^2") == ["1 kg*m/s^2"]
    finally:
        units.set_ascii(False)


def test_negative_temperatures_and_negation():
    assert run("convert -40 degC -> degF") == ["-40 °F"]
    assert run("convert -40 degF -> degC") == ["-40 °C"]
    assert run("convert -273.15 degC -> K") == ["0 K"]
    err = error_of("T = 25 degC\n-T")
    assert "negate an absolute temperature" in err.message
    assert run("-(3 m)") == ["-3 m"] and run("-(2 + 3)") == ["-5"]


def test_printer_keeps_negative_literals_safe_as_pow_bases():
    from f2orge.parser import parse_text
    from f2orge.printer import format_expr
    st = parse_text("(-2)^2")[0]
    assert format_expr(st.expr) == "(-2)^2"
    assert run("(-2)^2") == ["4"] and run("-2^2") == ["-4"]
