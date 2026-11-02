import json
import xml.etree.ElementTree as ET

import pytest

from f2orge import Interpreter
from f2orge.calculator import run_terminal_calculator
from f2orge.repl import is_complete, run_shell
from helpers import ROOT, TempDir, forge, run_it


def test_run_examples_exit_cleanly():
    for name in ("basics", "force", "glider", "imports"):
        r = forge("run", str(ROOT / "examples" / f"{name}.forge"))
        assert r.returncode == 0, (name, r.stderr)
    assert "V = 16.4" in forge("run", str(ROOT / "examples" / "glider.forge")).stdout
    (ROOT / "examples" / "Force.eq").unlink(missing_ok=True)  # written by force.forge's `export`


def test_errors_go_to_stderr_with_exit_code_1():
    with TempDir() as d:
        (d / "bad.forge").write_text("x = 1\ny = 10 kg + 5 m\n", encoding="utf-8")
        r = forge("run", str(d / "bad.forge"))
        assert r.returncode == 1 and r.stdout == ""
        assert "error: Unit mismatch" in r.stderr and "bad.forge:2:5" in r.stderr and "^^^^" in r.stderr
        assert forge("run", str(d / "missing.forge")).returncode == 2


def test_explain_flag_shows_the_rearrangement():
    with TempDir() as d:
        (d / "p.forge").write_text("import Force\nsolve Force for m { F = 10 N\n a = 2 m/s^2 }\n", encoding="utf-8")
        plain = forge("run", str(d / "p.forge")).stdout
        explained = forge("run", "--explain", str(d / "p.forge")).stdout
    assert plain == "m = 5 kg\n" and "rearranged: m = F / a" in explained


def test_ascii_flag_for_limited_terminals():
    with TempDir() as d:
        (d / "p.forge").write_text("9.81 m/s^2\n", encoding="utf-8")
        assert forge("--ascii", "run", str(d / "p.forge")).stdout == "9.81 m/s^2\n"
        assert forge("run", str(d / "p.forge")).stdout == "9.81 m/s²\n"


def test_units_and_version_commands():
    r = forge("units", "pressure")
    assert r.returncode == 0 and "psi" in r.stdout and "kg" not in r.stdout.split("\n")[0]
    assert forge("--version").stdout.startswith("F²ORGE 0.1.0")
    assert forge().returncode == 0


def test_desktop_ide_command_is_available():
    result = forge("ide", "--help")
    assert result.returncode == 0 and "embedded webview" in result.stdout


def test_browser_ide_commands_are_available():
    browser = forge("browser", "--help")
    web = forge("web", "--help")
    assert browser.returncode == 0 and "browser IDE on loopback" in browser.stdout
    assert web.returncode == 0 and "--no-open" in web.stdout


def test_graph_command_exports_browser_compatible_svg():
    with TempDir() as d:
        output = d / "force.svg"
        result = forge("graph", "Force", "--vary", "a", "--from", "0", "--to", "20",
                       "--set", "m=150 kg", "--samples", "3", "-o", str(output), cwd=d)
        assert result.returncode == 0, result.stderr
        svg = output.read_text(encoding="utf-8")
    root = ET.fromstring(svg)
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert root.find("svg:title", namespace).text == "Force: F vs a"
    texts = [element.text for element in root.findall(".//svg:text", namespace)]
    assert "Acceleration (m/s²)" in texts and "Net force (N)" in texts
    polyline = root.find("svg:polyline", namespace)
    assert len(polyline.attrib["points"].split()) == 3


@pytest.mark.parametrize(("extension", "signature"), [(".png", b"\x89PNG\r\n\x1a\n"), (".pdf", b"%PDF-")])
def test_graph_command_exports_raster_and_pdf_formats(extension, signature):
    with TempDir() as directory:
        output = directory / f"force{extension}"
        result = forge(
            "graph", "Force", "--vary", "a", "--from", "0", "--to", "20",
            "--set", "m=150 kg", "--samples", "3", "-o", str(output), cwd=directory,
        )
        assert result.returncode == 0, result.stderr
        assert output.read_bytes().startswith(signature)


