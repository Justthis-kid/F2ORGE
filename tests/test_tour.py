"""The feature tour must keep running as the language grows."""
from f2orge import Interpreter
from helpers import ROOT


def test_the_tour_example_runs_from_first_line_to_last():
    source = (ROOT / "examples" / "tour.forge").read_text(encoding="utf-8")
    output = []
    Interpreter(base_dir=ROOT / "examples", out=output.append).run(source, "tour.forge")
    text = "\n".join(output)
    assert "Tour finished." in text
    assert "error" not in text.lower()


def test_a_complex_quantity_prints_its_unit_on_both_parts():
    out = []
    Interpreter(out=out.append).run("Z = 3 ohm + 4i ohm\nZ * 2 A", "t.forge")
    assert out == ["6 V + 8i V"]
