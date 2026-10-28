import pytest

from f2orge import Interpreter
from f2orge.errors import ForgeError, ForgeImportError, ForgeSyntaxError, UnitError
from helpers import TempDir, error_of, forge, run, run_it


def test_inputs_outputs_and_order_are_detected():
    it, _ = run_it("eq Chain {\n    z = y + 1 m\n    y = 2 * x\n}")
    eq = it.equations["Chain"]
    assert eq.inputs == ["x"] and eq.outputs == ["z", "y"] and eq.primary == "z"
    assert [r.lhs.name for r in eq.order] == ["y", "z"]  # dependencies first
    assert run("eq Chain {\n z = y + 1 m\n y = 2 * x\n}\nChain(x = 3 m)\nChain(x = 3 m).y") == ["7 m", "6 m"]


def test_call_errors_explain_what_to_do():
    err = error_of("eq Force { F = m * a }\nForce(m = 1 kg)")
    assert "needs a value for: a" in err.message and "solve Force for a" in err.hint
    err = error_of("eq Force { F = m * a }\nForce(m = 1 kg, a = 2 m/s^2, mm = 3 kg)")
    assert "no input named 'mm'" in err.message and "Did you mean 'm'" in err.hint
    err = error_of("eq Force { F = m * a }\nForce(F = 1 N, m = 1 kg)")
    assert "'F' is an output" in err.message and "solve Force for" in err.hint
    err = error_of("eq Force { F = m * a }\nForce(1 kg, 2 m/s^2)")
    assert "needs named values" in err.message and "Force(m = ..., a = ...)" in err.hint
    err = error_of("eq Force { F = m * a }\nForce(m = 1 kg, m = 2 kg, a = 1 m/s^2)")
    assert "given twice" in err.message
    err = error_of("eq Force { F = m * a }\nForce(m = 1 kg, a = 2 m/s^2).X")
    assert "no output named 'X'" in err.message


def test_declared_units_check_arguments_and_label_outputs():
    src = "eq F2 {\n m : kg\n a : m/s^2\n F : N\n F = m * a\n}\n"
    assert run(src + "F2(m = 150 kg, a = 9.81 m/s^2)") == ["1471.5 N"]
    err = error_of(src + "F2(m = 150 kg, a = 5 kg)")
    assert isinstance(err, UnitError)
    assert "expects acceleration (m/s²)" in err.message and "mass (kg)" in err.message
    # the message points at the offending argument, and the caret shows the call-site value
    assert err.span.text == "5 kg"


def test_errors_inside_a_formula_mention_the_call_site():
    err = error_of("eq Bad { y = x + 1 m }\nBad(x = 2 s)")
    assert isinstance(err, UnitError) and any("while calling Bad()" in n for n in err.notes)


def test_definition_time_dimension_check():
    err = error_of("eq Bad {\n m : kg\n a : m/s^2\n F : N\n F = m * a * a\n}")
    assert isinstance(err, UnitError) and "declared as force (N)" in err.message
    err = error_of("eq W { x : m\n t : s\n x + 0 m = t }")
    assert "different things" in err.message
    run("eq Fine { y = x * 2 }")  # undeclared inputs: nothing to check yet, no error


def test_declared_names_override_constants():
    it, _ = run_it("import Ohm\nimport IdealGas\nv = Ohm(I = 2 A, R = 5 ohm)\n"
                   "p = IdealGas(n = 1 mol, T = 273.15 K, V = 22.414 L)")
    assert it.variables["v"].value == pytest.approx(10.0)
    assert it.variables["p"].value == pytest.approx(101325.0, rel=1e-3)  # R here is the gas constant
    # an undeclared R inside an equation is the built-in constant, so it is not an input
    eq = run_it("eq Gas { P = n * R * T / V }")[0].equations["Gas"]
    assert "R" not in eq.inputs and eq.inputs == ["n", "T", "V"]


@pytest.mark.parametrize("src,needle", [
    ("eq C { a = b + 1\n b = a + 1 }", "depend on each other"),
    ("eq D { x = 1\n x = 2 }", "defined twice"),
    ("eq U { q : m\n y = 2 }", "declared but never used"),
    ("eq N { description = \"nothing\" }", "has no formula"),
    ("eq M { m : kg\n m : kg\n y = m }", "declared twice"),
    ("eq Loop { y = Loop(x = x) }", "not a function or an equation"),
])
def test_invalid_equations(src, needle):
    assert needle in error_of(src).message


