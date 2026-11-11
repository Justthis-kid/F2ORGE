import pytest

from f2orge import Interpreter
from f2orge.errors import ForgeError, ForgeEvalError, ForgeNameError, ForgeSyntaxError, UnitError
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


def test_vectors_support_addition_scaling_and_dot_products():
    assert run("v = <1, 2, 3>\nv + <3, 2, 1>\n2 * v\nv * v") == [
        "<4, 4, 4>", "<2, 4, 6>", "14",
    ]


def test_a_vector_operand_is_not_read_as_a_comparison():
    assert run("v = <1, 2>\nw = <3, 2>\nv + w + <1, 1>") == ["<5, 5>"]
    assert run("A = [[1, 0], [0, 1]]\n<1, 2> * A") == ["<1, 2>"]
    assert run("a = 1\nb = 2\na < b\nb > a") == ["true", "true"]


def test_matrices_support_matrix_vector_and_matrix_matrix_products():
    assert run("""A = [
  [1, 2]
  [3, 4]
]
B = [[2, 0], [1, 2]]
A * B
A * <1, 2>
<1, 2> * A""") == [
        "[[4, 4], [10, 8]]", "<5, 11>", "<7, 10>",
    ]


def test_matrix_inverse_and_transpose():
    assert run("A = [[1, 2], [3, 4]]\ntranspose(A)\ninverse(A)") == [
        "[[1, 3], [2, 4]]", "[[-2, 1], [1.5, -0.5]]",
    ]


def test_linear_algebra_checks_shapes_units_and_singular_inverse():
    from f2orge.errors import ForgeEvalError

    assert "same length" in error_of("<1, 2> + <3>").message
    assert "cannot multiply" in error_of("[[1, 2]] * <1>").message
    assert "Unit mismatch" == error_of("<1 m, 2 s> * <1, 1>").title
    assert "singular" in error_of("inverse([[1, 2], [2, 4]])").message
    with pytest.raises(ForgeEvalError, match="same shape"):
        run("[[1, 2]] + [[1], [2]]")
    assert "same number of values" in error_of("A = [[1, 2], [3]]").message
    assert "square matrix" in error_of("inverse([[1, 2, 3], [4, 5, 6]])").message
    assert "scalar quantity" in error_of("convert <1, 2> -> m").message


def test_equations_reject_matrix_and_vector_values_with_clear_errors():
    assert "matrices and vectors are program values" in error_of("eq A { result = [[1, 2]] }").message


def test_desktop_ide_runs_programs_and_returns_compiler_errors():
    from f2orge.desktop import run_source

    output, success = run_source("x = 150 kg\nprint x * 9.81 m/s^2")
    assert success and output == "1471.5 N"
    output, success = run_source("10 kg + 5 m")
    assert not success and "Unit mismatch" in output and "<editor>:1:1" in output


def test_desktop_session_shares_script_and_command_window_workspace():
    from f2orge.desktop import DesktopSession

    session = DesktopSession()
    output, success = session.execute("mass = 2 kg\nspeed = 3 m/s")
    assert success and output == ""
    output, success = session.execute("mass * speed")
    assert success and output == "6 kg*m/s"
    output, success = session.execute("speed = 4 m/s")
    assert success and output == ""
    output, success = session.execute("mass * speed")
    assert success and output == "8 kg*m/s"


def test_desktop_session_plots_workspace_vectors():
    from f2orge.desktop import DesktopSession

    session = DesktopSession()
    output, success = session.execute("time = <0 s, 1 s, 2 s>\nposition = <0 m, 3 m, 8 m>")
    assert success and not output
    assert session.plot_data("plot(time, position)") == (
        "time (s)", "position (m)", [(0.0, 0.0), (1.0, 3.0), (2.0, 8.0)],
    )
    assert session.plot_data("plot position") == (
        "Index", "position (m)", [(1, 0.0), (2, 3.0), (3, 8.0)],
    )


