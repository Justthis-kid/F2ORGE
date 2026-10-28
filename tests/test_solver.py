import math

import pytest

from f2orge.errors import ForgeEvalError, SolveError, UnitError
from f2orge.solver import isolate, rearrangements
from helpers import error_of, run, run_it


def solve_value(relation, target, givens, decls=""):
    src = f"eq T {{ {decls} {relation} }}\nsolve T for {target} {{ {givens} }}"
    it, _ = run_it(src)
    return it.variables["ans"].value


@pytest.mark.parametrize("relation,target,givens,expected", [
    ("y = a + b", "a", "y = 10; b = 4", 6.0),
    ("y = a - b", "b", "y = 10; a = 15", 5.0),
    ("y = b - a", "a", "y = 10; b = 15", 5.0),
    ("y = a * b", "a", "y = 12; b = 4", 3.0),
    ("y = a / b", "b", "y = 3; a = 12", 4.0),
    ("y = b / a", "a", "y = 3; b = 12", 4.0),
    ("y = a ^ 3", "a", "y = 27", 3.0),
    ("y = 2 ^ a", "a", "y = 32", 5.0),
    ("y = sqrt(a)", "a", "y = 4", 16.0),
    ("y = ln(a)", "a", "y = 1", math.e),
    ("y = exp(a)", "a", "y = e", 1.0),
    ("y = log(a)", "a", "y = 2", 100.0),
    ("y = sin(a)", "a", "y = 0.5", math.pi / 6),
    ("y = cos(a)", "a", "y = 0.5", math.pi / 3),
    ("y = tan(a)", "a", "y = 1", math.pi / 4),
    ("y = -a", "a", "y = 5", -5.0),
    ("y = (a + 1) * 2", "a", "y = 10", 4.0),
    ("y = 3 * a^2 + 1", "a", "y = 13", 2.0),
    ("a / b = c / d", "d", "a = 1; b = 2; c = 6", 12.0),
])
def test_rearrangement_of_every_operation(relation, target, givens, expected):
    assert solve_value(relation, target, givens) == pytest.approx(expected, rel=1e-12)


def test_the_spec_example():
    assert run("eq Force { F = m * a }\nsolve Force for a {\n    F = 100 N\n    m = 50 kg\n}") == ["a = 2 m/s²"]


def test_units_come_out_right_by_construction():
    out = run("import KineticEnergy\nsolve KineticEnergy for v { KE = 18 J\n m = 4 kg }")
    assert out[0] == "v = 3 m/s"
    out = run("import Lift\nsolve Lift for S { L = 34.3 N\n rho = 1.225 kg/m^3\n V = 16 m/s\n CL = 1.3 }")
    assert out[0].startswith("S = 0.1682") and out[0].endswith(" m²")  # 34.3 / (0.5 * 1.225 * 16^2 * 1.3)
    # an equation without declarations still gets named SI units
    assert run("eq P { P = F / A }\nsolve P for F { P = 2 kPa\n A = 3 m^2 }") == ["F = 6000 N"]


def test_dimension_mismatch_in_known_values_is_reported():
    err = error_of("import Force\nsolve Force for a { F = 100 N\n m = 50 s }")
    assert isinstance(err, UnitError) and "expects mass (kg)" in err.message
    err = error_of("eq T { y = a + b }\nsolve T for a { y = 5 m\n b = 2 s }")
    assert isinstance(err, UnitError) and "cannot" in err.message


def test_solving_through_a_chain_of_relations():
    it, out = run_it("eq Chain {\n x : m\n y = 2 * x\n z = y + 1 m\n}\nsolve Chain for x { z = 11 m }")
    assert out == ["x = 5 m"]
    it.explain = True
    out = []
    it.out = out.append
    it.run("solve Chain for x { z = 11 m }", "t.forge")
    assert "  rearranged: y = z - 1 m" in out and "  rearranged: x = y / 2" in out