def test_equations_can_call_other_equations():
    out = run("eq A { y = x * 2 }\neq B { z = A(x = w) + 1 }\nB(w = 3)")
    assert out == ["7"]


def test_implicit_relations_work_with_solve_but_not_call():
    err = error_of("eq Imp { x + y = 10 }\nImp(x = 1, y = 2)")
    assert "does not define an output" in err.message and "solve Imp for" in err.hint
    assert run("eq Imp { x + y = 10 }\nsolve Imp for x { y = 4 }") == ["x = 6"]


def test_export_import_round_trip_is_stable():
    src = ('eq Spring {\n    description = "Hooke\'s law, with \\"quotes\\""\n    source = "textbook"\n\n'
           '    k : N/m "spring constant"\n    x : m\n    F : N\n\n    F = -k * x\n}\n')
    with TempDir() as d:
        run(src + "export Spring", d)
        first = (d / "Spring.eq").read_text(encoding="utf-8")
        assert "description = " in first and 'k : N/m "spring constant"' in first and "F = -k * x" in first
        it, _ = run_it("import Spring\nf = Spring(k = 200 N/m, x = 0.05 m)", d)
        assert it.variables["f"].value == pytest.approx(-10.0)
        assert it.equations["Spring"].metadata["description"] == 'Hooke\'s law, with "quotes"'
        run("import Spring\nexport Spring", d)  # export(import(export)) changes nothing
        assert (d / "Spring.eq").read_text(encoding="utf-8") == first


def test_imports_by_name_by_path_and_from_project_folders():
    with TempDir() as d:
        (d / "formulas").mkdir()
        (d / "formulas" / "Area.eq").write_text("eq Area { A = w * h }\n", encoding="utf-8")
        (d / "Volume.eq").write_text("import Area\neq Volume { V = Area(w = w, h = h) * d }\n", encoding="utf-8")
        assert run("import Area\nArea(w = 2 m, h = 3 m)", d) == ["6 m²"]                 # ./formulas is searched
        assert run("import ./formulas/Area.eq\nArea(w = 1 m, h = 1 m)", d) == ["1 m²"]    # explicit path
        assert run("import Volume\nVolume(w = 2 m, h = 3 m, d = 4 m)", d) == ["24 m³"]  # eq file importing eq file
        assert run("import Force\nForce(m = 1 kg, a = 1 m/s^2)", d) == ["1 N"]            # standard library


def test_import_errors():
    with TempDir() as d:
        err = error_of("import Forse", d)
        assert isinstance(err, ForgeImportError) and "Did you mean 'Force'" in err.hint
        assert "Cannot find the file" in error_of("import ./nope/X.eq", d).message
        (d / "Other.eq").write_text("eq Different { y = x }\n", encoding="utf-8")
        assert "does not define an equation named 'Other'" in error_of("import Other", d).message
        (d / "Bad.eq").write_text("x = 5\n", encoding="utf-8")
        assert "can only contain" in error_of("import Bad", d).message
        (d / "A.eq").write_text("import B\neq A { y = x }\n", encoding="utf-8")
        (d / "B.eq").write_text("import A\neq B { y = x }\n", encoding="utf-8")
        assert "cycle" in error_of("import A", d).message


def test_generated_documentation_has_all_sections():
    with TempDir() as d:
        out = forge("doc", "Lift", "-o", str(d / "Lift.md"))
        assert out.returncode == 0
        text = (d / "Lift.md").read_text(encoding="utf-8")
    for needle in ("# Lift", "> Aerodynamic lift", "## Formula", "L = 0.5 * rho * V^2 * S * CL", "## Inputs",
                   "| `rho` | kg/m³ | density | air density |", "## Outputs", "| `L` | N | force |",
                   "## Solve for any variable", "`V = sqrt("):
        assert needle in text, needle


def test_docs_derive_output_units_from_the_formula():
    with TempDir() as d:
        (d / "E.eq").write_text("eq E { m : kg\n a : m/s^2\n F = m * a }\n", encoding="utf-8")
        text = forge("doc", str(d / "E.eq")).stdout
    assert "| `F` | N (derived) | force |" in text


def test_check_command_reports_unit_errors_without_running_anything():
    with TempDir() as d:
        (d / "ok.eq").write_text("eq Ok { y = x }\n", encoding="utf-8")
        (d / "bad.eq").write_text("eq Bad { x : m\n y : s\n y = x }\n", encoding="utf-8")
        assert forge("check", str(d / "ok.eq")).returncode == 0
        r = forge("check", str(d / "bad.eq"))
        assert r.returncode == 1 and "declared as time (s)" in r.stderr
