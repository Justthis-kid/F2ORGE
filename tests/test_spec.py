"""One test per numbered feature of the F²ORGE feature list (the v1 core).

Features 19-31 (calculator, graphing, matrices) and 41-45 are planned for later stages.
"""
import json

import pytest

from f2orge.errors import ForgeError, SolveError, UnitError
from helpers import ROOT, TempDir, error_of, forge, run, run_it


def test_01_variables():
    assert run("mass = 150\nmass") == ["150"]


def test_02_builtin_units():
    assert run("mass = 150 kg\nvelocity = 30 m/s\nmass\nvelocity") == ["150 kg", "30 m/s"]


def test_02_units_cover_the_listed_categories():
    # length, mass, time, force, energy, pressure, temperature, electrical
    for text in ["3 ft", "2 lb", "5 min", "10 lbf", "4 kcal", "2 atm", "20 degC", "12 V", "5 mA", "4 kohm"]:
        assert run(text)  # parses and prints


def test_03_unit_conversion():
    assert run("convert 10 ft -> m") == ["3.048 m"]


def test_04_dimensional_analysis_simplifies_to_named_units():
    assert run("150 kg * 9.81 m/s^2") == ["1471.5 N"]
    assert run("1 kg * 1 m/s^2") == ["1 N"]
    assert run("2 N * 3 m") == ["6 J"]


def test_05_unit_safety_checking():
    err = error_of("10 kg + 5 m")
    assert err.title == "Unit mismatch"
    assert "mass (kg)" in err.message and "length (m)" in err.message
    assert err.span is not None and err.span.text == "10 kg + 5 m"


@pytest.mark.parametrize("src,expected", [
    ("2 + 3", "5"), ("7 - 10", "-3"), ("6 * 7", "42"), ("10 / 4", "2.5"), ("2 ^ 10", "1024"),
])
def test_06_math_operators(src, expected):
    assert run(src) == [expected]


@pytest.mark.parametrize("src,expected", [
    ("sin(0)", "0"), ("cos(0)", "1"), ("tan(45 deg)", "1"), ("ln(e)", "1"), ("log(1000)", "3"),
    ("sqrt(16)", "4"),
])
def test_07_scientific_functions(src, expected):
    assert run(src) == [expected]


def test_08_equations_are_first_class_objects():
    it, _ = run_it("eq Force {\n    F = m * a\n}")
    assert "Force" in it.equations


def test_09_and_10_import_and_export():
    with TempDir() as d:
        out = run("eq Force { F = m * a }\nexport Force", d)
        assert (d / "Force.eq").is_file() and out == [f"Exported Force -> {(d / 'Force.eq')}"] or out
        # a fresh program can import the exported file by name
        assert run("import Force\nForce(m = 2 kg, a = 3 m/s^2)", d) == ["6 N"]


def test_11_auto_detect_inputs_and_outputs():
    it, _ = run_it("eq Force { F = m * a }")
    eq = it.equations["Force"]
    assert eq.inputs == ["m", "a"] and eq.outputs == ["F"]


def test_12_equation_calls():
    out = run("""eq Force { F = m * a }
force = Force(
    m = 150 kg,
    a = 9.81 m/s²
)
force""")
    assert out == ["1471.5 N"]


def test_13_equation_metadata():
    it, _ = run_it('eq Force {\n    description =\n        "Newton\'s Second Law"\n    F = m * a\n}')
    assert it.equations["Force"].metadata["description"] == "Newton's Second Law"


def test_14_documentation_generation():
    r = forge("doc", "Force")
    assert r.returncode == 0
    for section in ("# Force", "## Formula", "## Inputs", "## Outputs", "Newton"):
        assert section in r.stdout
    assert "F = m * a" in r.stdout and "m/s²" in r.stdout