def test_graph_command_exports_multiple_curves_with_legend():
    with TempDir() as d:
        output = d / "forces.svg"
        result = forge("graph", "Force", "--vary", "a", "--from", "0", "--to", "20",
                       "--curve", "m=50 kg", "--curve", "m=100 kg", "--samples", "3",
                       "-o", str(output), cwd=d)
        assert result.returncode == 0, result.stderr
        root = ET.parse(output).getroot()
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    curves = root.findall("svg:polyline", namespace)
    assert len(curves) == 2
    assert all(len(curve.attrib["points"].split()) == 3 for curve in curves)
    texts = [element.text for element in root.findall(".//svg:text", namespace)]
    assert "m = 50 kg" in texts and "m = 100 kg" in texts


def test_graph_command_exports_offline_interactive_html():
    with TempDir() as d:
        output = d / "interactive.html"
        result = forge("graph", "Force", "--vary", "a", "--from", "0", "--to", "20",
                       "--curve", "m=50 kg", "--curve", "m=100 kg", "--samples", "3",
                       "--interactive", "-o", str(output), cwd=d)
        assert result.returncode == 0, result.stderr
        page = output.read_text(encoding="utf-8")
    assert "<!doctype html>" in page and "<svg " in page
    assert "Reset view" in page and 'data-series="0"' in page and 'data-series="1"' in page
    assert 'addEventListener("wheel",zoom' in page
    assert "pointerdown" in page and "https://" not in page and "<script src=" not in page


def test_vector_plot_command_exports_interactive_html():
    with TempDir() as directory:
        source = directory / "vectors.forge"
        output = directory / "plot.html"
        source.write_text("time = <0 s, 1 s, 2 s>\nposition = <0 m, 3 m, 8 m>\n", encoding="utf-8")
        result = forge("plot", str(source), "position", "--x", "time", "-o", str(output), cwd=directory)
        assert result.returncode == 0, result.stderr
        page = output.read_text(encoding="utf-8")
        assert "position (m) vs time (s)" in page
        assert "Reset view" in page and "pointerdown" in page


def test_graph_command_rejects_mixed_curve_variables():
    with TempDir() as d:
        equation = d / "TripleInput.eq"
        equation.write_text(
            "eq TripleInput {\n x : m\n y : kg\n z : s\n Q = x * y / z\n}\n",
            encoding="utf-8",
        )
        result = forge("graph", str(equation), "--vary", "x", "--from", "0", "--to", "20",
                       "--curve", "y=50 kg", "--curve", "z=10 s", cwd=d)
    assert result.returncode == 1 and "same input" in result.stderr


def test_calc_command_generates_standalone_offline_html():
    with TempDir() as d:
        equation = d / "Force.eq"
        equation.write_text(
            """eq Force {
 description = "Newton's Second Law"
 m : kg "mass"
 a : m/s^2 "acceleration"
 F : N "net force"
 F = m * a
}
""",
            encoding="utf-8",
        )
        output = d / "force.html"
        result = forge("calc", str(equation), "-o", str(output), cwd=d)
        assert result.returncode == 0, result.stderr
        page = output.read_text(encoding="utf-8")
    assert "<!doctype html>" in page
    assert "Newton's Second Law" in page
    assert 'input.id="input-"+name' in page and 'value.id="result-"+name' in page
    assert 'addEventListener("input",recalculate)' in page
    assert 'expects "+decl.description' in page
    assert "https://" not in page and "<script src=" not in page


def test_calc_command_requires_declared_input_units():
    with TempDir() as d:
        equation = d / "NoUnits.eq"
        equation.write_text("eq NoUnits { y = x * 2 }\n", encoding="utf-8")
        result = forge("calc", str(equation), "-o", str(d / "calculator.html"), cwd=d)
        assert result.returncode == 1 and "unit declarations" in result.stderr
        assert not (d / "calculator.html").exists()


