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
def test_every_example_the_readme_names_exists():
    """The README's commands point at real files; a rename must not leave dead paths behind."""
    import re

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    named = set(re.findall(r"examples[/\\][A-Za-z0-9_./\\-]+\.(?:forge|eq)", readme))
    assert named, "the README should name at least one example"
    missing = [name for name in sorted(named) if not (ROOT / name.replace("\\", "/")).is_file()]
    assert not missing, f"the README names files that do not exist: {missing}"


def test_the_readme_launch_block_names_the_tour_and_the_debug_commands():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    launch = readme.split("Run a program, start the interactive shell", 1)[1].split("```", 2)[1]
    for line in ("examples/tour.forge", "examples/objects.forge", "forge trace", "forge profile",
                 "forge ide", "forge browser"):
        assert line in launch, line
