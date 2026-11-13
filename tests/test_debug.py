"""Debugging and profiling: stepping, breakpoints, traces, and line profiles."""
from f2orge.debug import DebugSession, profile, trace_of
from f2orge.errors import UnitError
from helpers import ROOT, forge

LOOP = """total = 0
for k in 1..4 {
    total = total + k
}
if total > 5 {
    print "big"
} else {
    print "small"
}
total"""


def test_a_trace_lists_every_statement_the_program_runs():
    trace = trace_of(LOOP)
    assert [frame.line for frame in trace] == [1, 2, 3, 5, 6, 8, 10]
    assert [frame.kind for frame in trace[:3]] == ["assignment", "for", "assignment"]
    assert trace[0].source.strip() == "total = 0"


def test_stepping_runs_one_statement_at_a_time_and_shows_variables():
    session = DebugSession("x = 2\ny = x * 3\ny")
    assert session.current.line == 1 and session.variables == {}
    assert session.step()
    assert session.current.line == 2 and session.variables == {"x": "2"}
    assert session.step()
    assert session.variables == {"x": "2", "y": "6"}


def test_breakpoints_stop_the_session_before_a_line_runs():
    session = DebugSession(LOOP)
    session.breakpoints = {3}
    frame = session.run_to_breakpoint()
    assert frame is not None and frame.line == 3
    assert "total" in session.variables  # line 1 has run, line 3 has not


def test_an_error_stops_the_session_and_is_kept():
    session = DebugSession("x = 1\n10 kg + 5 m")
    session.run()
    assert isinstance(session.error, UnitError)
    assert len(session.trace) == 2


def test_a_profile_counts_each_statement_as_often_as_it_runs():
    result = profile(LOOP)
    by_line = {item.line: item for item in result.lines}
    assert by_line[3].calls == 4  # the loop body, once per pass
    assert by_line[1].calls == 1
    assert result.total_seconds > 0
    assert "calls" in result.report() and "total" in result.report()


def test_a_profile_reports_an_error_but_keeps_the_times():
    result = profile("x = 1\n10 kg + 5 m")
    assert isinstance(result.error, UnitError)
    assert any(item.calls for item in result.lines)


def test_trace_and_profile_commands_run_from_the_terminal():
    r = forge("trace", str(ROOT / "examples" / "basics.forge"))
    assert r.returncode == 0 and "assignment" in r.stdout and "statements ran" in r.stdout
    r = forge("profile", str(ROOT / "examples" / "basics.forge"))
    assert r.returncode == 0 and "ms" in r.stdout and "calls" in r.stdout
