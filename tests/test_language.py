import pytest

from f2orge import Interpreter
from f2orge.errors import ForgeEvalError, ForgeNameError, ForgeSyntaxError
from helpers import TempDir, error_of, run, run_it


@pytest.mark.parametrize("src,expected", [
    ("2 + 3 * 4", "14"), ("(2 + 3) * 4", "20"), ("-2^2", "-4"), ("2^3^2", "512"), ("2^-1", "0.5"),
    ("10 - 4 - 3", "3"), ("100 / 10 / 5", "2"), ("-(2 + 3)", "-5"), ("+4", "4"), ("2 * -3", "-6"),
    ("6 × 7", "42"), ("10 ÷ 4", "2.5"), ("5 − 2", "3"), ("2 · 3", "6"),
])
def test_precedence_and_unicode_operators(src, expected):
    assert run(src) == [expected]


@pytest.mark.parametrize("src,expected", [
    ("sqrt(2) * sqrt(2)", "2"), ("exp(0)", "1"), ("abs(-3 m)", "3 m"), ("min(3 m, 2 m)", "2 m"),
    ("max(1, 5, 3)", "5"), ("asin(1)", "1.570796327"), ("atan2(1 m, 1 m)", "0.7853981634"),
    ("cos(180 deg)", "-1"), ("sin(pi / 2)", "1"), ("sqrt(16 m^2)", "4 m"),
])
def test_functions(src, expected):
    assert run(src) == [expected]


@pytest.mark.parametrize("src", ["ln(0)", "ln(-1)", "log(0)", "sqrt(-1)", "asin(2)", "5 / 0", "0 ^ -1", "(-8) ^ 0.5"])
def test_math_domain_errors(src):
    assert isinstance(error_of(src), ForgeEvalError)


def test_variables_and_ans():
    assert run("x = 3 m\ny = x * 2\ny") == ["6 m"]
    assert run("5 kg\nans * 2") == ["5 kg", "10 kg"]
    assert run("x = 1; y = 2; x + y") == ["3"]


def test_variables_can_shadow_constants_and_units():
    assert run("g = 5 m/s^2\ng") == ["5 m/s²"]
    assert run("m = 150 kg\nm * 2 m") == ["300 kg*m"] or run("m = 150 kg\nm * 2 m")[0].startswith("300")


def test_names_with_suggestions():
    err = error_of("mass = 5 kg\nmas")
    assert isinstance(err, ForgeNameError) and "Did you mean 'mass'" in err.hint
    assert "is an equation" in error_of("eq Foo { y = x }\nFoo").hint


def test_comments_continuation_and_blank_lines():
    src = "# a comment\nx = 1 +\n    2   // another\n\n\nx"
    assert run(src) == ["3"]


def test_multiline_call_and_print():
    out = run('eq E { y = a * b }\nr = E(\n    a = 2 m,\n    b = 3 m\n)\nprint "area:", r')
    assert out == ["area: 6 m²"]


def test_superscript_power_on_values():
    assert run("x = 3 m\nx²") == ["9 m²"]
    assert run("(2 + 1)²") == ["9"]


def test_text_is_only_for_print_and_metadata():
    assert isinstance(error_of('x = "hi"'), ForgeSyntaxError)


@pytest.mark.parametrize("src,needle", [
    ("x = (1 + ", "Expected a value"),
    ("x = 5 kg 3", "Unexpected"),
    ("eq A { y = }", "Expected a value"),
    ("eq A {\n y = 1", "missing its closing"),
    ("convert 5 m", "Expected '->'"),
    ("solve Force a { }", "Expected 'for'"),
    ("x = @", "Unexpected character"),
    ('print "abc', "closing quote"),
    ("for = 3", "can only be used inside a solve"),
    ("import", "Expected an equation name"),
])
def test_syntax_errors_say_what_was_expected(src, needle):
    err = error_of(src)
    assert needle in err.message


def test_error_report_points_at_the_source():
    text = error_of("a = 1\nb = 10 kg + 5 m").format()
    lines = text.splitlines()
    assert lines[0] == "error: Unit mismatch"
    assert "test.forge:2:5" in lines[1]
    assert "b = 10 kg + 5 m" in text
    assert "^^^^^^^^^^^" in text and "cannot add mass (kg) and length (m)" in text


def test_programs_run_from_files_with_a_bom():
    with TempDir() as d:
        (d / "p.forge").write_bytes("\ufeffx = 4 m\nx * 2\n".encode("utf-8"))
        out = []
        Interpreter(out=out.append).run_file(d / "p.forge")
        assert out == ["8 m"]


def test_assignments_are_silent_in_programs_and_echoed_in_the_shell():
    assert run("x = 5 m") == []
    out = []
    it = Interpreter(out=out.append, echo=True)
    it.run("x = 5 m", "<shell>")
    assert out == ["x = 5 m"]
