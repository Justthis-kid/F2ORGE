import contextlib
import io

import pytest

from f2orge.errors import ForgeError
from f2orge.transpile import transpile
from helpers import TempDir, forge


def test_python_transpilation_executes_si_scalar_program_and_conversion():
    source = (
        "mass = 150 kg\n"
        "acceleration = 9.81 m/s^2\n"
        "force = mass * acceleration\n"
        "force\n"
        'print "ready"\n'
        "convert 10 ft -> m\n"
    )
    generated = transpile(source, "python")
    namespace = {}
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(compile(generated, "<generated>", "exec"), namespace)
    assert namespace["force"] == pytest.approx(1471.5)
    assert output.getvalue().splitlines() == ["1471.5", "ready", "3.048 m"]
    assert "unit-safety checks are not retained" in generated


def test_python_transpilation_supports_functions_and_constant_overrides():
    generated = transpile("pi = 3\nx = sin(pi / 2) + log(100)\nx\n", "python")
    namespace = {}
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(compile(generated, "<generated>", "exec"), namespace)
    assert output.getvalue() == "2.9974949866040546\n"
    override = transpile("pi = 3\npi\n", "python")
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(compile(override, "<generated>", "exec"), {})
    assert output.getvalue() == "3.0\n"


def test_micropython_transpilation_runs_with_standard_python_compatible_subset():
    source = (
        "distance = 10 ft\n"
        "speed = 2 m/s\n"
        "print distance / speed\n"
        "print log(100)\n"
        "convert 10 ft -> m\n"
    )
    generated = transpile(source, "micropython")
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(compile(generated, "<generated>", "exec"), {})
    assert output.getvalue().splitlines() == ["1.524", "2.0", "3.048 m"]
    assert "import math" in generated
    assert "(math.log(100.0) / math.log(10))" in generated
    assert transpile("x = sqrt(9)\n", "micro-py") == transpile("x = sqrt(9)\n", "micropython")


def test_ti_basic_transpilation_maps_variables_and_generates_calculator_syntax():
    source = (
        "mass = 150 kg\n"
        "acceleration = 9.81 m/s^2\n"
        "force = mass * acceleration\n"
        "force\n"
        "convert 10 ft -> m\n"
    )
    generated = transpile(source, "ti-basic")
    assert ':Disp "A=mass"' in generated
    assert ':Disp "B=acceleration"' in generated
    assert "150.0→A" in generated
    assert "9.81→" in generated
    assert "→C" in generated
    assert ":Disp D" in generated and 'Disp "m"' in generated
    assert generated.startswith(":ClrHome\n:If 0:Then\n")
    assert "\n:End\n:150.0→A" in generated and generated.endswith('Disp "m"\n')


def test_ti_basic_transpilation_maps_functions_and_physical_constants():
    generated = transpile("answer = sqrt(g) + sin(pi / 2)\nanswer\n", "ti84")
    assert "√(9.80665)" in generated
    assert "sin((π / 2.0))" in generated
    assert ":Disp B" in generated
    assert "import math" not in generated


def test_ti_basic_rejects_unsupported_function_and_variable_overflow():
    with pytest.raises(ForgeError, match="atan2") as caught:
        transpile("x = atan2(1, 2)\n", "ti-basic")
    assert caught.value.title == "Cannot transpile"
    program = "\n".join(f"value_{index} = {index}" for index in range(28))
    with pytest.raises(ForgeError, match="27 scalar variables"):
        transpile(program, "ti-basic")


def test_cpp_transpilation_emits_standalone_main_and_si_conversion():
    generated = transpile("force = 150 kg * 9.81 m/s^2\nprint force\nconvert 10 ft -> m\n", "cpp")
    assert "#include <cmath>" in generated
    assert "int main() {" in generated
    assert "force = ((150.0 * 1.0) * (9.81 * 1.0));" in generated
    assert 'std::cout << ans << " m" << \'\\n\';' in generated
    assert generated.rstrip().endswith("}")


@pytest.mark.parametrize(
    "source",
    [
        "eq Force { F = m * a }\n",
        "solve Force for a { F = 10 N\nm = 2 kg }\n",
        "v = <1, 2, 3>\n",
        "import Force\n",
    ],
)
def test_transpilation_rejects_unsupported_constructs_with_locations(source):
    with pytest.raises(ForgeError) as caught:
        transpile(source, "python", "sample.forge")
    assert caught.value.title == "Cannot transpile"
    assert caught.value.span is not None
    assert caught.value.span.source.name == "sample.forge"


def test_transpile_cli_writes_generated_file_and_reports_unsupported_source():
    with TempDir() as directory:
        source = directory / "program.forge"
        target = directory / "program.py"
        source.write_text("distance = 10 ft\nconvert distance -> m\n", encoding="utf-8")
        result = forge("transpile", str(source), "--target", "python", "-o", str(target))
        assert result.returncode == 0, result.stderr
        assert "Wrote" in result.stdout
        assert 'print(f"{ans:g} m")' in target.read_text(encoding="utf-8")

        source.write_text("eq Force { F = m * a }\n", encoding="utf-8")
        result = forge("transpile", str(source), "--target", "cpp")
        assert result.returncode == 1
        assert "Cannot transpile" in result.stderr and "sample" not in result.stderr


@pytest.mark.parametrize(
    ("target", "suffix"),
    [("micropython", ".py"), ("ti-basic", ".ti.txt")],
)
def test_transpile_cli_exports_additional_targets(target, suffix):
    with TempDir() as directory:
        source = directory / "program.forge"
        output = directory / f"program{suffix}"
        source.write_text("distance = 10 ft\nconvert distance -> m\n", encoding="utf-8")
        result = forge("transpile", str(source), "--target", target, "-o", str(output))
        assert result.returncode == 0, result.stderr
        generated = output.read_text(encoding="utf-8")
        assert "import math" in generated if target == "micropython" else ":ClrHome" in generated


@pytest.mark.parametrize(
    ("target", "expected"),
    [("micro-py", "import math"), ("ti-84-basic", ":ClrHome")],
)
def test_transpile_cli_accepts_target_aliases(target, expected):
    with TempDir() as directory:
        source = directory / "program.forge"
        source.write_text("answer = 42\n", encoding="utf-8")
        result = forge("transpile", str(source), "--target", target)
        assert result.returncode == 0, result.stderr
        assert expected in result.stdout
