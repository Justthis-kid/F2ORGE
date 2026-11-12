"""Symbolic helpers for calculus: simplify an expression, differentiate it, and take limits.

This is deliberately small.  It handles the shapes a student writes in a calculus class — sums,
products, quotients, powers, and the standard functions — and it is honest when it cannot decide:
`limit()` reports the numeric value it measured instead of pretending to a proof.

    derivative(x^2)        -> 2x
    limit(sin(x)/x, 0)     -> 1
    limit(1/x, 0)          -> the two one-sided limits disagree
"""
from __future__ import annotations

import math
from fractions import Fraction
from typing import List, Optional, Tuple

from . import syntax as S
from .errors import ForgeEvalError, ForgeError, UnitError
from .printer import format_expr


# ---- simplification ---------------------------------------------------------------------------
def is_zero(node) -> bool:
    return isinstance(node, S.Number) and node.value == 0


def is_one(node) -> bool:
    return isinstance(node, S.Number) and node.value == 1


def number(value: float) -> S.Number:
    return S.Number(float(value))


def simplify(node):
    """Fold constant arithmetic and the obvious identities (`x+0`, `x*1`, `x^0`, `x^1`)."""
    if isinstance(node, (S.Number, S.QuantityLit, S.Name, S.StringLit)):
        return node
    if isinstance(node, S.Unary):
        operand = simplify(node.operand)
        if node.op == "not":
            return S.Unary("not", operand, node.span)
        if isinstance(operand, S.Number):
            return number(-operand.value)
        if isinstance(operand, S.Unary) and operand.op == "-":
            return operand.operand
        return S.Unary("-", operand, node.span)
    if isinstance(node, S.Binary):
        return _simplify_binary(node)
    if isinstance(node, S.Call):
        args = tuple(simplify(arg) for arg in node.args)
        return S.Call(node.func, args, node.kwargs, node.span, node.func_span)
    return node


def _simplify_binary(node: S.Binary):
    op = node.op
    left, right = simplify(node.left), simplify(node.right)
    if op in ("+", "-"):
        if is_zero(right):
            return left
        if is_zero(left):
            return S.Unary("-", right, node.span) if op == "-" else right
        if isinstance(left, S.Number) and isinstance(right, S.Number):
            return number(left.value + right.value if op == "+" else left.value - right.value)
        return S.Binary(op, left, right, node.span)
    if op == "*":
        if is_zero(left) or is_zero(right):
            return number(0)
        if is_one(left):
            return right
        if is_one(right):
            return left
        if isinstance(left, S.Number) and isinstance(right, S.Number):
            return number(left.value * right.value)
        return S.Binary(op, left, right, node.span)
    if op == "/":
        if is_zero(left) and not is_zero(right):
            return number(0)
        if is_one(right):
            return left
        if isinstance(left, S.Number) and isinstance(right, S.Number) and right.value != 0:
            value = left.value / right.value
            return number(value)
        return S.Binary(op, left, right, node.span)
    if op == "^":
        if is_zero(right):
            return number(1)
        if is_one(right):
            return left
        if isinstance(left, S.Number) and isinstance(right, S.Number):
            try:
                return number(left.value ** right.value)
            except (ValueError, OverflowError):
                return S.Binary(op, left, right, node.span)
        return S.Binary(op, left, right, node.span)
    return S.Binary(op, left, right, node.span)


# ---- differentiation --------------------------------------------------------------------------
_DIFF_RULES = {"sin": "cos", "cos": lambda x: S.Unary("-", S.Call("sin", (x,))), "exp": "exp"}


def differentiate(node, var: str = "x"):
    """The derivative of an expression with respect to `var`."""
    if isinstance(node, S.Number) or isinstance(node, S.QuantityLit):
        return number(0)
    if isinstance(node, S.Name):
        return number(1) if node.name == var else number(0)
    if isinstance(node, S.Unary) and node.op == "-":
        return S.Unary("-", differentiate(node.operand, var))
    if isinstance(node, S.Binary):
        return simplify(_differentiate_binary(node, var))
    if isinstance(node, S.Call) and len(node.args) == 1:
        inner = differentiate(node.args[0], var)
        arg = node.args[0]
        if node.func == "sin":
            return simplify(S.Binary("*", S.Call("cos", (arg,)), inner))
        if node.func == "cos":
            return simplify(S.Binary("*", S.Unary("-", S.Call("sin", (arg,))), inner))
        if node.func == "exp":
            return simplify(S.Binary("*", S.Call("exp", (arg,)), inner))
        if node.func == "ln":
            return simplify(S.Binary("/", inner, arg))
        if node.func == "sqrt":
            return simplify(S.Binary("/", inner, S.Binary("*", number(2), S.Call("sqrt", (arg,)))))
        if node.func in ("tan",):
            return simplify(S.Binary("/", inner,
                                     S.Binary("^", S.Call("cos", (arg,)), number(2))))
        if node.func == "abs":
            return simplify(S.Binary("*", S.Call("sign", (arg,)), inner))
    raise ForgeEvalError(f"cannot differentiate {format_expr(node)} symbolically",
                         hint="Use derivative(f, x) for a numeric derivative instead.")


