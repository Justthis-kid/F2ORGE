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
from .dimensions import describe_full
from .errors import ForgeError, ForgeEvalError, ForgeNameError, ForgeSyntaxError, Span, UnitError
from .quantity import Quantity
from .units import lookup_unit


class UndefinedVariable(ForgeNameError):
    """A plain variable lookup failed (as opposed to an unknown function or equation)."""


class Scope:
    """Variable lookup: explicit values first, then built-in constants.

    `excluded` names are never taken from the constants: an equation that declares `R : ohm`
    gets its own R rather than the molar gas constant.
    """

    def __init__(self, values: Optional[Dict[str, Quantity]] = None, excluded: Iterable[str] = (),
                 constants: bool = True):
        self.values: Dict[str, Quantity] = values if values is not None else {}
        self.excluded = frozenset(excluded)
        self.constants = constants

    def get(self, name: str) -> Optional[Quantity]:
        if name in self.values:
            return self.values[name]
        if self.constants and name not in self.excluded:
            return CONSTANTS.get(name)
        return None

    def set(self, name: str, value: Quantity) -> None:
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
    "min": (2, 99), "max": (2, 99),
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
    def eval(self, node, scope: Scope) -> Quantity:
        try:
            return self._eval(node, scope)
        except ForgeError as err:
            if err.span is None and getattr(node, "span", None) is not None:
                err.span = node.span
            raise

    def _eval(self, node, scope: Scope) -> Quantity:
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
            return -self.eval(node.operand, scope)
        if isinstance(node, S.Binary):
            left = self.eval(node.left, scope)
            right = self.eval(node.right, scope)
            if node.op == "+":
                return left + right
            if node.op == "-":
                return left - right
            if node.op == "*":
                return left * right
            if node.op == "/":
                return left / right
            return left ** right
        if isinstance(node, S.Call):
            if node.func in ARITY:
                return self._call_function(node, scope)
            eq, values = self.call_equation(node, scope)
            return values[eq.primary]
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
    def _call_function(self, node: S.Call, scope: Scope) -> Quantity:
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


def _apply(name: str, args: List[Quantity]) -> Quantity:
    try:
        if name in ("sin", "cos", "tan"):
            x = _dimless(args[0], name, "an angle (rad or deg) or a plain number")
            return Quantity({"sin": math.sin, "cos": math.cos, "tan": math.tan}[name](x))
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