def test_visual_graph_compiles_connected_nodes_to_forge_and_runs():
    from f2orge.desktop import DesktopSession
    from f2orge.visual_graph import VisualGraph

    graph = VisualGraph()
    mass = graph.add_node("Input", "mass", 10, 10)
    acceleration = graph.add_node("Constant", "9.81 m/s^2", 10, 140)
    multiply = graph.add_node("Multiply", x=250, y=50)
    output = graph.add_node("Output", "force", 500, 50)
    graph.connect(mass.id, multiply.id, 0)
    graph.connect(acceleration.id, multiply.id, 1)
    graph.connect(multiply.id, output.id, 0)

    source = graph.compile()
    assert source == "force = (mass * 9.81 m/s^2)\nforce"
    session = DesktopSession()
    session.execute("mass = 150 kg")
    result, success = session.execute(source)
    assert success and result == "1471.5 N"


def test_visual_graph_functions_persistence_and_validation():
    from f2orge.errors import ForgeError
    from f2orge.visual_graph import VisualGraph

    graph = VisualGraph()
    source = graph.add_node("Constant", "16")
    root = graph.add_node("Function", "sqrt")
    output = graph.add_node("Output", "length")
    graph.connect(source.id, root.id, 0)
    graph.connect(root.id, output.id, 0)
    saved = graph.to_data()
    restored = VisualGraph.from_data(saved)
    assert restored.compile() == "length = sqrt(16)\nlength"
    cyclic = VisualGraph()
    add_a = cyclic.add_node("Add")
    add_b = cyclic.add_node("Add")
    cyclic.connect(add_a.id, add_b.id, 0)
    with pytest.raises(ForgeError, match="cycle"):
        cyclic.connect(add_b.id, add_a.id, 0)
    with pytest.raises(ForgeError, match="valid output"):
        graph.add_node("Output", "not a name")
    with pytest.raises(ForgeError, match="one F²ORGE expression"):
        graph.add_node("Constant", "1\nx = 2")
    with pytest.raises(ForgeError, match="Output"):
        VisualGraph().compile()


def test_visual_graph_removing_node_clears_its_connections():
    from f2orge.visual_graph import VisualGraph

    graph = VisualGraph()
    value = graph.add_node("Constant", "16")
    root = graph.add_node("Function", "sqrt")
    output = graph.add_node("Output", "length")
    graph.connect(value.id, root.id, 0)
    graph.connect(root.id, output.id, 0)

    graph.remove_node(root.id)

    assert (root.id, 0) not in graph.connections
    assert (output.id, 0) not in graph.connections


def test_visual_graph_shared_output_input_orders_assignments_and_runs_scripts():
    from f2orge.desktop import DesktopSession
    from f2orge.visual_graph import VisualGraph

    graph = VisualGraph()
    graph.add_node("Script", "eq Force { F = m * a }\nm = 2 kg\na = 3 m/s^2")
    two = graph.add_node("Constant", "2")
    three = graph.add_node("Constant", "3")
    five = graph.add_node("Add")
    graph.connect(two.id, five.id, 0)
    graph.connect(three.id, five.id, 1)
    downstream_input = graph.add_node("Input", "force")
    four = graph.add_node("Constant", "4")
    multiply = graph.add_node("Multiply")
    graph.connect(downstream_input.id, multiply.id, 0)
    graph.connect(four.id, multiply.id, 1)
    downstream_output = graph.add_node("Output", "result")
    graph.connect(multiply.id, downstream_output.id, 0)
    produced_output = graph.add_node("Output", "force")
    graph.connect(five.id, produced_output.id, 0)

    source = graph.compile()
    assert source.index("force =") < source.index("result =")
    session = DesktopSession()
    result, success = session.execute(source)
    assert success and result == "5\n20"
    assert session.interpreter.variables["force"].value == 5


def test_visual_graph_version_two_preserves_node_sizes_and_reads_legacy_files():
    from f2orge.visual_graph import VisualGraph

    graph = VisualGraph()
    script = graph.add_node("Script", "x = 2")
    script.width = 360
    script.height = 240
    restored = VisualGraph.from_data(graph.to_data())
    assert restored.nodes[script.id].width == 360
    assert restored.nodes[script.id].height == 240
    legacy = VisualGraph.from_data({
        "version": 1,
        "nodes": [{"id": 1, "kind": "Output", "value": "result", "x": 10, "y": 20}],
        "connections": [],
    })
    assert legacy.nodes[1].width == 190


