"""Blueprint nodes for the newer language features: Call, Compare, and two-output unpacking."""
import json

import pytest

from f2orge.desktop import DesktopSession
from f2orge.errors import ForgeError
from f2orge.visual_graph import NODE_INPUTS, VisualGraph
from helpers import ROOT


def _run(graph):
    """Compile and run a graph, returning its output lines."""
    output, success = DesktopSession().execute(graph.compile())
    assert success, output
    return output.splitlines()


def test_call_node_invokes_a_user_function():
    graph = VisualGraph()
    graph.add_node("Script", "def area(r) { return pi * r^2 }")
    radius = graph.add_node("Constant", "2 m")
    call = graph.add_node("Call", "area")
    out = graph.add_node("Output", "a")
    graph.connect(radius.id, call.id, 0)
    graph.connect(call.id, out.id, 0)
    assert graph.compile() == "def area(r) { return pi * r^2 }\na = area(2 m)\na"
    assert _run(graph)[0] == "12.56637061 m²"


def test_call_node_takes_one_pin_per_argument():
    graph = VisualGraph()
    first = graph.add_node("Constant", "<1, 0, 0>")
    second = graph.add_node("Constant", "<0, 1, 0>")
    call = graph.add_node("Call", "cross")
    out = graph.add_node("Output", "n")
    graph.connect(first.id, call.id, 0)
    graph.connect(second.id, call.id, 1)
    graph.connect(call.id, out.id, 0)
    assert "n = cross(<1, 0, 0>, <0, 1, 0>)" in graph.compile()
    assert _run(graph)[0] == "<0, 0, 1>"


def test_a_call_node_with_no_pins_is_a_bare_call():
    graph = VisualGraph()
    graph.add_node("Script", "def answer() { return 42 }")
    call = graph.add_node("Call", "answer")
    out = graph.add_node("Output", "a")
    graph.connect(call.id, out.id, 0)
    assert "a = answer()" in graph.compile()
    assert _run(graph) == ["42"]


def test_a_missing_argument_is_reported_when_the_graph_runs():
    graph = VisualGraph()
    graph.add_node("Script", "def area(r) { return pi * r^2 }")
    call = graph.add_node("Call", "area")
    out = graph.add_node("Output", "a")
    graph.connect(call.id, out.id, 0)
    output, success = DesktopSession().execute(graph.compile())
    assert not success and "area()" in output


def test_compare_node_compares_two_values():
    graph = VisualGraph()
    left = graph.add_node("Constant", "3 m")
    right = graph.add_node("Constant", "2 m")
    compare = graph.add_node("Compare", "<=")
    out = graph.add_node("Output", "small")
    graph.connect(left.id, compare.id, 0)
    graph.connect(right.id, compare.id, 1)
    graph.connect(compare.id, out.id, 0)
    assert "small = (3 m <= 2 m)" in graph.compile()
    assert _run(graph)[0] == "false"


@pytest.mark.parametrize("symbol,signed", [("lt", "<"), ("le", "<="), ("gt", ">"),
                                           ("ge", ">="), ("eq", "=="), ("ne", "!=")])
def test_compare_node_accepts_short_names(symbol, signed):
    graph = VisualGraph()
    graph.add_node("Compare", symbol)
    assert graph.nodes[1].value == signed


def test_compare_node_rejects_an_unknown_comparison():
    with pytest.raises(ForgeError, match="not a comparison"):
        VisualGraph().add_node("Compare", "~=")


def test_a_two_output_node_unpacks_several_results():
    graph = VisualGraph()
    graph.add_node("Script", "def pair() { return <1 m, 2 m> }")
    call = graph.add_node("Call", "pair")
    out = graph.add_node("Output2", "first, second")
    graph.connect(call.id, out.id, 0)
    assert graph.compile().endswith("[first, second] = pair()\nfirst\nsecond")
    assert _run(graph) == ["1 m", "2 m"]


def test_a_two_output_node_needs_two_valid_names():
    with pytest.raises(ForgeError, match="at least two names"):
        VisualGraph().add_node("Output2", "only")
    with pytest.raises(ForgeError, match="not a valid output variable name"):
        VisualGraph().add_node("Output2", "good, 9bad")


def test_new_nodes_survive_saving_and_reopening():
    graph = VisualGraph()
    graph.add_node("Call", "area")
    graph.add_node("Compare", "<=")
    graph.add_node("Output2", "a, b")
    restored = VisualGraph.from_data(json.loads(json.dumps(graph.to_data())))
    assert [node.kind for node in restored.nodes.values()] == ["Call", "Compare", "Output2"]
    assert restored.nodes[3].value == "a, b"


def test_the_ide_offers_the_new_nodes():
    html = (ROOT / "src" / "f2orge" / "web" / "index.html").read_text(encoding="utf-8")
    for kind in ("Call", "Compare", "Output2"):
        assert f'data-node="{kind}"' in html
    script = (ROOT / "src" / "f2orge" / "web" / "app.js").read_text(encoding="utf-8")
    assert "Call: 2" in script and "Compare: 2" in script and "Output2: 1" in script
    desktop = (ROOT / "src" / "f2orge" / "desktop.py").read_text(encoding="utf-8")
    assert '"Compare", "Output", "Output2"' in desktop


def test_node_input_counts_cover_every_kind():
    for kind, inputs in NODE_INPUTS.items():
        assert isinstance(inputs, int) and inputs >= 0, kind


# ---- magnitude comparisons -------------------------------------------------------------------
@pytest.mark.parametrize("symbol,call,expected", [
    ("mag<=", "less_equal_mag(3, 2 m)", "false"),
    ("mag<", "less_mag(3, 2 m)", "false"),
    ("mag>", "greater_mag(3, 2 m)", "true"),
    ("mag>=", "greater_equal_mag(3, 2 m)", "true"),
])
def test_a_compare_node_can_compare_magnitudes(symbol, call, expected):
    graph = VisualGraph()
    left = graph.add_node("Constant", "3")
    right = graph.add_node("Constant", "2 m")
    compare = graph.add_node("Compare", symbol)
    out = graph.add_node("Output", "r")
    graph.connect(left.id, compare.id, 0)
    graph.connect(right.id, compare.id, 1)
    graph.connect(compare.id, out.id, 0)
    assert f"r = {call}" in graph.compile()
    assert _run(graph) == [expected]


def test_a_plain_compare_node_stays_unit_safe():
    graph = VisualGraph()
    left = graph.add_node("Constant", "3")
    right = graph.add_node("Constant", "2 m")
    compare = graph.add_node("Compare", "<=")
    out = graph.add_node("Output", "r")
    graph.connect(left.id, compare.id, 0)
    graph.connect(right.id, compare.id, 1)
    graph.connect(compare.id, out.id, 0)
    assert "r = (3 <= 2 m)" in graph.compile()
    output, success = DesktopSession().execute(graph.compile())
    assert not success and "cannot compare" in output


def test_an_unknown_compare_symbol_names_what_was_wrong():
    with pytest.raises(ForgeError, match="'~=' is not a comparison"):
        VisualGraph().add_node("Compare", "~=")
