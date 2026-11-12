"""Abstract syntax tree.  Every node remembers its Span so errors can point at the source."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, List, Optional, Tuple

from .errors import Span
from .units import Unit


# ---- expressions ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Number:
    value: float
    span: Optional[Span] = None


@dataclass(frozen=True)
class QuantityLit:
    value: float
    unit: Unit
    span: Optional[Span] = None


@dataclass(frozen=True)
class StringLit:
    value: str
    span: Optional[Span] = None


@dataclass(frozen=True)
class Name:
    name: str
    span: Optional[Span] = None


@dataclass(frozen=True)
class Unary:
    op: str
    operand: object
    span: Optional[Span] = None


@dataclass(frozen=True)
class Binary:
    op: str
    left: object
    right: object
    span: Optional[Span] = None


@dataclass(frozen=True)
class Call:
    func: str
    args: Tuple[object, ...] = ()
    kwargs: Tuple[Tuple[str, object, Optional[Span]], ...] = ()  # (name, expr, name span)
    span: Optional[Span] = None
    func_span: Optional[Span] = None


@dataclass(frozen=True)
class Member:
    obj: object
    attr: str
    span: Optional[Span] = None


@dataclass(frozen=True)
class Index:
    obj: object
    indices: Tuple[object, ...]
    span: Optional[Span] = None
    count: Optional[object] = None  # the n in M[:, j:j+n] — a counted selection


@dataclass(frozen=True)
class VectorLiteral:
    items: Tuple[object, ...]
    span: Optional[Span] = None


@dataclass(frozen=True)
class MatrixLiteral:
    rows: Tuple[Tuple[object, ...], ...]
    span: Optional[Span] = None


@dataclass(frozen=True)
class ListLiteral:
    """[a, b, c]: vectors joined into one vector, or matrices joined into more rows."""

    items: Tuple[object, ...]
    span: Optional[Span] = None


def children(node) -> Iterator[object]:
    if isinstance(node, VectorLiteral):
        yield from node.items
    elif isinstance(node, ListLiteral):
        yield from node.items
    elif isinstance(node, MatrixLiteral):
        for row in node.rows:
            yield from row
    elif isinstance(node, Unary):
        yield node.operand
    elif isinstance(node, Binary):
        yield node.left
        yield node.right
    elif isinstance(node, Call):
        yield from node.args
        for _, expr, _ in node.kwargs:
            yield expr
    elif isinstance(node, Member):
        yield node.obj
    elif isinstance(node, Index):
        yield node.obj
        yield from node.indices
        if node.count is not None:
            yield node.count


def walk(node) -> Iterator[object]:
    yield node
    for child in children(node):
        yield from walk(child)


def names_in(node) -> List[str]:
    """Variable names used by an expression, in order of first appearance."""
    seen: List[str] = []
    for n in walk(node):
        if isinstance(n, Name) and n.name not in seen:
            seen.append(n.name)
    return seen


def count_name(node, name: str) -> int:
    return sum(1 for n in walk(node) if isinstance(n, Name) and n.name == name)


# ---- equation bodies ------------------------------------------------------------------------
@dataclass(frozen=True)
class Meta:
    key: str
    value: str
    span: Optional[Span] = None


@dataclass(frozen=True)
class Decl:
    name: str
    unit: Unit
    doc: Optional[str] = None
    span: Optional[Span] = None


@dataclass(frozen=True)
class Relation:
    lhs: object
    rhs: object
    span: Optional[Span] = None


# ---- statements -----------------------------------------------------------------------------
@dataclass(frozen=True)
class Assign:
    name: str
    expr: object
    span: Optional[Span] = None


@dataclass(frozen=True)
class ExprStmt:
    expr: object
    span: Optional[Span] = None


@dataclass(frozen=True)
class Print:
    items: Tuple[object, ...]
    span: Optional[Span] = None


@dataclass(frozen=True)
class Convert:
    expr: object
    unit: Unit
    span: Optional[Span] = None


@dataclass(frozen=True)
class Plot:
    """plot(y), plot(x, y), plot(x, y1, y2), plot(theta, r, polar = true),
    plot(xs, ys, z, kind = "heatmap")."""

    ys: Tuple[object, ...]
    x: Optional[object] = None
    polar: bool = False
    kind: str = "plot"
    span: Optional[Span] = None


@dataclass(frozen=True)
class Solve:
    eq: str
    target: str
    givens: Tuple[Tuple[str, object, Optional[Span]], ...]
    span: Optional[Span] = None
    eq_span: Optional[Span] = None
    target_span: Optional[Span] = None


@dataclass(frozen=True)
class SolveSystem:
    """solve a, b for x, y { ... }: find several unknowns of several equations at once."""

    equations: Tuple[str, ...]
    unknowns: Tuple[str, ...]
    givens: Tuple[Tuple[str, object, Optional[Span]], ...] = ()
    span: Optional[Span] = None
    name_spans: Tuple[Span, ...] = ()
    unknown_spans: Tuple[Span, ...] = ()


@dataclass(frozen=True)
class Import:
    target: str
    is_path: bool
    span: Optional[Span] = None


@dataclass(frozen=True)
class Export:
    name: str
    span: Optional[Span] = None


@dataclass(frozen=True)
class EqDef:
    name: str
    items: Tuple[object, ...]
    span: Optional[Span] = None
    name_span: Optional[Span] = None


@dataclass(frozen=True)
class WorksheetInput:
    name: str
    unit: Unit
    default: object
    doc: Optional[str] = None
    span: Optional[Span] = None


@dataclass(frozen=True)
class WorksheetOutput:
    name: str
    expr: object
    span: Optional[Span] = None


@dataclass(frozen=True)
class WorksheetGraph:
    output: str
    variable: str
    start: object
    stop: object
    span: Optional[Span] = None


@dataclass(frozen=True)
class WorksheetDef:
    name: str
    items: Tuple[object, ...]
    span: Optional[Span] = None
    name_span: Optional[Span] = None


# ---- control flow ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Range:
    """a..b or a..b..step: the values of a for loop (a range step of 1 is implied)."""

    start: object
    stop: object
    step: Optional[object] = None
    span: Optional[Span] = None


@dataclass(frozen=True)
class If:
    """if / elseif / else.  `branches` holds (condition, body); an else is the final
    branch with a None condition."""

    branches: Tuple[Tuple[object, Tuple[object, ...]], ...]
    span: Optional[Span] = None


@dataclass(frozen=True)
class While:
    condition: object
    body: Tuple[object, ...]
    span: Optional[Span] = None


@dataclass(frozen=True)
class For:
    """for name in iterable { body } — one loop variable over a vector, matrix, or text."""

    name: str
    iterable: object
    body: Tuple[object, ...]
    span: Optional[Span] = None
    name_span: Optional[Span] = None


@dataclass(frozen=True)
class Def:
    """def name(p1, p2, p3 = default) { body }

    Every parameter is positional except the last, which may have a plain-number default.
    Strings are values in this language, so p1 defaulting to "X" returns a string.
    """

    name: str
    params: Tuple[str, ...]
    default: Optional[object]
    body: Tuple[object, ...]
    span: Optional[Span] = None
    name_span: Optional[Span] = None


@dataclass(frozen=True)
class Return:
    value: object
    span: Optional[Span] = None


@dataclass(frozen=True)
class Break:
    span: Optional[Span] = None


@dataclass(frozen=True)
class Continue:
    span: Optional[Span] = None