def _differentiate_binary(node: S.Binary, var: str):
    left, right = node.left, node.right
    dl, dr = differentiate(left, var), differentiate(right, var)
    if node.op in ("+", "-"):
        return S.Binary(node.op, dl, dr)
    if node.op == "*":  # product rule
        return S.Binary("+", S.Binary("*", dl, right), S.Binary("*", left, dr))
    if node.op == "/":  # quotient rule
        numerator = S.Binary("-", S.Binary("*", dl, right), S.Binary("*", left, dr))
        return S.Binary("/", numerator, S.Binary("^", right, number(2)))
    if node.op == "^":
        if isinstance(right, S.Number):  # power rule
            return S.Binary("*", S.Binary("*", right, S.Binary("^", left, number(right.value - 1))), dl)
        # x^g: d/dx exp(g ln x) = x^g (g' ln x + g/x)
        term = S.Binary("+", S.Binary("*", dr, S.Call("ln", (left,))), S.Binary("/", right, left))
        return S.Binary("*", node, term)
    raise ForgeEvalError(f"cannot differentiate the {node.op} operator symbolically")


# ---- limits -----------------------------------------------------------------------------------
def _substitute(node, var: str, value: float):
    """The expression with `var` replaced by a number, simplified."""
    if isinstance(node, S.Name) and node.name == var:
        return number(value)
    if isinstance(node, S.Unary):
        return S.Unary(node.op, _substitute(node.operand, var, value), node.span)
    if isinstance(node, S.Binary):
        return S.Binary(node.op, _substitute(node.left, var, value),
                        _substitute(node.right, var, value), node.span)
    if isinstance(node, S.Call):
        return S.Call(node.func, tuple(_substitute(arg, var, value) for arg in node.args))
    return node


def indeterminate(node, var: str, at: float) -> bool:
    """Is the expression 0/0, 0*inf, or inf/inf at this point?  (The shapes l'Hôpital's rule needs.)"""
    try:
        return _shape(node, var, at) in ("0/0", "inf/inf", "0*inf")
    except ValueError:
        return False


def _shape(node, var: str, at: float) -> str:
    """'finite', '0/0', 'inf/inf', or '0*inf' — how the expression behaves at the point."""
    if isinstance(node, S.Binary) and node.op in ("/", "*"):
        left = _value(node.left, var, at)
        right = _value(node.right, var, at)
        if node.op == "/":
            if left == 0 and right == 0:
                return "0/0"
            if left is math.inf and right is math.inf:
                return "inf/inf"
        elif left == 0 and right is math.inf or right == 0 and left is math.inf:
            return "0*inf"
    return "finite"


def _value(node, var: str, at: float):
    """A number, 0, or infinity for a sub-expression; 0 for anything that fails."""
    try:
        result = _evaluate(_substitute(node, var, at))
    except (ForgeError, ValueError, ZeroDivisionError, OverflowError):
        if isinstance(node, S.Binary) and node.op == "/":
            try:
                denominator = _evaluate(_substitute(node.right, var, at))
                if denominator == 0 and _evaluate(_substitute(node.left, var, at)) != 0:
                    return math.inf
            except (ForgeError, ValueError, ZeroDivisionError, OverflowError):
                pass
        return 0.0
    return result


def _evaluate(node):
    """The value of a numeric expression, as a float."""
    if isinstance(node, S.Number):
        return float(node.value)
    if isinstance(node, S.Unary) and node.op == "-":
        return -_evaluate(node.operand)
    if isinstance(node, S.Binary):
        left, right = _evaluate(node.left), _evaluate(node.right)
        if node.op == "+":
            return left + right
        if node.op == "-":
            return left - right
        if node.op == "*":
            return left * right
        if node.op == "/":
            return left / right
        if node.op == "^":
            return left ** right
    if isinstance(node, S.Call) and len(node.args) == 1:
        value = _evaluate(node.args[0])
        if node.func in ("sin", "cos", "tan", "exp", "sqrt", "asin", "acos", "atan"):
            return getattr(math, node.func)(value)
        if node.func == "ln":
            return math.log(value)
        if node.func == "log":
            return math.log10(value)
        if node.func == "abs":
            return abs(value)
    raise ValueError(f"not numeric: {type(node).__name__}")


def lhopital_order(node, var: str, at: float) -> Optional[Tuple[object, int]]:
    """The expression to differentiate, and how many times, to resolve an indeterminate shape."""
    depth = 0
    current = node
    while isinstance(current, S.Binary) and current.op in ("/", "*"):
        if not indeterminate(current, var, at):
            break
        if current.op == "/":
            depth += 1
            numerator = differentiate(current.left, var)
            denominator = differentiate(current.right, var)
            current = simplify(S.Binary("/", numerator, denominator))
        else:
            depth += 1  # 0*inf: rewrite x*ln(x) as ln(x)/(1/x) and take the quotient's limit
            current = simplify(S.Binary("/", current.left,
                                        S.Binary("/", number(1), current.right)))
        if depth > 12:
            break
    return current, depth
