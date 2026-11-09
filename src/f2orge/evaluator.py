"""Expression evaluation with unit safety.

Every operation goes through Quantity, so `10 kg + 5 m` fails with a UnitError no matter how
deeply it is nested.  Errors raised without a location are given the span of the expression
node being evaluated, which is how the caret ends up under the right piece of source.
"""
from __future__ import annotations

import difflib
import math
from fractions import Fraction
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from . import syntax as S
from .constants import CONSTANTS
from .dimensions import ANGLE, DIMLESS, describe_full
from .errors import ForgeError, ForgeEvalError, ForgeNameError, ForgeSyntaxError, Span, UnitError
from .linear_algebra import (
    Matrix, Value, Vector, add as add_linear, cross, determinant, divide as divide_linear,
    index as index_linear, inverse, make_matrix, make_vector, multiply as multiply_linear, negate,
    subtract as subtract_linear, transpose,
)
from .quantity import Quantity
from .units import lookup_unit


class UndefinedVariable(ForgeNameError):
    """A plain variable lookup failed (as opposed to an unknown function or equation)."""


class Scope:
    """Variable lookup: explicit values first, then built-in constants.

    `excluded` names are never taken from the constants: an equation that declares `R : ohm`
    gets its own R rather than the molar gas constant.
    """

    def __init__(self, values: Optional[Dict[str, Value]] = None, excluded: Iterable[str] = (),
                 constants: bool = True):
        self.values: Dict[str, Value] = values if values is not None else {}
        self.excluded = frozenset(excluded)
        self.constants = constants

    def get(self, name: str) -> Optional[Value]:
        if name in self.values:
            return self.values[name]
        if self.constants and name not in self.excluded:
            return CONSTANTS.get(name)
        return None

    def set(self, name: str, value: Value) -> None:
        self.values[name] = value

    def names(self) -> List[str]:
        names = list(self.values)
        if self.constants:
            names += [n for n in CONSTANTS if n not in self.excluded]
        return names


# name -> (min args, max args)
ARITY = {
    "sin": (1, 1), "cos": (1, 1), "tan": (1, 1), "asin": (1, 1), "acos": (1, 1), "atan": (1, 1),
    "atan2": (2, 2), "exp": (1, 1), "ln": (1, 1), "log": (1, 1), "sqrt": (1, 1), "abs": (1, 1),
    "min": (2, 99), "max": (2, 99), "inverse": (1, 1), "transpose": (1, 1),
    "cross": (2, 2), "det": (1, 1), "sum": (1, 1), "mean": (1, 1),
    "std": (1, 1), "median": (1, 1), "floor": (1, 1), "ceil": (1, 1),
    "round": (1, 2), "log2": (1, 1), "linspace": (3, 3), "range": (1, 3),
    "db": (1, 1), "undb": (1, 1),
}
FUNCTIONS = tuple(ARITY)


def _suggest(name: str, candidates: Iterable[str]) -> Optional[str]:
    close = difflib.get_close_matches(name, list(candidates), n=3, cutoff=0.6)
    return ("Did you mean " + " or ".join(f"'{c}'" for c in close) + "?") if close else None


