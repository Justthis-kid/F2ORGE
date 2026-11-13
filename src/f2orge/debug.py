"""Debugging and profiling for scripts: stepped execution, breakpoints, and a statement profile.

The debugger runs a program one statement at a time and calls back before each one, so the caller
can show the current line, inspect variables, and decide to continue, step, or stop.  Nothing here
needs threads or signals: the interpreter already exposes `execute` per statement, so a hook is
enough.

    session = DebugSession(source_text)
    while session.step():
        print(session.line, session.variables)

`profile()` measures where a program's time goes — per statement, so a slow loop is obvious — and
reports the number of times each line ran.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from . import syntax as S
from .errors import ForgeError, Source
from .interpreter import Interpreter
from .parser import parse


@dataclass
class Frame:
    """One statement about to run, with the variables visible at that moment."""

    statement: object
    line: int
    column: int
    kind: str
    source: str

    def __str__(self) -> str:
        return f"{self.line}: {self.source.strip()}"


def _describe(statement) -> str:
    names = {
        S.Assign: "assignment", S.MultiAssign: "assignment", S.ExprStmt: "expression",
        S.Print: "print", S.Plot: "plot", S.Convert: "convert", S.Solve: "solve",
        S.SolveSystem: "solve", S.EqDef: "equation", S.WorksheetDef: "worksheet",
        S.Import: "import", S.Export: "export", S.If: "if", S.While: "while", S.For: "for",
        S.Def: "function", S.Return: "return", S.Break: "break", S.Continue: "continue",
    }
    return next((label for cls, label in names.items() if isinstance(statement, cls)), "statement")


class DebugSession:
    """Run a program statement by statement, with breakpoints and an optional trace."""

    def __init__(self, text: str, name: str = "<debug>", *, base_dir=None,
                 echo: bool = False):
        self.source = Source(name, text)
        self.statements = self._flatten(parse(self.source))
        self.interpreter = Interpreter(base_dir=base_dir, out=lambda _line: None, echo=echo)
        self.index = 0
        self.breakpoints: set = set()  # 1-based source lines
        self.trace: List[Frame] = []
        self.finished = False
        self.error: Optional[ForgeError] = None

    def _flatten(self, statements) -> List[object]:
        """The statements of the program, with each block's body in order after its header.

        Stepping into a branch is what a reader expects: `if` shows its condition, then the body
        it takes.  Nested statements keep their own source spans, which is what the debugger shows.
        """
        out: List[object] = []
        for statement in statements:
            out.append(statement)
            for body in _bodies(statement):
                out.extend(self._flatten(body))
        return out

    # ---- stepping -------------------------------------------------------------------------
    @property
    def total(self) -> int:
        return len(self.statements)

    @property
    def current(self) -> Optional[Frame]:
        if self.index >= len(self.statements):
            return None
        statement = self.statements[self.index]
        span = getattr(statement, "span", None) or self.source_span()
        line, column = span.line_col
        return Frame(statement, line, column, _describe(statement), span.source.line_text(line))

    def source_span(self):
        from .errors import Span

        return Span(self.source, 0, 0)

    @property
    def variables(self) -> Dict[str, str]:
        return {name: str(value) for name, value in self.interpreter.variables.items()}

    def at_breakpoint(self) -> bool:
        frame = self.current
        return frame is not None and frame.line in self.breakpoints

    def step(self) -> bool:
        """Run the next statement.  False when the program has finished or stopped on an error."""
        if self.finished:
            return False
        frame = self.current
        if frame is None:
            self.finished = True
            return False
        self.trace.append(frame)
        self.index += 1
        try:
            self.interpreter.execute(frame.statement, frame.statement.span.source
                                     if getattr(frame.statement, "span", None) else self.source)
        except ForgeError as err:
            self.error = err
            self.finished = True
            return False
        return True

    def run_to_breakpoint(self) -> Optional[Frame]:
        """Run until a breakpoint, the end, or an error; returns the frame it stopped on."""
        while self.step():
            if self.at_breakpoint():
                return self.current
        return self.current

    def run(self) -> None:
        while self.step():
            pass

    def reset(self) -> None:
        self.index = 0
        self.trace.clear()
        self.finished = False
        self.error = None
        self.interpreter = Interpreter(base_dir=self.interpreter.base_dir, out=lambda _line: None)


def _bodies(statement) -> List[Tuple[object, ...]]:
    if isinstance(statement, S.If):
        return [body for _, body in statement.branches]
    if isinstance(statement, (S.While, S.For, S.Def)):
        return [statement.body]
    return []


# ---- profiling --------------------------------------------------------------------------------
@dataclass
class LineProfile:
    line: int
    source: str
    calls: int = 0
    seconds: float = 0.0


@dataclass
class Profile:
    """Where a program spends its time: one entry per source line, busiest first."""

    lines: List[LineProfile] = field(default_factory=list)
    total_seconds: float = 0.0
    error: Optional[ForgeError] = None

    def busiest(self, count: int = 10) -> List[LineProfile]:
        ordered = sorted(self.lines, key=lambda item: item.seconds, reverse=True)
        return [item for item in ordered if item.calls][:count]

    def report(self) -> str:
        """A table of the busiest lines, like a small profiler report."""
        rows = [f"{'ms':>10}  {'calls':>8}  line"]
        for item in self.busiest():
            rows.append(f"{item.seconds * 1000:10.2f}  {item.calls:8d}  {item.line:>4}  {item.source.strip()}")
        if not self.lines:
            rows.append("  (no statements ran)")
        rows.append(f"{self.total_seconds * 1000:10.2f}  total")
        return "\n".join(rows)


def profile(text: str, name: str = "<profile>", *, base_dir=None, runs: int = 1) -> Profile:
    """Run a program and measure the time each source line took, over `runs` repetitions.

    A statement is timed as it executes, so a line inside a loop is counted once per pass — that
    is what makes a hot loop visible.  Wall time is measured separately from the per-line times,
    so the difference is the interpreter's own overhead in the lines above the loop.
    """
    source = Source(name, text)
    statements = parse(source)
    entries: Dict[int, LineProfile] = {}
    for statement in _walk_statements(statements):
        span = getattr(statement, "span", None)
        line = span.line_col[0] if span is not None else 0
        if line and line not in entries:
            entries[line] = LineProfile(line, source.line_text(line))

    interpreter = _ProfilingInterpreter(entries, base_dir=base_dir)
    result = Profile(error=None)
    start = time.perf_counter()
    for _ in range(max(1, runs)):
        interpreter.reset()
        interpreter.run(text, name)
    result.total_seconds = time.perf_counter() - start
    result.lines = sorted(entries.values(), key=lambda item: item.line)
    result.error = interpreter.error
    return result


def _walk_statements(statements):
    """Every statement in a program, including the bodies of blocks (for the profile's lines)."""
    for statement in statements:
        yield statement
        for body in _bodies(statement):
            yield from _walk_statements(body)


class _ProfilingInterpreter(Interpreter):
    """An interpreter that adds each statement's running time to a line profile."""

    def __init__(self, entries: Dict[int, LineProfile], *, base_dir=None):
        super().__init__(base_dir=base_dir, out=lambda _line: None)
        self.entries = entries
        self.error: Optional[ForgeError] = None

    def reset(self) -> None:
        self.variables.clear()
        self.equations.clear()
        self.functions.clear()
        self._frames.clear()
        self.error = None

    def run(self, text: str, name: str = "<input>") -> None:
        try:
            super().run(text, name)
        except ForgeError as err:
            self.error = err

    def execute(self, statement, source: Source) -> None:
        span = getattr(statement, "span", None)
        entry = None
        if span is not None:
            line = span.line_col[0]
            entry = self.entries.get(line)
        began = time.perf_counter()
        try:
            super().execute(statement, source)
        finally:
            if entry is not None:
                entry.seconds += time.perf_counter() - began
                entry.calls += 1


def trace_of(text: str, name: str = "<trace>", *, base_dir=None) -> List[Frame]:
    """Every statement a program runs, in order — a readable execution trace."""
    session = DebugSession(text, name, base_dir=base_dir)
    session.run()
    return list(session.trace)
