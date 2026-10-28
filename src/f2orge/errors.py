"""Error types and source-located diagnostics.

Every user-facing failure is a ForgeError.  When it carries a Span the report shows the offending
line with a caret underline, like a compiler:

    error: Unit mismatch
     --> main.forge:1:1
      |
    1 | 10 kg + 5 m
      | ^^^^^^^^^^^ cannot add mass (kg) and length (m)
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import List, Optional, Tuple


class Source:
    """A named piece of program text with fast offset -> (line, column) lookup."""

    __slots__ = ("name", "text", "_starts")

    def __init__(self, name: str, text: str):
        self.name = name
        self.text = text
        starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                starts.append(i + 1)
        self._starts = starts

    def line_col(self, offset: int) -> Tuple[int, int]:
        """1-based (line, column) of a character offset."""
        line = bisect.bisect_right(self._starts, offset) - 1
        return line + 1, offset - self._starts[line] + 1

    def line_text(self, line: int) -> str:
        start = self._starts[line - 1]
        end = self.text.find("\n", start)
        return self.text[start : end if end != -1 else len(self.text)].rstrip("\r")


@dataclass(frozen=True)
class Span:
    """A half-open character range [start, end) inside a Source."""

    source: Source
    start: int
    end: int

    @property
    def line_col(self) -> Tuple[int, int]:
        return self.source.line_col(self.start)

    def location(self) -> str:
        line, col = self.line_col
        return f"{self.source.name}:{line}:{col}"

    def join(self, other: "Span") -> "Span":
        return Span(self.source, min(self.start, other.start), max(self.end, other.end))

    @property
    def text(self) -> str:
        return self.source.text[self.start : self.end]


class ForgeError(Exception):
    """Base class for every error the language reports to the user."""

    title = "Error"

    def __init__(
        self,
        message: str,
        span: Optional[Span] = None,
        *,
        hint: Optional[str] = None,
        notes: Optional[List[str]] = None,
        title: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.span = span
        self.hint = hint
        self.notes: List[str] = list(notes or [])
        if title:
            self.title = title

    def __str__(self) -> str:  # plain one-line form, used by tests and logging
        return f"{self.title}: {self.message}"

    def format(self, color: bool = False) -> str:
        """Multi-line, compiler-style report."""

        def paint(text: str, code: str) -> str:
            return f"\x1b[{code}m{text}\x1b[0m" if color else text

        lines = [paint(f"error: {self.title}", "1;31")]
        pad = " "
        if self.span is None:
            lines.append(f"  {self.message}")
        else:
            src = self.span.source
            line, col = self.span.line_col
            pad = " " * len(str(line))
            text = src.line_text(line).replace("\t", " ")
            end_line, end_col = src.line_col(max(self.span.end - 1, self.span.start))
            length = (end_col - col + 1) if end_line == line else (len(text) - col + 1)
            length = max(1, length)
            bar = paint("|", "34")
            lines.append(f"{pad}{paint('-->', '34')} {src.name}:{line}:{col}")
            lines.append(f"{pad} {bar}")
            lines.append(f"{paint(str(line), '34')} {bar} {text}")
            lines.append(f"{pad} {bar} {' ' * (col - 1)}{paint('^' * length + ' ' + self.message, '31')}")
        for note in self.notes:
            lines.append(f"{pad} {paint('=', '34')} note: {note}")
        if self.hint:
            lines.append(f"{pad} {paint('=', '34')} hint: {self.hint}")
        return "\n".join(lines)


class ForgeSyntaxError(ForgeError):
    title = "Syntax error"


class UnitError(ForgeError):
    title = "Unit mismatch"


class ForgeNameError(ForgeError):
    title = "Unknown name"


class ForgeEvalError(ForgeError):
    title = "Math error"


class SolveError(ForgeError):
    title = "Cannot solve"


class ForgeImportError(ForgeError):
    title = "Import error"