def test_insufficient_information_names_what_is_missing():
    err = error_of("eq Force { F = m * a }\nsolve Force for F { }")
    assert isinstance(err, SolveError) and "m, a are unknown" in err.message
    err = error_of("eq Force { F = m * a }\nsolve Force for F { m = 2 kg }")
    assert "a is unknown" in err.message and "value for a" in err.hint
    assert "has no variable named 'q'" in error_of("eq Force { F = m * a }\nsolve Force for q { }").message
    assert "Did you mean 'm'" in error_of("eq Force { F = m * a }\nsolve Force for mm { }").hint
    assert "nothing to solve for" in error_of("eq Force { F = m * a }\nsolve Force for F { F = 1 N }").message
    assert "no variable named 'zz'" in error_of("eq Force { F = m * a }\nsolve Force for F { zz = 1 N }").message
    assert "no equation named 'Nope'" in error_of("solve Nope for x { }").message


def test_numeric_fallback_when_the_unknown_appears_twice():
    it, out = run_it("eq Q { t : dimensionless\n t + t^2 = 6 }\nsolve Q for t { }")
    assert out[0] == "t = 2"
    assert any("other solutions: -3" in line for line in out)
    # a unit-bearing example: x + x^2/(1 m) = 6 m  ->  x = 2 m
    out = run("eq M { x : m\n x + x^2 / 1 m = 6 m }\nsolve M for x { }")
    assert out[0] == "x = 2 m"


def test_numeric_fallback_requires_a_declared_unit_and_reports_no_solution():
    err = error_of("eq Q { t + t^2 = 6 }\nsolve Q for t { }")
    assert isinstance(err, SolveError) and "more than once" in err.message and "t : m" in err.hint
    err = error_of("eq P { t : dimensionless\n t + 1 / t = 1 }\nsolve P for t { }")
    assert isinstance(err, SolveError) and "no solution" in err.message  # the pole at t = 0 is not a root


def test_root_of_even_powers_and_domain_errors():
    out = run("eq S { L : m\n L^2 = 9 m^2 }\nsolve S for L { }")
    assert out[0] == "L = 3 m" and "negative solution" in out[1]
    assert isinstance(error_of("eq S { y = x^2 }\nsolve S for x { y = -4 }"), ForgeEvalError)


def test_declared_output_unit_is_applied_to_solutions():
    out = run("eq T { d : km\n t : h\n v : km/h\n v = d / t }\nsolve T for d { v = 90 km/h\n t = 2 h }")
    assert out == ["d = 180 km"]
    out = run("eq G { P : Pa\n V : m^3\n n : mol\n T : K\n P = n * R * T / V }\n"
              "solve G for T { P = 101325 Pa\n V = 22.414 L\n n = 1 mol }")
    assert out[0].startswith("T = 273.1") and out[0].endswith(" K")


def test_rearrangement_listing_and_isolate_requires_exactly_one_occurrence():
    it, _ = run_it("eq Force { F = m * a }")
    assert rearrangements(it.equations["Force"]) == ["m = F / a", "a = F / m"]
    rel = it.equations["Force"].relations[0]
    assert isolate(rel.lhs, rel.rhs, "m") is not None
    it2, _ = run_it("eq Q { y = x + x^2 }")
    rel = it2.equations["Q"].relations[0]
    assert isolate(rel.lhs, rel.rhs, "x") is None and isolate(rel.lhs, rel.rhs, "y") is not None


def test_stdlib_equations_agree_with_hand_calculation():
    out = run("import CircularOrbit\nCircularOrbit(mu = muEarth, r = rEarth + 400 km).v")
    assert out[0].startswith("7668.5")
    out = run("import DeltaV\nsolve DeltaV for m0 { Isp = 300 s\n mf = 1 kg\n dv = 3232 m/s }")
    assert out[0].startswith("m0 = 2.99") or out[0].startswith("m0 = 3.0")