class Evaluator:
    MAX_DEPTH = 64

    def __init__(self, lookup_equation: Callable[[str], object]):
        self.lookup_equation = lookup_equation
        self.depth = 0
        self.equation_names: Callable[[], List[str]] = lambda: []
        self.import_hint: Callable[[str], Optional[str]] = lambda name: None  # set by the Interpreter

    # ---- entry point -----------------------------------------------------------------------
    def eval(self, node, scope: Scope):
        try:
            return self._eval(node, scope)
        except ForgeError as err:
            if err.span is None and getattr(node, "span", None) is not None:
                err.span = node.span
            raise

    def _eval(self, node, scope: Scope):
        if isinstance(node, S.Number):
            return Quantity(node.value)
        if isinstance(node, S.QuantityLit):
            return Quantity.from_unit(node.value, node.unit)
        if isinstance(node, S.Name):
            value = scope.get(node.name)
            if value is None:
                raise self._undefined(node.name, node.span, scope)
            return value
        if isinstance(node, S.Unary):
            return negate(self.eval(node.operand, scope))
        if isinstance(node, S.Binary):
            left = self.eval(node.left, scope)
            right = self.eval(node.right, scope)
            if node.op == "+":
                return add_linear(left, right)
            if node.op == "-":
                return subtract_linear(left, right)
            if node.op == "*":
                return multiply_linear(left, right)
            if node.op == "/":
                return divide_linear(left, right)
            if not isinstance(left, Quantity) or not isinstance(right, Quantity):
                raise ForgeEvalError("vectors and matrices cannot be raised to a power", node.span)
            return left ** right
        if isinstance(node, S.VectorLiteral):
            return make_vector([self.eval(item, scope) for item in node.items])
        if isinstance(node, S.MatrixLiteral):
            return make_matrix([[self.eval(item, scope) for item in row] for row in node.rows])
        if isinstance(node, S.Call):
            if node.func in ARITY:
                return self._call_function(node, scope)
            eq, values = self.call_equation(node, scope)
            return values[eq.primary]
        if isinstance(node, S.Index):
            return index_linear(self.eval(node.obj, scope), [self.eval(item, scope) for item in node.indices])
        if isinstance(node, S.Member):
            if isinstance(node.obj, S.Call) and node.obj.func not in ARITY:
                eq, values = self.call_equation(node.obj, scope)
                if node.attr not in values:
                    raise ForgeNameError(
                        f"{eq.name} has no output named '{node.attr}'", node.span,
                        hint=f"Its outputs are: {', '.join(eq.outputs)}")
                return values[node.attr]
            raise ForgeSyntaxError("Only the result of an equation call has named outputs", node.span,
                                   hint="For example: Force(m = 2 kg, a = 3 m/s^2).F")
        if isinstance(node, S.StringLit):
            raise ForgeSyntaxError("Text can only be used with print and in equation metadata", node.span)
        raise TypeError(f"cannot evaluate {node!r}")  # pragma: no cover

    # ---- names -----------------------------------------------------------------------------
    def _undefined(self, name: str, span: Optional[Span], scope: Scope) -> ForgeNameError:
        parts: List[str] = []
        if lookup_unit(name) is not None:
            parts.append(f"'{name}' is a unit. Write a unit joined to its number, like 5 {name} or 5 m/s "
                         f"(units inside a quantity cannot have spaces around / or *).")
        elif self.lookup_equation(name) is not None:
            parts.append(f"'{name}' is an equation. Call it with named values: {name}(x = ..., y = ...).")
        else:
            tip = _suggest(name, scope.names())
            if tip:
                parts.append(tip)
        return UndefinedVariable(f"'{name}' is not defined", span, hint=" ".join(parts) or None)

    # ---- built-in functions ----------------------------------------------------------------
    def _call_function(self, node: S.Call, scope: Scope):
        name = node.func
        if node.kwargs:
            raise ForgeSyntaxError(f"{name}() takes plain values, not name = value pairs", node.span)
        args = [self.eval(a, scope) for a in node.args]
        lo, hi = ARITY[name]
        if not lo <= len(args) <= hi:
            want = f"{lo}" if lo == hi else f"{lo} or more"
            raise ForgeSyntaxError(f"{name}() takes {want} value(s) but got {len(args)}", node.span)
        return _apply(name, args)

    # ---- equation calls --------------------------------------------------------------------
    def call_equation(self, node: S.Call, scope: Scope):
        eq = self.lookup_equation(node.func)
        if eq is None:
            tip = _suggest(node.func, list(ARITY) + list(self.equation_names())) or self.import_hint(node.func)
            raise ForgeNameError(f"'{node.func}' is not a function or an equation", node.func_span or node.span,
                                 hint=tip)
        if node.args:
            raise ForgeSyntaxError(
                f"{eq.name}() needs named values", node.span,
                hint=f"Write: {eq.name}({', '.join(i + ' = ...' for i in eq.inputs)})", )
        args: Dict[str, Tuple[Quantity, Optional[Span]]] = {}
        for name, expr, name_span in node.kwargs:
            if name in args:
                raise ForgeSyntaxError(f"'{name}' is given twice in this call", name_span)
            args[name] = (self.eval(expr, scope), getattr(expr, "span", None) or name_span)
        if self.depth >= self.MAX_DEPTH:
            raise ForgeEvalError("equations are calling each other too deeply (is there a loop?)", node.span)
        self.depth += 1
        try:
            return eq, eq.call(self, args, node.span)
        finally:
            self.depth -= 1


