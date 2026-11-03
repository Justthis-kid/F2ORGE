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
class VectorLiteral:
    items: Tuple[object, ...]
    span: Optional[Span] = None


@dataclass(frozen=True)
class MatrixLiteral:
    rows: Tuple[Tuple[object, ...], ...]
    span: Optional[Span] = None


def children(node) -> Iterator[object]:
    if isinstance(node, VectorLiteral):
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
class Solve:
    eq: str
    target: str
    givens: Tuple[Tuple[str, object, Optional[Span]], ...]
    span: Optional[Span] = None
    eq_span: Optional[Span] = None
    target_span: Optional[Span] = None


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
