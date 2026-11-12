"""Script-level file I/O: read and write CSV tables from inside a .forge program.

A table is a vector of columns.  The first value is a vector of the column headers (text), and each
following value is a vector holding one column's values: quantities when every cell in that column
is a number (optionally with a unit written in the header, `time [s]`), text otherwise.  That shape
needs no new value type — `columns(t)[1]` is the first data column — and it keeps unit checking: a
column read as `[m]` holds metres, so `sum(columns(t)[1])` is a length.

    t = readtable("data.csv")     # local file, relative to the program
    columns(t)                    # <<"time", "distance">, <...>, <...>>
    header = t[0]                 # <"time", "distance">
    times = t[1]                  # <0 s, 1 s, 2 s>
    csvwrite("out.csv", t)        # write the same shape back
"""
from __future__ import annotations

import csv
import io
import re
from fractions import Fraction
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .dimensions import Dim
from .errors import ForgeError, ForgeEvalError, Source, Span, UnitError
from .linear_algebra import Matrix, Vector
from .parser import parse_text
from .printer import format_number
from .quantity import Quantity
from .text import Text, as_text
from .units import Unit, lookup_unit

_HEADER_UNIT = re.compile(r"^\s*(.*?)\s*\[([^\]]*)\]\s*$")


class TableError(ForgeError):
    title = "Table error"


def parse_unit(text: str, where: str, span: Optional[Span]) -> Optional[Unit]:
    """The unit written in a column header's brackets, such as the `s` of `time [s]`."""
    if not text.strip():
        return None
    try:
        # `x : s` is a declaration, whose unit runs to the end of the line.  Parsing it with the
        # real parser keeps the header's unit spelled exactly as the language spells units.
        # A declaration lives inside an equation, so `x : s` is read there, by the real parser, to
        # keep headers' units spelled exactly as the language spells units.
        from . import syntax as S

        statements = parse_text(f"eq Column {{\n    x : {text.strip()}\n    y = x\n}}\n", where)
        if len(statements) != 1 or not isinstance(statements[0], S.EqDef):
            raise ValueError
        return statements[0].items[0].unit
    except (ForgeError, ValueError):
        raise TableError(f"'{text}' in a column header is not a unit", span,
                         hint="Write a header such as 'time [s]', or leave the brackets off.") from None


def _number_or_text(cell: str, unit: Optional[Unit], column: str, span: Optional[Span]) -> object:
    stripped = cell.strip()
    if not stripped:
        return Text("")
    try:
        value = float(stripped.replace("_", ""))
    except ValueError:
        return Text(stripped)
    return Quantity.from_unit(value, unit) if unit is not None else Quantity(value)


def read_table(text: str, name: str = "<table>", span: Optional[Span] = None) -> Vector:
    """Parse CSV text into a table: headers first, then one vector per column."""
    rows = [row for row in csv.reader(io.StringIO(text)) if any(cell.strip() for cell in row)]
    if not rows:
        raise TableError("this file holds no rows", span, hint="The first row names the columns.")
    header, body = rows[0], rows[1:]
    width = len(header)
    for index, row in enumerate(body, start=2):
        if len(row) != width:
            raise TableError(
                f"row {index} of {name} has {len(row)} values but the header has {width}",
                span, hint="Every row needs one value for each column.")
    names: List[str] = []
    units: List[Optional[Unit]] = []
    for title in header:
        match = _HEADER_UNIT.match(title)
        if match:
            names.append(match.group(1).strip() or f"column {len(names) + 1}")
            units.append(parse_unit(match.group(2), name, span))
        else:
            names.append(title.strip() or f"column {len(names) + 1}")
            units.append(None)
    columns: List[object] = [Vector(tuple(Text(title) for title in names))]
    for position, unit in enumerate(units):
        cells = [row[position] if position < len(row) else "" for row in body]
        values = [_number_or_text(cell, unit, names[position], span) for cell in cells]
        numeric = [value for value in values if isinstance(value, Quantity)]
        if numeric and len(numeric) != len(values):
            raise TableError(
                f"column '{names[position]}' mixes numbers and text", span,
                hint="A column is either all numbers or all text; blank cells count as text.")
        if numeric and unit is not None and any(value.dim != unit.dim for value in numeric):
            raise UnitError(f"column '{names[position]}' is not all {unit.symbol()}", span)
        columns.append(Vector(tuple(values)))
    return Vector(tuple(columns))


def write_table(table: object, span: Optional[Span] = None) -> str:
    """Render a table (headers plus column vectors) as CSV text."""
    if not isinstance(table, Vector) or not table.items:
        raise TableError("csvwrite() needs a table such as readtable() returns", span)
    header_value = table.items[0]
    if not isinstance(header_value, Vector) or any(
            not isinstance(title, (Text, Quantity)) for title in header_value.items):
        raise TableError("the first value of a table must be a vector of column names", span,
                         hint="Build it with readtable(), or write <\"a\", \"b\"> first.")
    names = [as_text(title) for title in header_value.items]
    columns = table.items[1:]
    for index, column in enumerate(columns):
        if not isinstance(column, Vector):
            raise TableError(f"value {index + 2} of a table is not a column vector", span)
        if len(column.items) != len(columns[0].items):
            raise TableError("every column of a table needs the same number of values", span)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    titles = []
    for original, column in zip(header_value.items, columns):
        text = as_text(original)
        unit = _column_unit(column)
        titles.append(f"{text} [{unit.symbol(ascii_only=True)}]" if unit is not None and unit.symbol() else text)
    writer.writerow(titles)
    for row in range(len(columns[0].items) if columns else 0):
        writer.writerow([_cell_text(column.items[row]) for column in columns])
    return out.getvalue()


def _column_unit(column: Vector) -> Optional[Unit]:
    for item in column.items:
        if isinstance(item, Quantity) and not item.dim.is_dimensionless:
            return item.unit or Unit.from_dim(item.dim)
    return None


def _cell_text(value: object) -> str:
    if isinstance(value, Quantity):
        if value.unit is not None:
            return format_number(value.magnitude(value.unit))
        return format_number(value.value)
    return as_text(value)


def resolve_path(base: Path, name: str, span: Optional[Span], writing: bool = False) -> Path:
    """Where a script's relative file path points: next to the program."""
    path = Path(name).expanduser()
    if not path.is_absolute():
        path = base / path
    if writing:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as err:  # pragma: no cover - depends on the filesystem
            raise ForgeError(f"cannot create {path.parent}: {err}", span, title="Cannot write file") from None
    return path


def read_table_file(path: Path, span: Optional[Span] = None) -> Vector:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise ForgeError(f"cannot find the file '{path.name}'", span, title="Cannot read file",
                         hint="Paths are relative to the program; check the name and folder.") from None
    except OSError as err:
        raise ForgeError(f"cannot read {path}: {err}", span, title="Cannot read file") from None
    return read_table(text, path.name, span)


def write_table_file(path: Path, table: object, span: Optional[Span] = None) -> None:
    text = write_table(table, span)
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as err:
        raise ForgeError(f"cannot write {path}: {err}", span, title="Cannot write file") from None