# ---- function table -----------------------------------------------------------------------
def _dimless(q: Quantity, fname: str, what: str = "a plain number") -> float:
    if not q.dim.is_dimensionless:
        raise UnitError(f"{fname}() needs {what}, found {describe_full(q.dim)}",
                        hint="Divide by a reference quantity first, e.g. ln(x / x0).")
    return q.value


def _apply(name: str, args: List[object]):
    if name == "transpose":
        if not isinstance(args[0], Matrix):
            raise ForgeEvalError("transpose() requires a matrix")
        return transpose(args[0])
    if name == "inverse":
        if not isinstance(args[0], Matrix):
            raise ForgeEvalError("inverse() requires a matrix")
        return inverse(args[0])
    if name == "det":
        if not isinstance(args[0], Matrix):
            raise ForgeEvalError("det() requires a matrix")
        return determinant(args[0])
    if name == "cross":
        if not all(isinstance(arg, Vector) for arg in args):
            raise ForgeEvalError("cross() requires two vectors")
        return cross(args[0], args[1])
    if name in ("sum", "mean", "std", "median"):
        value = args[0]
        if not isinstance(value, Vector):
            raise ForgeEvalError(f"{name}() requires a vector")
        items = value.items
        first = items[0]
        if any(item.dim != first.dim for item in items):
            raise UnitError(f"{name}() requires vector elements with matching units")
        if name == "sum":
            total = first
            for item in items[1:]:
                total = total + item
            return total
        numbers = sorted(item.value for item in items)
        if name == "mean":
            return Quantity(sum(numbers) / len(numbers), first.dim, first.unit)
        if name == "median":
            middle = len(numbers) // 2
            median = numbers[middle] if len(numbers) % 2 else (numbers[middle - 1] + numbers[middle]) / 2
            return Quantity(median, first.dim, first.unit)
        mean = sum(numbers) / len(numbers)
        return Quantity(math.sqrt(sum((number - mean) ** 2 for number in numbers) / len(numbers)), first.dim, first.unit)
    if name == "linspace":
        start, stop, count = args
        n = _plain_integer(count, "linspace() sample count")
        if n < 1 or n > 100000:
            raise ForgeEvalError("linspace() sample count must be between 1 and 100000")
        if start.dim != stop.dim:
            raise UnitError("linspace() endpoints must have matching units")
        if n == 1:
            return Vector((start,))
        return Vector(tuple(Quantity(start.value + i * (stop.value - start.value) / (n - 1), start.dim,
                                    start.unit) for i in range(n)))
    if name == "range":
        if len(args) == 1:
            start, stop, step = Quantity(0), args[0], Quantity(1)
        elif len(args) == 2:
            start, stop, step = args[0], args[1], Quantity(1)
        else:
            start, stop, step = args
        if start.is_plain and stop.dim != DIMLESS:
            start = Quantity(start.value, stop.dim, stop.unit)
        if start.dim != stop.dim:
            raise UnitError("range() start and stop must have compatible units")
        if step.is_plain and start.dim != DIMLESS:
            step = Quantity(step.value, start.dim, start.unit)
        if step.dim != start.dim:
            raise UnitError("range() step must have compatible units")
        if step.value == 0:
            raise ForgeEvalError("range() step cannot be zero")
        values = []
        current = start.value
        predicate = (lambda x: x < stop.value) if step.value > 0 else (lambda x: x > stop.value)
        while predicate(current):
            if len(values) >= 100000:
                raise ForgeEvalError("range() is limited to 100000 values")
            values.append(Quantity(current, start.dim, start.unit))
            current += step.value
        return Vector(tuple(values))
    if name == "db":
        q = args[0]
        if q.value <= 0 or not q.dim.is_dimensionless:
            raise UnitError("db() requires a positive dimensionless ratio")
        return Quantity(10 * math.log10(q.value), lookup_unit("dB").dim, lookup_unit("dB"))
    if name == "undb":
        q = args[0]
        if q.dim != lookup_unit("dB").dim:
            raise UnitError("undb() requires a dB value")
        return Quantity(10 ** (q.value / 10))
    if name in ("floor", "ceil", "round"):
        q = args[0]
        if not q.dim.is_dimensionless:
            raise UnitError(f"{name}() requires a dimensionless value")
        digits = _plain_integer(args[1], "round() digits") if len(args) == 2 else 0
        value = math.floor(q.value) if name == "floor" else math.ceil(q.value) if name == "ceil" else round(q.value, digits)
        return Quantity(value)
    if name == "log2":
        x = _dimless(args[0], name)
        if x <= 0:
            raise ForgeEvalError("log2() needs a positive number")
        return Quantity(math.log2(x))
    if not all(isinstance(arg, Quantity) for arg in args):
        raise ForgeEvalError(f"{name}() requires scalar quantities")
    try:
        if name in ("sin", "cos", "tan"):
            q = args[0]
            if q.dim not in (DIMLESS, ANGLE):
                raise UnitError(f"{name}() needs an angle or a plain number, found {describe_full(q.dim)}")
            return Quantity({"sin": math.sin, "cos": math.cos, "tan": math.tan}[name](q.value))
        if name in ("asin", "acos"):
            x = _dimless(args[0], name)
            if not -1.0 <= x <= 1.0:
                raise ForgeEvalError(f"{name}() needs a value between -1 and 1, found {x:g}")
            return Quantity(math.asin(x) if name == "asin" else math.acos(x))
        if name == "atan":
            return Quantity(math.atan(_dimless(args[0], name)))
        if name == "atan2":
            y, x = args
            if y.dim != x.dim:
                raise UnitError(f"atan2() needs two values of the same kind, found {describe_full(y.dim)} "
                                f"and {describe_full(x.dim)}")
            return Quantity(math.atan2(y.value, x.value))
        if name == "exp":
            return Quantity(math.exp(_dimless(args[0], name)))
        if name in ("ln", "log"):
            x = _dimless(args[0], name)
            if x <= 0:
                raise ForgeEvalError(f"{name}() needs a positive number, found {x:g}")
            return Quantity(math.log(x) if name == "ln" else math.log10(x))
        if name == "sqrt":
            q = args[0]
            if q.value < 0:
                raise ForgeEvalError(f"sqrt() of a negative number ({q})")
            return q ** Quantity(0.5)
        if name == "abs":
            q = args[0]
            keep = q.unit is not None and not q.unit.affine
            return Quantity(abs(q.value), q.dim, q.unit if keep else None)
        if name in ("min", "max"):
            first = args[0]
            for other in args[1:]:
                if other.dim != first.dim:
                    raise UnitError(f"{name}() needs values of the same kind, found {describe_full(first.dim)} "
                                    f"and {describe_full(other.dim)}")
            pick = min(args, key=lambda q: q.value) if name == "min" else max(args, key=lambda q: q.value)
            return pick
    except OverflowError:
        raise ForgeEvalError(f"{name}() result is too large to represent") from None
    raise AssertionError(name)  # pragma: no cover


def _plain_integer(value, label):
    if not isinstance(value, Quantity) or not value.is_plain or not value.value.is_integer():
        raise ForgeEvalError(f"{label} must be a plain whole number")
    return int(value.value)