def test_visual_graph_script_only_executes_full_forge_statements():
    from f2orge.desktop import DesktopSession
    from f2orge.visual_graph import VisualGraph

    graph = VisualGraph()
    graph.add_node("Script", "eq Area { A = w * h }\nprint \"ready\"\nsolve Area for A { w = 3 m\n h = 2 m }")
    compiled = graph.compile()
    session = DesktopSession()
    result, success = session.execute(compiled)
    assert success and result == "ready\nA = 6 m²"


def test_visual_graph_script_nodes_cannot_be_connected_as_expressions():
    from f2orge.errors import ForgeError
    from f2orge.visual_graph import VisualGraph

    graph = VisualGraph()
    script = graph.add_node("Script", "x = 1")
    output = graph.add_node("Output", "result")
    with pytest.raises(ForgeError, match="Script node has no output pin"):
        graph.connect(script.id, output.id, 0)


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


def test_a_matrix_may_span_several_lines():
    assert run("A = [\n  [1, 2]\n  [3, 4]\n]\nA") == ["[[1, 2], [3, 4]]"]
    assert run("A = [\n  [1, 2],\n  [3, 4]\n]\nA * <1, 1>") == ["<3, 7>"]


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
    ("for = 3", "Expected a loop variable name"),
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


def test_native_worksheet_defaults_outputs_and_graph_sweeps():
    source = '''worksheet Flight {
    description = "Newton's second law"
    input mass : kg = 150 kg "Vehicle mass"
    input acceleration : m/s^2 = 9.81 m/s^2
    output force = mass * acceleration
    graph force over acceleration from 0 m/s^2 to 20 m/s^2
}'''
    interpreter = Interpreter(out=lambda _text: None)
    interpreter.run(source)

    schema = interpreter.worksheet_schema("Flight")
    assert schema["description"] == "Newton's second law"
    assert schema["inputs"] == [
        {"name": "mass", "unit": "kg", "default": 150.0, "description": "Vehicle mass"},
        {"name": "acceleration", "unit": "m/s²", "default": 9.81, "description": ""},
    ]
    result = interpreter.evaluate_worksheet("Flight", {"mass": 50})
    assert result["inputs"] == {"mass": 50.0, "acceleration": 9.81}
    assert result["outputs"] == [{"name": "force", "value": "490.5 N"}]
    graph = result["graphs"][0]
    assert graph["xLabel"] == "acceleration (m/s²)"
    assert graph["yLabel"] == "force (N)"
    assert graph["points"][0] == (0, 0)
    assert graph["points"][-1] == (20, 1000)


def test_worksheet_rejects_input_defaults_with_incompatible_units():
    interpreter = Interpreter(out=lambda _text: None)
    with pytest.raises(UnitError, match="expects kg"):
        interpreter.run('''worksheet Invalid {
    input mass : kg = 5 m
    output weight = mass
}''')


def test_worksheet_rejects_unknown_sweep_inputs_and_outputs():
    interpreter = Interpreter(out=lambda _text: None)
    with pytest.raises(ForgeError, match="graph sweep 'speed' is not a worksheet input"):
        interpreter.run('''worksheet Invalid {
    input mass : kg = 5 kg
    output weight = mass
    graph weight over speed from 0 m/s to 10 m/s
}''')


def test_invalid_worksheet_redefinition_preserves_previous_definition():
    interpreter = Interpreter(out=lambda _text: None)
    interpreter.run('''worksheet Flight {
    input mass : kg = 150 kg
    output weight = mass * 9.81 m/s^2
}''')
    with pytest.raises(UnitError):
        interpreter.run('''worksheet Flight {
    input mass : kg = 5 m
    output weight = mass
}''')
    assert interpreter.evaluate_worksheet("Flight")["inputs"] == {"mass": 150.0}