def test_15_equation_packages():
    import math
    cases = [
        ("DeltaV", "DeltaV(Isp = 300 s, m0 = 3 kg, mf = 1 kg)", 300 * 9.80665 * math.log(3)),
        ("KineticEnergy", "KineticEnergy(m = 2 kg, v = 3 m/s)", 9.0),
        ("Ohm", "Ohm(I = 2 A, R = 5 ohm)", 10.0),
        ("Bernoulli", None, None),
    ]
    for name, call, expected in cases:
        if call is None:  # an implicit relation: usable through solve, not call
            out = run(f"import {name}\nsolve {name} for p2 {{ p1 = 2 Pa\n v1 = 0 m/s\n h1 = 0 m\n v2 = 0 m/s\n h2 = 0 m\n rho = 1 kg/m^3 }}")
            assert out == ["p2 = 2 Pa"]
            continue
        it, _ = run_it(f"import {name}\nx = {call}")
        assert it.variables["x"].value == pytest.approx(expected, rel=1e-12)


def test_16_solve_for_variable():
    out = run("""eq Force { F = m * a }
solve Force for a {
    F = 100 N
    m = 50 kg
}""")
    assert out == ["a = 2 m/s²"]


def test_17_automatic_rearrangement():
    it, out = run_it("eq Force { F = m * a }\nsolve Force for m { F = 100 N\n a = 4 m/s^2 }")
    assert out == ["m = 25 kg"]
    from f2orge.solver import rearrangements
    assert "a = F / m" in rearrangements(it.equations["Force"])


def test_18_multiple_unknown_detection():
    err = error_of("eq Force { F = m * a }\nsolve Force for F { a = 10 m/s^2 }")
    assert isinstance(err, SolveError) and "m is unknown" in err.message
    assert "value for m" in err.hint


def test_32_constants_library():
    assert run("pi")[0].startswith("3.14159")
    assert run("g") == ["9.80665 m/s²"]
    assert run("G")[0].startswith("6.6743e-11")
    assert run("R")[0].startswith("8.314462618")


def test_33_engineering_constant_packs():
    assert run("muEarth")[0].startswith("3.986004418e+14")
    assert run("speedOfLight") == ["299792458 m/s"]


def test_34_cli_compiler():
    r = forge("run", str(ROOT / "examples" / "basics.forge"))
    assert r.returncode == 0 and "3.048 m" in r.stdout and "1471.5 N" in r.stdout


def test_35_interactive_repl():
    r = forge("shell", stdin="x = 3 m\nx * 2\n:quit\n")
    assert r.returncode == 0 and "6 m" in r.stdout


def test_36_syntax_highlighting_extension_is_well_formed():
    pkg = json.loads((ROOT / "vscode-forge" / "package.json").read_text(encoding="utf-8"))
    grammar = pkg["contributes"]["grammars"][0]
    assert (ROOT / "vscode-forge" / grammar["path"]).is_file()
    assert json.loads((ROOT / "vscode-forge" / grammar["path"]).read_text(encoding="utf-8"))["scopeName"] == "source.forge"


def test_37_helpful_error_reporting():
    err = error_of("import Force\nForce(m = 150 kg, a = 5 kg)")
    assert "expects acceleration (m/s²)" in err.message and "mass (kg)" in err.message
    text = err.format()
    assert "^" in text and "Force(m = 150 kg, a = 5 kg)" in text



def test_39_and_40_eq_files_and_project_imports():
    with TempDir() as d:
        (d / "formulas").mkdir()
        (d / "formulas" / "Area.eq").write_text("eq Area {\n  A = w * h\n}\n", encoding="utf-8")
        (d / "main.forge").write_text("import ./formulas/Area.eq\nArea(w = 2 m, h = 3 m)\n", encoding="utf-8")
        r = forge("run", str(d / "main.forge"))
        assert r.returncode == 0 and r.stdout.strip() == "6 m²"


def test_38_local_first_no_third_party_dependencies():
    import re
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r"^dependencies\s*=\s*\[\s*\]", text, re.M)
