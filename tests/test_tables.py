"""Script-level file I/O: readtable() and csvwrite() inside a .forge program."""
import pytest

from f2orge import Interpreter
from f2orge.errors import ForgeError, UnitError
from helpers import TempDir


def _run(base, src):
    out = []
    Interpreter(base_dir=base, out=out.append).run(src, "table.forge")
    return out


def _csv(base, name="data.csv"):
    (base / name).write_text(
        "time [s],distance [m],label\n0,0,start\n1,3,middle\n2,8,end\n", encoding="utf-8")


def test_headers_become_text_and_columns_carry_their_units():
    with TempDir() as d:
        _csv(d)
        assert _run(d, 't = readtable("data.csv")\nt[0]') == ["<time, distance, label>"]
        assert _run(d, 't = readtable("data.csv")\nt[1]') == ["<0 s, 1 s, 2 s>"]


def test_columns_behave_like_any_unit_aware_vector():
    with TempDir() as d:
        _csv(d)
        assert _run(d, 't = readtable("data.csv")\nsum(t[2])') == ["11 m"]
        assert _run(d, 't = readtable("data.csv")\nmean(t[2])') == ["3.666666667 m"]
        slope, intercept, r2 = _run(d, 't = readtable("data.csv")\nlinreg(t[1], t[2])')[0].strip("<>").split(", ", 2)
        assert slope.startswith("4 m/s") and r2.startswith("0.9795")


def test_text_columns_are_text():
    with TempDir() as d:
        _csv(d)
        assert _run(d, 't = readtable("data.csv")\nt[3]') == ["<start, middle, end>"]


def test_csvwrite_round_trips_a_table():
    with TempDir() as d:
        _csv(d)
        assert _run(d, 't = readtable("data.csv")\ncsvwrite("out.csv", t)') == ["wrote out.csv"]
        assert (d / "out.csv").read_text(encoding="utf-8") == (d / "data.csv").read_text(encoding="utf-8")
        assert _run(d, 'u = readtable("out.csv")\nsum(u[2])') == ["11 m"]


def test_headers_without_units_are_plain_numbers():
    with TempDir() as d:
        (d / "plain.csv").write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
        assert _run(d, 't = readtable("plain.csv")\nsum(t[1])') == ["4"]
        assert _run(d, 't = readtable("plain.csv")\nt[1]') == ["<1, 3>"]


def test_table_errors_explain_themselves():
    with TempDir() as d:
        with pytest.raises(ForgeError, match="cannot find the file"):
            _run(d, 'readtable("nope.csv")')
        (d / "ragged.csv").write_text("a,b\n1\n", encoding="utf-8")
        with pytest.raises(ForgeError, match="1 values but the header has 2"):
            _run(d, 'readtable("ragged.csv")')
        (d / "badunit.csv").write_text("mass [zzz]\n1\n", encoding="utf-8")
        with pytest.raises(ForgeError, match="not a unit"):
            _run(d, 'readtable("badunit.csv")')
        (d / "mixed.csv").write_text("a\n1\nx\n", encoding="utf-8")
        with pytest.raises(ForgeError, match="mixes numbers and text"):
            _run(d, 'readtable("mixed.csv")')


def test_paths_are_relative_to_the_program_and_folders_are_created():
    with TempDir() as d:
        _csv(d)
        assert _run(d, 't = readtable("data.csv")\ncsvwrite("reports/out.csv", t)') == ["wrote reports/out.csv"]
        assert (d / "reports" / "out.csv").is_file()