def test_terminal_calculator_recalculates_and_checks_units():
    interpreter, _ = run_it(
        'eq Force {\n m : kg\n a : m/s^2\n F : N\n F = m * a\n}\n'
    )
    lines = iter(["m = 50 kg", "a = 2 m/s^2", "m = 100 kg", "a = 2 m", ":quit"])
    output = []
    run_terminal_calculator(interpreter, "Force", input_fn=lambda prompt: next(lines), out=output.append)
    text = "\n".join(output)
    assert "F = 100 N" in text and "F = 200 N" in text
    assert "a of Force expects acceleration (m/s²), but this is length (m)" in text


def test_terminal_calculator_cli_uses_standard_equation():
    result = forge("calc", "Force", "--terminal",
                   stdin="m = 150 kg\na = 9.81 m/s^2\n:quit\n")
    assert result.returncode == 0, result.stderr
    assert "F = 1471.5 N" in result.stdout


def test_graph_command_reports_unit_mismatches_without_writing_a_graph():
    with TempDir() as d:
        output = d / "bad.svg"
        result = forge("graph", "Force", "--vary", "a", "--from", "0", "--to", "10",
                       "--set", "m=150 m", "-o", str(output), cwd=d)
        assert result.returncode == 1 and "expects mass" in result.stderr
        assert not output.exists()


def test_shell_session_over_a_pipe():
    r = forge("shell", stdin='x = 3 m\nx * 2\nconvert x -> ft\neq K {\n  KE = 0.5 * m * v^2\n}\n'
                             'K(m = 2 kg, v = 3 m/s)\n:eqs\n10 kg + 5 m\nx\n:quit\n')
    assert r.returncode == 0
    for needle in ("x = 3 m", "6 m", "9.842519685 ft", "9 J", "K: m, v -> KE", "error: Unit mismatch", "3 m"):
        assert needle in r.stdout, needle


def test_shell_commands_and_recovery_from_errors():
    out = []
    lines = iter(["import Force", ":eqs", ":doc Force", ":vars", ":units mass", ":constants", ":explain on",
                  "solve Force for a { F = 6 N\n", "m = 2 kg }", "oops +", "1", "3 kg + 1 m", "ans", ":bogus", ":quit"])
    run_shell(Interpreter(out=out.append), input_fn=lambda prompt: next(lines), out=out.append)
    text = "\n".join(out)
    for needle in ("Force: m, a -> F", "# Force", "(no variables yet)", "mass:", "Physics:", "explain is on",
                   "a = 3 m/s²", "rearranged: a = F / m", "error: Unit mismatch", "Unknown command"):
        assert needle in text, needle


def test_shell_knows_when_to_keep_reading():
    assert not is_complete(["eq F {"]) and is_complete(["eq F {", "}"])
    assert not is_complete(["x ="]) and not is_complete(["f(1,"]) and not is_complete(["convert 5 m ->"])
    assert is_complete(['print "a ("']) and is_complete(["x = 1 # (comment"]) and is_complete([""])


def test_vscode_extension_files_are_consistent():
    root = ROOT / "vscode-forge"
    pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
    lang = pkg["contributes"]["languages"][0]
    assert ".forge" in lang["extensions"] and ".eq" in lang["extensions"]
    assert (root / lang["configuration"]).is_file()
    grammar = json.loads((root / pkg["contributes"]["grammars"][0]["path"]).read_text(encoding="utf-8"))
    import re
    patterns = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("match", "begin", "end") and isinstance(v, str):
                    patterns.append(v)
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(grammar)
    assert len(patterns) >= 10
    for p in patterns:
        re.compile(p)
    quantity = re.compile(grammar["repository"]["quantity"]["match"])
    m = quantity.search("a = 9.81 m/s²")
    assert m.group(1) == "9.81" and m.group(2) == "m/s²"


def test_blank_lines_in_the_shell_do_not_start_a_continuation():
    out = []
    lines = iter(["", "   ", "1 + 1", ":quit"])
    prompts = []
    run_shell(Interpreter(out=out.append), input_fn=lambda p: (prompts.append(p), next(lines))[1], out=out.append)
    assert prompts == ["forge> "] * 4 and "2" in out
