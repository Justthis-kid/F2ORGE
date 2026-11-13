"""Expression evaluation with unit safety.

Every operation goes through Quantity, so `10 kg + 5 m` fails with a UnitError no matter how
deeply it is nested.  Errors raised without a location are given the span of the expression
node being evaluated, which is how the caret ends up under the right piece of source.

Expressions can also yield text, vectors (of numbers, text, or rows), matrices, functions
(`def f(x)` used as a value), and booleans (from comparisons, `and`, `or`, `not`).
"""
from __future__ import annotations

import cmath
import difflib
import math
from fractions import Fraction
from typing import Callable, Dict, Iterable, List, Optional, Tuple, Union

from . import syntax as S
from .constants import BOOLEANS, CONSTANTS
from .dimensions import ANGLE, DIMLESS, describe_full
from .errors import ForgeError, ForgeEvalError, ForgeNameError, ForgeSyntaxError, Span, UnitError
from .linear_algebra import (
    ALL as _ALL, Element, Matrix, Value, Vector, add as add_linear, ascending_all, cross, cumsum,
    descending_all, determinant, divide as divide_linear, diff, elementwise, index as index_linear,
    inverse, linear_regression, make_matrix, make_range, make_vector, mean, median,
    multiply as multiply_linear, negate, normalize, numeric_items, percentile, same_units, select,
    solve_linear, standard_deviation, subtract as subtract_linear, transpose, variance,
)
from .mathlib import adaptive_simpson, bisect, golden
from .printer import format_expr
from .quantity import Quantity, format_number
from .text import Text, as_text
from .units import lookup_unit, unit_named, Unit

Scalar = Union[Quantity, Text]

MOLAR = Unit.from_atoms([("mol", Fraction(1)), ("L", Fraction(-1))])  # the unit pH is defined on


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


class FunctionReference:
    """A function used as a value: `integrate(f, 0, 1)` passes `f` itself."""

    __slots__ = ("name", "call")

    def __init__(self, name: str, call: Callable[[Value], Value]):
        self.name = name
        self.call = call

    def __str__(self) -> str:
        return f"function {self.name}"

    def __repr__(self) -> str:
        return f"FunctionReference({self.name})"


class GridFunction:
    """`surface(x*y, xs, ys)`: an expression of two axis variables, sampled over a grid."""

    __slots__ = ("expression", "evaluator", "scope", "names")

    def __init__(self, expression, evaluator: "Evaluator", scope: Scope, names):
        self.expression = expression
        self.evaluator = evaluator
        self.scope = scope
        self.names = list(names)

    def call(self, *arguments) -> object:
        """Evaluate the expression with each name bound to the matching argument."""
        values = dict(self.scope.values)
        for name, value in zip(self.names, arguments):
            values[name] = value
        return self.evaluator.eval(
            self.expression, Scope(values, self.scope.excluded, self.scope.constants))

    def __str__(self) -> str:
        return "function of " + " and ".join(self.names)


class PartialFunction:
    """`integrate(x^2, 0, 1)`: an expression of x that behaves like a function of one value."""

    __slots__ = ("expression", "variable", "evaluator", "scope", "name")

    def __init__(self, expression, evaluator: "Evaluator", scope: Scope, name: str = "f"):
        self.expression = expression
        self.evaluator = evaluator
        self.scope = scope
        self.variable = "x"
        self.name = name

    def call(self, value: Value) -> Value:
        values = dict(self.scope.values)
        values[self.variable] = value
        return self.evaluator.eval(self.expression, Scope(values, self.scope.excluded, self.scope.constants))

    def with_variable(self, name: str) -> "PartialFunction":
        clone = PartialFunction(self.expression, self.evaluator, self.scope, self.name)
        clone.variable = name
        return clone

    def __str__(self) -> str:
        return f"function {self.name}"


# name -> (min args, max args)
ARITY = {
    "sin": (1, 1), "cos": (1, 1), "tan": (1, 1), "asin": (1, 1), "acos": (1, 1), "atan": (1, 1),
    "atan2": (2, 2), "sinh": (1, 1), "cosh": (1, 1), "tanh": (1, 1),
    "exp": (1, 1), "ln": (1, 1), "log": (1, 2), "log2": (1, 1), "sqrt": (1, 1), "cbrt": (1, 1),
    "abs": (1, 1), "min": (2, 99), "max": (2, 99), "clamp": (3, 3),
    "inverse": (1, 1), "transpose": (1, 1), "cross": (2, 2), "det": (1, 1), "solve_system": (2, 2),
    "sum": (1, 1), "mean": (1, 1), "std": (1, 1), "pstd": (1, 1), "var": (1, 1), "pvar": (1, 1),
    "median": (1, 1), "percentile": (2, 2), "linreg": (2, 2), "count": (1, 1),
    "cumsum": (1, 1), "normalize": (1, 1), "diff": (1, 1), "trapz": (1, 3),
    "floor": (1, 1), "ceil": (1, 1), "round": (1, 2), "sign": (1, 1),
    "linspace": (3, 3), "logspace": (2, 3), "range": (1, 3), "sort": (1, 2), "select": (2, 2),
    "concat": (1, 99), "size": (1, 1), "reshape": (3, 3),
    "db": (1, 1), "undb": (1, 1), "dbm": (1, 1), "pH": (1, 1), "fromPH": (1, 1),
    "real": (1, 1), "imag": (1, 1), "conj": (1, 1), "arg": (1, 1), "mag": (1, 1),
    "format": (1, 99), "text": (1, 1), "char": (1, 1), "ascii": (1, 1), "upper": (1, 1), "lower": (1, 1),
    "integrate": (2, 4), "derivative": (2, 2), "roots": (1, 1), "fzero": (2, 3), "minimize": (2, 3),
    "surface": (3, 3), "readtable": (1, 1), "csvwrite": (2, 2), "limit": (2, 2), "solveODE": (4, 4),
    "solvePDE": (1, 3), "fminsearch": (2, 2), "linprog": (2, 4),
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
        self.import_hint: Callable[[str], Optional[str]] = lambda _name: None  # set by the Interpreter
        self.lookup_function: Callable[[str], Optional[object]] = lambda _name: None
        self.function_names: Callable[[], List[str]] = lambda: []
        self.interpreter: Optional[object] = None  # set by the Interpreter; runs user functions
        self.file_io: Callable[[str, list, object], object] = _no_file_io

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
        if isinstance(node, S.StringLit):
            return Text(node.value)
        if isinstance(node, S.Name):
            if node.name == "i" and node.name not in scope.values:
                return Quantity(complex(0, 1))
            if node.name in BOOLEANS:
                return BOOLEANS[node.name]
            value = scope.get(node.name)
            if value is None:
                function = self.lookup_function(node.name)
                if function is not None:
                    return self._function_reference(function)
                raise self._undefined(node.name, node.span, scope)
            return value
        if isinstance(node, S.Unary):
            if node.op == "not":
                return not self.condition(node.operand, scope)
            return negate(self.eval(node.operand, scope))
        if isinstance(node, S.Binary):
            return self._binary(node, scope)
        if isinstance(node, S.VectorLiteral):
            return make_vector([self.eval(item, scope) for item in node.items])
        if isinstance(node, S.MatrixLiteral):
            return make_matrix([[self.eval(item, scope) for item in row] for row in node.rows])
        if isinstance(node, S.ListLiteral):
            from .linear_algebra import concatenate

            return concatenate([self.eval(item, scope) for item in node.items])
        if isinstance(node, S.Call):
            return self.call(node, scope)
        if isinstance(node, S.Index):
            count = self.eval(node.count, scope) if node.count is not None else None
            target = self.eval(node.obj, scope)
            indices = [
                _ALL if isinstance(item, S.Name) and item.name == ":" else self.eval(item, scope)
                for item in node.indices
            ]
            if count is None and not any(isinstance(item, S.Name) and item.name == ":" for item in node.indices) \
                    and not any(isinstance(item, S.Binary) and item.op == ":" for item in node.indices):
                return index_linear(target, indices)
            results = select(target, indices, count)
            if len(results) == 1:
                return results[0]
            if count is not None:
                return results[0]  # M[:, j:j+n] is one block
            if all(isinstance(item, Vector) for item in results):
                # M[:, 0] picks one column from every row, which is a matrix of its own.
                widths = {len(item.items) for item in results}
                if len(widths) == 1:
                    return Matrix(tuple(tuple(item.items) for item in results))
            raise ForgeEvalError("a selection such as M[i, j] must pick one value", node.span,
                                 hint="Use M[i] for a row, or M[:, j:j+n] for a block.")
        if isinstance(node, S.Member):
            if isinstance(node.obj, S.Call) and node.obj.func not in ARITY:
                eq, values = self.call_equation(node.obj, scope)
                if node.attr not in values:
                    raise ForgeNameError(
                        f"{eq.name} has no output named '{node.attr}'", node.span,
                        hint=f"Its outputs are: {', '.join(eq.outputs)}")
                return values[node.attr]
            if isinstance(node.obj, S.Call):
                raise ForgeSyntaxError(f"{node.obj.func}() does not have a named part '{node.attr}'", node.span)
            target = self.eval(node.obj, scope)
            if isinstance(target, Matrix) and node.attr == "T":
                return transpose(target)
            raise ForgeSyntaxError("Only the result of an equation call has named outputs", node.span,
                                   hint="For example: Force(m = 2 kg, a = 3 m/s^2).F")
        raise TypeError(f"cannot evaluate {node!r}")  # pragma: no cover

    # ---- operators -------------------------------------------------------------------------
    def _binary(self, node: S.Binary, scope: Scope):
        op = node.op
        if op in ("and", "or"):
            left = self.condition(node.left, scope)
            if op == "and" and not left:
                return False
            if op == "or" and left:
                return True
            return self.condition(node.right, scope)
        left = self.eval(node.left, scope)
        right = self.eval(node.right, scope)
        if op in COMPARISONS:
            return compare(left, right, op, node.span)
        if op == "+":
            return add_linear(left, right)
        if op == "-":
            return subtract_linear(left, right)
        if op in ("*", "*."):
            return multiply_linear(left, right)
        if op == "/":
            return divide_linear(left, right)
        if op == "/.":
            return elementwise(left, right, "/")
        if not isinstance(left, Quantity) or not isinstance(right, Quantity):
            if isinstance(left, Text) or isinstance(right, Text):
                raise ForgeEvalError("cannot raise text to a power", node.span)
            raise ForgeEvalError("vectors and matrices cannot be raised to a power", node.span)
        return left ** right

    def loop_values(self, node, scope: Scope) -> List[Value]:
        """The values a `for` loop walks: a range, a vector, matrix rows, or the characters of text."""
        if isinstance(node, S.Range):
            from .linear_algebra import make_range

            start = self.eval(node.start, scope)
            stop = self.eval(node.stop, scope)
            step = self.eval(node.step, scope) if node.step is not None else Quantity(1)
            return list(make_range(start, stop, step).items)
        value = self.eval(node, scope)
        if isinstance(value, Vector):
            return list(value.items)
        if isinstance(value, Matrix):
            return [Vector(row) for row in value.rows]
        if isinstance(value, Text):
            return [Text(character) for character in value.value]
        return [value]

    def condition(self, node, scope: Scope) -> bool:
        """Evaluate a condition to True/False.  Comparisons give booleans; numbers are true when nonzero."""
        return truth(self.eval(node, scope), node.span)

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

    # ---- calls -----------------------------------------------------------------------------
    def call(self, node: S.Call, scope: Scope):
        name = node.func
        if name in ARITY:
            return self._call_function(node, scope)
        function = self.lookup_function(name)
        if function is not None:
            args = [self.eval(arg, scope) for arg in node.args]
            kwargs = [(key, self.eval(expr, scope)) for key, expr, _ in node.kwargs]
            return self.interpreter.call_function(function, args, kwargs, node.span)  # type: ignore[union-attr]
        eq, values = self.call_equation(node, scope)
        return values[eq.primary]

    def _function_reference(self, function) -> FunctionReference:
        return FunctionReference(function.name,
                                 lambda *values, f=function: self._call_user(f, *values))

    def _call_user(self, function, *values: Value) -> Value:
        return self.interpreter.call_function(function, list(values), [], None)  # type: ignore[union-attr]

    def as_function(self, value, scope: Scope, span, what: str = "this function", arity: int = 1):
        """A scalar function of one variable: a def function, an equation, or an expression."""
        if isinstance(value, (FunctionReference, PartialFunction, GridFunction)):
            return value
        if isinstance(value, Text):
            raise ForgeEvalError(f"{what} needs a function such as f, x^2, or an equation name")
        eq = self.lookup_equation(as_text(value)) if not isinstance(value, Quantity) else None
        if eq is not None:
            inputs = list(eq.inputs)
            if len(inputs) != 1:
                raise ForgeEvalError(f"{eq.name} needs {len(inputs)} inputs; {what} needs a function of one")

            def call(item: Value, equation=eq, single=inputs[0]) -> Value:
                return equation.call(self, {single: (item, None)}, span)[1][equation.primary]

            return FunctionReference(eq.name, call)
        if isinstance(value, Quantity):
            raise ForgeEvalError(f"{what} needs a function such as f, x^2, or an equation name, found {value}")
        raise ForgeEvalError(f"{what} needs a function such as f, x^2, or an equation name")

    def two_variable_function(self, node, scope: Scope, xs, ys):
        """`surface(x*y, xs, ys)`: an expression of two variables over a grid.

        The names it refers to that are not already values become the two axes, x first.
        """
        free = [n for n in S.names_in(node) if scope.get(n) is None]
        names = [free[0]] if free else ["x"]
        second = free[1] if len(free) > 1 else ("y" if names[0] == "x" else "x")
        return GridFunction(node, self, scope, (names[0], second))

    def _solveODE(self, node: S.Call, scope: Scope):
        """solveODE(f, y0, t0, t1): integrate dy/dt = f(t, y), returning <times, values>."""
        from .ode import integrate

        y0 = self.eval(node.args[1], scope)
        t0 = self.eval(node.args[2], scope)
        t1 = self.eval(node.args[3], scope)
        for value, what in ((y0, "the starting value"), (t0, "the start time"), (t1, "the end time")):
            if not isinstance(value, Quantity):
                raise ForgeEvalError(f"solveODE() needs a scalar quantity for {what}", node.span)
        if t0.dim != t1.dim:
            raise UnitError("solveODE() start and end times must have the same unit", node.span)
        if t1.value == t0.value:
            raise ForgeEvalError("solveODE() needs an end time different from the start time", node.span)
        derivative = self._derivative_function(node.args[0], scope, node.span)
        first = derivative(Quantity(t0.value, t0.dim), y0)
        if not isinstance(first, Quantity):
            raise ForgeEvalError("solveODE() needs a function that returns a number", node.span)
        # dy/dt must measure the value per unit of time, or the result cannot have y0's unit.
        value_dim = first.dim * t0.dim
        if value_dim != y0.dim:
            raise UnitError(
                f"solveODE() needs a derivative in {describe_full(y0.dim)} per {describe_full(t0.dim)}, "
                f"but it gives {describe_full(first.dim)}", node.span,
                hint="The derivative is dy/dt: its unit is the value's unit divided by time.")

        def slope(t_: float, y_: float) -> float:
            out = derivative(Quantity(t_, t0.dim), Quantity(y_, y0.dim))
            if not isinstance(out, Quantity):
                raise ForgeEvalError("solveODE() needs a function that returns a number", node.span)
            return out.value

        times, values = integrate(slope, y0.value, t0.value, t1.value)
        return Vector((Vector(tuple(Quantity(t, t0.dim, t0.unit) for t in times)),
                       Vector(tuple(Quantity(v, value_dim, y0.unit) for v in values))))

    def _solve_pde(self, node: S.Call, scope: Scope):
        """solvePDE(grid) or solvePDE(grid, cells): relax a field to steady state.

        `grid` is a square matrix whose edge values are the boundary conditions and whose interior
        values are the starting guess (0 for a cold field).  The result is a matrix of the same
        shape that plots as a heatmap.
        """
        from .ode import solve_poisson

        grid = self.eval(node.args[0], scope)
        if not isinstance(grid, Matrix):
            raise ForgeEvalError("solvePDE() needs a square matrix of boundary values", node.span,
                                 hint="Build one with surface() or reshape(), or fill edges by hand.")
        rows, columns = grid.shape
        if rows != columns:
            raise ForgeEvalError(f"solvePDE() needs a square grid, found {rows}x{columns}", node.span)
        cells = _plain_integer(self.eval(node.args[1], scope), "solvePDE() grid size") \
            if len(node.args) > 1 else rows
        if cells < 3:
            raise ForgeEvalError("solvePDE() needs a grid at least 3 cells across", node.span)
        unit = next((item.unit for row in grid.rows for item in row if item.unit is not None), None)
        dim = grid.rows[0][0].dim
        raw = [[item.value for item in row] for row in grid.rows]
        solved = solve_poisson(raw, rows)
        return Matrix(tuple(tuple(Quantity(value, dim, unit) for value in row) for row in solved))

    def _fminsearch(self, node: S.Call, scope: Scope):
        """fminsearch(f, start): minimise f over several variables from a starting vector."""
        from .mathlib import nelder_mead

        start = self.eval(node.args[1], scope)
        if not isinstance(start, Vector) or not start.items:
            raise ForgeEvalError("fminsearch() needs a starting vector of values", node.span,
                                 hint="Write: fminsearch(cost, <1, 1>)")
        if any(not isinstance(item, Quantity) for item in start.items):
            raise ForgeEvalError("fminsearch() needs a starting vector of numbers", node.span)
        dimensions = [item.dim for item in start.items]
        function = self.multi_variable_function(node.args[0], scope, len(start.items), node.span)
        units = [item.unit for item in start.items]

        def cost(point: List[float]) -> float:
            args = [Quantity(value, dim, unit) for value, dim, unit in zip(point, dimensions, units)]
            result = function(*args)
            if not isinstance(result, Quantity):
                raise ForgeEvalError("fminsearch() needs a function that returns a number", node.span)
            if not result.dim.is_dimensionless:
                raise UnitError("fminsearch() needs a cost with no unit", node.span,
                                hint="Divide by a reference quantity so the cost is a plain number.")
            return result.value

        best, value = nelder_mead(cost, [item.value for item in start.items])
        return Vector(tuple(Quantity(v, dim, unit) for v, dim, unit in zip(best, dimensions, units)))

    def multi_variable_function(self, node, scope: Scope, count: int, span):
        """`def cost(x, y)`, or a bare expression over count free names, as a function of them."""
        if isinstance(node, (S.Name, S.Call)):
            function = self.eval(node, scope)
            if hasattr(function, "call"):
                return function.call
            raise ForgeEvalError("this needs a function such as def cost(x, y) { ... }", span)
        free = [n for n in S.names_in(node) if scope.get(n) is None][:count]
        while len(free) < count:
            free.append(f"v{len(free) + 1}")
        return GridFunction(node, self, scope, free).call

    def _linprog(self, node: S.Call, scope: Scope):
        """linprog(cost, constraints, bounds): maximise a linear objective for non-negative x.

        `constraints` is a matrix whose rows hold coefficients and `bounds` the right-hand sides
        of `sum(a_i x_i) <= b`.  The optional third argument is "max" (the default) or "min".
        """
        from .mathlib import simplex_linear

        objective = self.eval(node.args[0], scope)
        matrix = self.eval(node.args[1], scope)
        bounds = self.eval(node.args[2], scope) if len(node.args) > 2 else None
        if isinstance(matrix, Matrix) and bounds is None:
            bounds = Vector(tuple(row[-1] for row in matrix.rows))
            matrix = Matrix(tuple(row[:-1] for row in matrix.rows))
        if not isinstance(objective, Vector) or not isinstance(matrix, Matrix) or \
                not isinstance(bounds, Vector):
            raise ForgeEvalError("linprog() needs a cost vector, a constraint matrix, and bounds",
                                 node.span, hint='Write: linprog(<3, 2>, [[1, 1], [2, 1]], <4, 6>)')
        sense = "max"
        if len(node.args) > 3:
            sense = as_text(self.eval(node.args[3], scope))
        coefficients = [_scalar_in(item, "linprog") for item in objective.items]
        rows = [[_scalar_in(item, "linprog") for item in row] for row in matrix.rows]
        limits = [_scalar_in(item, "linprog") for item in bounds.items]
        values, best = simplex_linear([c.value for c in coefficients],
                                      [[c.value for c in row] for row in rows],
                                      [c.value for c in limits], sense)
        return Vector((Vector(tuple(Quantity(v) for v in values)), Quantity(best)))

    def _derivative_function(self, node, scope: Scope, span):
        """`def f(t, y)`, or a bare expression using t and y, as a function of (t, y)."""
        if isinstance(node, S.Name) or isinstance(node, S.Call):
            function = self.eval(node, scope)
            if hasattr(function, "call"):
                return function.call
            raise ForgeEvalError("solveODE() needs a function such as def f(t, y) { ... }", span)
        names = [n for n in S.names_in(node) if scope.get(n) is None]
        time_name = "t" if "t" in names else (names[0] if names else "t")
        value_name = "y" if "y" in names else (names[1] if len(names) > 1 else "y")
        grid = GridFunction(node, self, scope, (time_name, value_name))
        return grid.call

    def _limit(self, node: S.Call, scope: Scope):
        """limit(expression, at): the value an expression approaches.

        A function name is sampled numerically; a bare expression such as `sin(x)/x` is first put
        into a form l'Hôpital's rule can read, so the common 0/0 cases come out exact.
        """
        from . import calculus

        target = node.args[1]
        point = self.eval(target, scope)
        if not isinstance(point, Quantity):
            raise ForgeEvalError("limit() needs a numeric point", node.span)
        first = node.args[0]
        if isinstance(first, S.Name) and scope.get(first.name) is None:
            # `limit(x, 2)`: a bare name that is not a value is the variable itself.
            return Quantity(point.value, point.dim)
        if isinstance(first, S.Name) or isinstance(first, S.Call):
            value = self.eval(first, scope)
            if not isinstance(value, (FunctionReference, PartialFunction, GridFunction)):
                # A plain value has no limit to take: limit(3, 0) is 3.
                return value
            numeric = self._as_numeric_function(value, scope, node.span, "limit()")
            return Quantity(_approach(numeric, point.value), point.dim)
        expression, order = calculus.lhopital_order(first, "x", point.value)
        if order:
            simplified = calculus.simplify(calculus._substitute(expression, "x", point.value))
            try:
                exact = calculus._evaluate(simplified)
            except (ValueError, ZeroDivisionError, OverflowError):
                exact = None
            if exact is not None and math.isfinite(exact):
                return Quantity(exact, point.dim)
        numeric = self._as_numeric_function(PartialFunction(first, self, scope, "expression"),
                                            scope, node.span, "limit()")
        return Quantity(_approach(numeric, point.value), point.dim)

    def _symbolic_diff(self, node) -> Text:
        """`diff(x^2)` gives `2x`: the derivative of an expression, as text."""
        from . import calculus

        derivative = calculus.simplify(calculus.differentiate(node, "x"))
        return Text(format_expr(derivative))

    def callback_function(self, node, scope: Scope):
        """The function argument of integrate/derivative/fzero/minimize/surface.

        A name or a call is evaluated as usual.  Anything else is a bare expression such as `x^2`,
        which becomes a function of the variable the limits are written in.
        """
        if isinstance(node, (S.Name, S.Call)) and not (
                isinstance(node, S.Name) and node.name == "x" and scope.get("x") is None):
            return self.eval(node, scope)
        return PartialFunction(node, self, scope, "expression")

    def _as_numeric_function(self, value, scope: Scope, span, what: str,
                             arity: int = 1) -> Callable[..., float]:
        function = self.as_function(value, scope, span, what, arity)

        def call(*coordinates: float) -> float:
            if arity == 1:
                result = function.call(Quantity(coordinates[0]))
            else:
                result = function.call(*[Quantity(c) for c in coordinates])
            if isinstance(result, Quantity):
                return result.magnitude(result.unit) if result.unit is not None else result.value
            raise ForgeEvalError(f"{what} must return a number, found text")

        return call

    # ---- built-in functions ----------------------------------------------------------------
    def _call_function(self, node: S.Call, scope: Scope):
        name = node.func
        if node.kwargs:
            raise ForgeSyntaxError(f"{name}() takes plain values, not name = value pairs", node.span)
        lo, hi = ARITY[name]
        if not lo <= len(node.args) <= hi:
            want = f"{lo}" if lo == hi else f"{lo} or more"
            raise ForgeSyntaxError(f"{name}() takes {want} value(s) but got {len(node.args)}", node.span)
        try:
            if name in FILE_FUNCTIONS:
                return self.file_io(name, [self.eval(arg, scope) for arg in node.args], node.span)
            if name == "diff" and _is_symbolic(node.args[0], scope):
                return self._symbolic_diff(node.args[0])
            if name in CALLBACK_FUNCTIONS:
                return self._callback(name, node, scope)
            args = [self.eval(a, scope) for a in node.args]
            return _apply(name, args)
        except ForgeError as err:
            if err.span is None:
                err.span = node.span
            raise

    def _callback(self, name: str, node: S.Call, scope: Scope):
        span = node.span
        tolerance = None
        if name == "limit":
            return self._limit(node, scope)
        if name == "solveODE":
            return self._solveODE(node, scope)
        if name == "solvePDE":
            return self._solve_pde(node, scope)
        if name == "fminsearch":
            return self._fminsearch(node, scope)
        if name == "linprog":
            return self._linprog(node, scope)
        if name == "surface":
            xs, ys = [self.eval(a, scope) for a in node.args[1:]]
            first = node.args[0]
            if isinstance(first, (S.Name, S.Call)):
                function = self.eval(first, scope)
            else:
                # `surface(x*y, ...)`: a bare expression of x and y over the whole grid.
                function = self.two_variable_function(first, scope, xs, ys)
            numeric = self._as_numeric_function(function, scope, span, "surface()", arity=2)
            return _surface(numeric, xs, ys, span)
        if name == "roots":
            lines = self.eval(node.args[0], scope)
            return _real_roots(numeric_items(lines, "roots"), span)
        if name == "integrate":
            from_node, to_node = node.args[1], node.args[2]
            a, b = self.eval(from_node, scope), self.eval(to_node, scope)
            if len(node.args) > 3:
                tolerance = self.eval(node.args[3], scope)
        elif name == "derivative":
            from_node = to_node = node.args[1]
            a = b = self.eval(from_node, scope)
        else:  # fzero, minimize
            from_node = node.args[1]
            to_node = node.args[2] if len(node.args) > 2 else from_node
            a, b = self.eval(from_node, scope), self.eval(to_node, scope)
        function = _resolve_function(self.callback_function(node.args[0], scope), (from_node, to_node))
        numeric = self._as_numeric_function(function, scope, span, f"{name}()")
        unit = _function_unit(function)
        if name == "integrate":
            if not isinstance(a, Quantity) or not isinstance(b, Quantity):
                raise ForgeEvalError("integrate() limits must be quantities")
            if a.dim != b.dim:
                raise UnitError("integrate() limits must have matching units")
            # The integral of f over x has the units of f times x, which the limits reveal.
            dimension = _function_dim(function, a, numeric, scope) * a.dim
            tolerance = scale_free(tolerance, span) if tolerance is not None else 1e-9
            return Quantity(adaptive_simpson(numeric, a.value, b.value, tolerance), dimension)
        if name == "derivative":
            dimension = _function_dim(function, a, numeric, scope) / a.dim
            step = max(1e-6, abs(a.value) * 1e-6)
            value = (numeric(a.value + step) - numeric(a.value - step)) / (2 * step)
            return Quantity(value, dimension)
        if name == "fzero":
            root = bisect(numeric, a.value, b.value)
            return Quantity(root, a.dim)
        best, best_value = golden(numeric, a.value, b.value)
        return Vector((Quantity(best, a.dim), Quantity(best_value, unit.dim if unit is not None else DIMLESS)))

    # ---- equation calls --------------------------------------------------------------------
    def call_equation(self, node: S.Call, scope: Scope):
        eq = self.lookup_equation(node.func)
        if eq is None:
            tip = _suggest(node.func, list(ARITY) + list(self.equation_names()) + list(self.function_names())) \
                or self.import_hint(node.func)
            raise ForgeNameError(f"'{node.func}' is not a function or an equation",
                                 node.func_span or node.span, hint=tip)
        if node.args:
            raise ForgeSyntaxError(
                f"{eq.name}() needs named values", node.span,
                hint=f"Write: {eq.name}({', '.join(i + ' = ...' for i in eq.inputs)})", )
        args: Dict[str, Tuple[Value, Optional[Span]]] = {}
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


def _resolve_function(value, limit_nodes):
    """`integrate(t^2, 0, 1)`: a bare expression is a function of the variable used in the limits."""
    if isinstance(value, PartialFunction):
        names = set(S.names_in(value.expression))
        for node in limit_nodes:
            for name in S.names_in(node):
                if name in names:
                    return value.with_variable(name)
    return value


def _function_unit(function) -> Optional[Quantity]:
    """The unit of a trial evaluation, used to give integrals and derivatives units."""
    try:
        result = function.call(Quantity(1.0)) if hasattr(function, "call") else None
    except ForgeError:
        return None
    return result if isinstance(result, Quantity) else None


def _function_dim(function, at: Quantity, numeric, scope) -> Dim:
    """The dimension f(x) has when x is measured like `at`, so `x^2` over metres is an area."""
    from .dimensions import Dim

    if hasattr(function, "variable"):
        # A bare expression is evaluated at a quantity, which gives its terms units.
        try:
            result = function.call(Quantity(1.0, at.dim))
        except ForgeError:
            result = None
        if isinstance(result, Quantity):
            return result.dim
    unit = _function_unit(function)
    return unit.dim if unit is not None else Dim.of()





def _clean_root(z: complex) -> complex:
    """Tidy the tiny real part that floating point leaves in a purely imaginary root."""
    real = 0.0 if abs(z.real) <= 1e-12 * max(1.0, abs(z.imag)) else z.real
    return complex(real, z.imag)


def _approach(numeric, at: float, span=None) -> float:
    """The value a numeric function settles on as it nears `at` from both sides.

    Very large results mean the two sides diverge, which a one-sided limit could still describe.
    """
    steps = [10.0 ** -k for k in range(3, 13)]
    left = [numeric(at - step) for step in steps]
    right = [numeric(at + step) for step in steps]
    if any(not math.isfinite(value) for value in left + right):
        raise ForgeEvalError("the limit is not finite here", span,
                             hint="Check the values around the point, or use a one-sided approach.")
    settled_left, settled_right = left[-1], right[-1]
    scale = max(1.0, abs(settled_left), abs(settled_right))
    if abs(settled_left - settled_right) > 1e-6 * scale:
        raise ForgeEvalError(
            f"the limit does not exist: the two sides approach {format_number(settled_left)} and "
            f"{format_number(settled_right)}", span,
            hint="A one-sided limit may exist; check the expression near the point.")
    return 0.5 * (settled_left + settled_right)


def _real_roots(coefficients: List[Quantity], span) -> Vector:
    dims = {item.dim for item in coefficients}
    if len(dims) != 1:
        raise UnitError("roots() needs coefficients with matching units", span)
    from .linear_algebra import polynomial_roots

    values = polynomial_roots([item.value for item in coefficients])
    roots = []
    for value in sorted(values):
        nearest = round(value)
        value = float(nearest) if abs(value - nearest) < 1e-9 else value
        roots.append(Quantity(value))
    if not roots:
        raise ForgeEvalError("this polynomial has no real roots", span,
                             hint="Write the coefficients from the constant term up: roots(<c, b, a>) solves c + b x + a x².")
    return Vector(tuple(roots))


def scale_free(value, span) -> float:
    if not isinstance(value, Quantity) or not value.dim.is_dimensionless:
        raise UnitError("a tolerance must be a plain number", span)
    return abs(value.value)





def truth(value, span=None) -> bool:
    if isinstance(value, bool):
        return value
    if not isinstance(value, Quantity):
        raise ForgeEvalError("a condition needs true or false, found text or a vector", span)
    if not value.dim.is_dimensionless:
        raise UnitError(f"a condition needs true or false, not {describe_full(value.dim)}", span,
                        hint="Compare quantities first, e.g. speed > 20 m/s.")
    if value.is_complex:
        raise ForgeEvalError("a complex number cannot be used as a condition", span)
    return value.value != 0


COMPARISONS = ("==", "!=", "<=", ">=", "<", ">")
CALLBACK_FUNCTIONS = frozenset({"integrate", "derivative", "roots", "fzero", "minimize", "surface",
                               "limit", "solveODE", "solvePDE", "fminsearch", "linprog"})
FILE_FUNCTIONS = frozenset({"readtable", "csvwrite"})


def _is_symbolic(node, scope: Scope) -> bool:
    """Is this argument an expression to differentiate (`x^2`) rather than a value to difference?

    A name that is not a value, or an expression containing such a name, is symbolic; anything
    else (`v`, `<1, 4, 9>`, `f(x)`) is a value and takes the numeric meaning.
    """
    if isinstance(node, (S.Number, S.QuantityLit, S.StringLit, S.VectorLiteral, S.MatrixLiteral)):
        return False
    if isinstance(node, S.Name):
        return scope.get(node.name) is None
    return any(scope.get(name) is None and name == "x" for name in S.names_in(node))


def _no_file_io(name: str, args: list, span) -> object:
    raise ForgeEvalError(f"{name}() needs a running interpreter, which this evaluation does not have",
                         span, hint="Run the program with forge run, the shell, or an IDE.")


def compare(left, right, op: str, span=None):
    """Comparisons: equality works for any two values; ordering needs two numbers or two texts."""
    if op in ("==", "!="):
        same = _equal(left, right)
        return same if op == "==" else not same
    if isinstance(left, Text) and isinstance(right, Text):
        return {"<": left.value < right.value, ">": left.value > right.value,
                "<=": left.value <= right.value, ">=": left.value >= right.value}[op]
    if not isinstance(left, Quantity) or not isinstance(right, Quantity):
        raise ForgeEvalError(f"cannot compare {_describe(left)} with {op}", span,
                             hint="Use == or != to compare text or vectors.")
    if left.dim != right.dim:
        raise UnitError(f"cannot compare {describe_full(left.dim)} with {describe_full(right.dim)}", span)
    if left.is_complex or right.is_complex:
        raise ForgeEvalError("complex numbers cannot be ordered with < or >", span,
                             hint="Compare magnitudes with abs(), or parts with real() and imag().")
    a, b = left.value, right.value
    return {"<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op]


def _equal(left, right) -> bool:
    if isinstance(left, Text) or isinstance(right, Text):
        return as_text(left) == as_text(right)
    if isinstance(left, Quantity) and isinstance(right, Quantity):
        if left.dim != right.dim:
            return False
        return left.value == right.value
    if isinstance(left, Vector) and isinstance(right, Vector):
        return len(left.items) == len(right.items) and all(
            _equal(a, b) for a, b in zip(left.items, right.items))
    return left == right


def _describe(value) -> str:
    return "text" if isinstance(value, Text) else describe_full(value.dim) if isinstance(value, Quantity) \
        else type(value).__name__.lower()


# ---- function table -----------------------------------------------------------------------
def _dimless(q: Quantity, fname: str, what: str = "a plain number") -> float:
    if not q.dim.is_dimensionless:
        raise UnitError(f"{fname}() needs {what}, found {describe_full(q.dim)}",
                        hint="Divide by a reference quantity first, e.g. ln(x / x0).")
    if q.is_complex:
        raise ForgeEvalError(f"{fname}() needs a real number")
    return q.value


def _plain_integer(value, label):
    if not isinstance(value, Quantity) or not value.is_plain or not value.value.is_integer():
        raise ForgeEvalError(f"{label} must be a plain whole number")
    return int(value.value)


def _scalar_in(value, fname: str) -> Quantity:
    if not isinstance(value, Quantity):
        raise ForgeEvalError(f"{fname}() needs a number, found {type(value).__name__.lower()}")
    return value


def _scalars(args, fname: str) -> List[Quantity]:
    return [_scalar_in(arg, fname) for arg in args]


def _angle(q: Quantity, fname: str) -> float:
    """sin/cos/tan take an angle (converted to radians) or a plain number of radians."""
    if not isinstance(q, Quantity):
        raise ForgeEvalError(f"{fname}() needs a number")
    if q.dim == ANGLE:
        return q.value
    if not q.dim.is_dimensionless:
        raise UnitError(f"{fname}() needs an angle or a plain number, found {describe_full(q.dim)}")
    return q.value


def _apply(name: str, args: List[object]):
    if name == "format":
        return Text("".join(as_text(arg) for arg in args))
    if name == "text":
        return Text(as_text(args[0]))
    if name == "char":
        code = _plain_integer(args[0], "char() code point")
        if not 0 <= code <= 0x10FFFF:
            raise ForgeEvalError("char() needs a code point from 0 to 1114111")
        return Text(chr(code))
    if name == "ascii":
        text = as_text(args[0])
        if not text:
            raise ForgeEvalError("ascii() needs text with at least one character")
        return Quantity(ord(text[0]))
    if name in ("upper", "lower"):
        return Text(as_text(args[0]).upper() if name == "upper" else as_text(args[0]).lower())
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
    if name == "solve_system":
        matrix, vector = args
        if not isinstance(matrix, Matrix):
            raise ForgeEvalError("solve_system() needs a square matrix of coefficients")
        if isinstance(vector, Vector):
            constants = [_scalar_in(item, "solve_system") for item in vector.items]
        elif isinstance(vector, Matrix):
            if vector.shape[1] != 1:
                raise ForgeEvalError("solve_system() needs a column vector of right-hand sides")
            constants = list(vector.rows[0]) if vector.shape[0] == 1 else [row[0] for row in vector.rows]
        else:
            raise ForgeEvalError("solve_system() needs a vector of right-hand sides")
        return Vector(tuple(solve_linear(matrix.rows, constants)))
    if name == "count":
        return Quantity(len(_items(args[0], "count")))
    if name == "size":
        value = args[0]
        if isinstance(value, Matrix):
            return Vector((Quantity(value.shape[0]), Quantity(value.shape[1])))
        if isinstance(value, Vector):
            return Quantity(len(value.items))
        if isinstance(value, Text):
            return Quantity(len(value.value))
        return Quantity(1)
    if name in ("sum", "mean", "std", "pstd", "var", "pvar", "median"):
        items = numeric_items(args[0], name)
        if name == "sum":
            total = items[0]
            for item in items[1:]:
                total = total + item
            return total
        if name == "mean":
            return mean(items)
        if name == "median":
            return median(items)
        if name == "var":
            return variance(items, sample=True)
        if name == "pvar":
            return variance(items, sample=False)
        if name == "std":
            return standard_deviation(items, sample=True)
        return standard_deviation(items, sample=False)
    if name == "percentile":
        fraction = _dimless(_scalar_in(args[1], "percentile"), "percentile")
        if fraction > 1:
            fraction /= 100.0
        return percentile(numeric_items(args[0], "percentile"), fraction)
    if name == "linreg":
        if not isinstance(args[0], Vector) or not isinstance(args[1], Vector):
            raise ForgeEvalError("linreg() needs two vectors of numbers")
        xs = [_scalar_in(item, "linreg") for item in args[0].items]
        ys = [_scalar_in(item, "linreg") for item in args[1].items]
        slope, intercept, r_squared = linear_regression(xs, ys)
        slope.unit = None
        intercept.unit = None
        return Vector((slope, intercept, Quantity(r_squared)))
    if name == "trapz":
        return _trapz(args)
    if name == "diff":
        return diff(numeric_items(args[0], name))
    if name == "cumsum":
        return cumsum(numeric_items(args[0], name))
    if name == "normalize":
        return normalize(numeric_items(args[0], name))
    if name == "sort":
        items = _items(args[0], "sort")
        order = "asc"
        if len(args) == 2:
            order = as_text(args[1])
            if order not in ("asc", "desc"):
                raise ForgeEvalError('sort() order must be "asc" or "desc"')
        return Vector(tuple(sorted_items(items, order)))
    if name == "select":
        source = args[0]
        indices = args[1]
        if not isinstance(indices, Vector):
            raise ForgeEvalError("select() needs a vector of indices")
        positions = [_plain_integer(item, "select() index") for item in indices.items]
        items = _items(source, "select")
        out = []
        for position in positions:
            if not 0 <= position < len(items):
                raise ForgeEvalError(f"select() index {position} is out of range")
            out.append(items[position])
        return Vector(tuple(out))
    if name == "concat":
        from .linear_algebra import concatenate

        return concatenate(args)
    if name == "linspace":
        return _linspace(args)
    if name == "logspace":
        return _logspace(args)
    if name == "range":
        if len(args) == 1:
            start, stop, step = Quantity(0), args[0], Quantity(1)
        elif len(args) == 2:
            start, stop, step = args[0], args[1], Quantity(1)
        else:
            start, stop, step = args
        return make_range(start, stop, step)
    if name == "reshape":
        return _reshape(args)

    if name == "db":
        q = _scalar_in(args[0], "db")
        if q.value <= 0:
            raise ForgeEvalError("db() needs a positive number")
        return Quantity(10 * math.log10(q.value), lookup_unit("dB").dim, unit_named("dB"))
    if name == "undb":
        q = args[0]
        if not isinstance(q, Quantity) or q.dim != lookup_unit("dB").dim:
            raise UnitError("undb() requires a dB value")
        return Quantity(10 ** (q.value / 10))
    if name == "dbm":
        q = _scalar_in(args[0], "dbm")
        power_dim = lookup_unit("W").dim
        if q.dim != power_dim:
            if q.dim.is_dimensionless:
                q = Quantity(q.value, power_dim)  # a plain number is read as watts
            else:
                raise UnitError(f"dbm() needs a power in watts, found {describe_full(q.dim)}",
                                hint="Write the power in W, for example 0.001 W or 1 mW.")
        if q.value <= 0:
            raise ForgeEvalError("dbm() needs a positive power")
        level = 10 * math.log10(q.value / 1e-3)  # dB above 1 mW
        return Quantity(level, lookup_unit("dBm").dim, unit_named("dBm"))
    if name in ("pH", "fromPH"):
        if name == "pH":
            q = _scalar_in(args[0], "pH")
            # pH is defined on the molar scale, so a concentration in SI (mol/m³) is converted.
            molar = q.magnitude(MOLAR) if q.dim == MOLAR.dim else q.magnitude(q.unit or MOLAR)
            if molar <= 0:
                raise ForgeEvalError("pH() needs a positive concentration, such as 1e-7 mol/L")
            return Quantity(-math.log10(molar))
        level = _dimless(_scalar_in(args[0], "fromPH"), "fromPH")
        return Quantity.from_unit(10 ** (-level), MOLAR)  # mol/L
    if name in ("real", "imag", "conj", "arg", "mag"):
        return _complex_part(name, _scalar_in(args[0], name))
    if name in ("floor", "ceil", "round", "sign"):
        q = _scalar_in(args[0], name)
        if not q.dim.is_dimensionless:
            raise UnitError(f"{name}() requires a dimensionless value")
        if q.is_complex:
            raise ForgeEvalError(f"{name}() needs a real number")
        if name == "floor":
            return Quantity(math.floor(q.value))
        if name == "ceil":
            return Quantity(math.ceil(q.value))
        if name == "sign":
            return Quantity((q.value > 0) - (q.value < 0))
        digits = _plain_integer(args[1], "round() digits") if len(args) == 2 else 0
        return Quantity(round(q.value, digits))
    if name == "log2":
        x = _dimless(_scalar_in(args[0], name), name)
        if x <= 0:
            raise ForgeEvalError("log2() needs a positive number")
        return Quantity(math.log2(x))
    if name == "clamp":
        value, low, high = _scalars(args, name)
        for other in (low, high):
            if other.dim != value.dim:
                raise UnitError("clamp() needs three values of the same kind")
        return Quantity(min(max(value.value, low.value), high.value), value.dim, value.unit)
    if name in ("min", "max"):
        if all(isinstance(arg, (Quantity, Text)) for arg in args):
            first = args[0]
            for other in args[1:]:
                if isinstance(first, Text) != isinstance(other, Text):
                    raise ForgeEvalError(f"{name}() needs values of one kind")
                if isinstance(first, Quantity) and other.dim != first.dim:  # type: ignore[union-attr]
                    raise UnitError(f"{name}() needs values of the same kind, found {describe_full(first.dim)} "
                                    f"and {describe_full(other.dim)}")  # type: ignore[union-attr]
            if isinstance(first, Text):
                return min(args, key=lambda q: as_text(q)) if name == "min" else max(args, key=lambda q: as_text(q))
            pick = min(args, key=lambda q: q.value) if name == "min" else max(args, key=lambda q: q.value)
            return pick
        items = []
        for arg in args:
            items.extend(_items(arg, name))
        if not items:
            raise ForgeEvalError(f"{name}() needs at least one value")
        if all(isinstance(item, (Quantity, Text)) for item in items):
            return _apply(name, list(items))
        raise ForgeEvalError(f"{name}() cannot compare rows")
    scalars = _scalars(args, name)
    try:
        if name in ("sin", "cos", "tan"):
            angle = _angle(scalars[0], name)
            value = {"sin": math.sin, "cos": math.cos, "tan": math.tan}[name](angle)
            return Quantity(value)
        if name in ("sinh", "cosh", "tanh"):
            x = _dimless(scalars[0], name)
            return Quantity(getattr(math, name)(x))
        if name in ("asin", "acos"):
            x = _dimless(scalars[0], name)
            if not -1.0 <= x <= 1.0:
                raise ForgeEvalError(f"{name}() needs a value between -1 and 1, found {x:g}")
            result = math.asin(x) if name == "asin" else math.acos(x)
            return Quantity(result, ANGLE)
        if name == "atan":
            return Quantity(math.atan(_dimless(scalars[0], name)), ANGLE)
        if name == "atan2":
            y, x = scalars
            if y.dim != x.dim:
                raise UnitError(f"atan2() needs two values of the same kind, found {describe_full(y.dim)} "
                                f"and {describe_full(x.dim)}")
            return Quantity(math.atan2(y.value, x.value), ANGLE)
        if name == "exp":
            return Quantity(cmath.exp(complex(scalars[0].value)) if scalars[0].is_complex
                            else math.exp(_dimless(scalars[0], name)))
        if name in ("ln", "log"):
            base = None
            if len(scalars) == 2:
                base = _dimless(scalars[1], name)
                if base <= 0 or base == 1:
                    raise ForgeEvalError("log() base must be positive and not 1")
            q = scalars[0]
            if q.is_complex:
                if base is not None:
                    raise ForgeEvalError("log() with two arguments needs a real number")
                result = cmath.log(complex(q.value))
                return Quantity(result)
            x = _dimless(q, name)
            if x <= 0:
                raise ForgeEvalError(f"{name}() needs a positive number, found {x:g}")
            if base is not None:
                return Quantity(math.log(x) / math.log(base))
            return Quantity(math.log(x) if name == "ln" else math.log10(x))
        if name in ("sqrt", "cbrt"):
            q = scalars[0]
            if name == "cbrt":
                if q.value < 0 and not q.is_complex:
                    return Quantity(-((-q.value) ** (1 / 3)), q.dim ** Fraction(1, 3))
                return q ** Quantity(1 / 3)
            if q.value < 0 and not q.is_complex:
                # The square root of a negative quantity is imaginary, which the language supports.
                return Quantity(_clean_root(complex(q.value) ** 0.5), q.dim ** Fraction(1, 2))
            return q ** Quantity(0.5)
        if name == "abs":
            q = scalars[0]
            if q.is_complex:
                return Quantity(abs(q.value), q.dim)
            keep = q.unit is not None and not q.unit.affine
            return Quantity(abs(q.value), q.dim, q.unit if keep else None)
    except OverflowError:
        raise ForgeEvalError(f"{name}() result is too large to represent") from None
    raise AssertionError(name)  # pragma: no cover


def _items(value, fname: str) -> List[Element]:
    if isinstance(value, Vector):
        return list(value.items)
    if isinstance(value, Matrix):
        return [Vector(row) for row in value.rows]
    raise ForgeEvalError(f"{fname}() requires a vector or matrix")


def sorted_items(items: List[Element], order: str) -> List[Element]:
    return ascending_all(items) if order == "asc" else descending_all(items)


def _trapz(args) -> Quantity:
    """trapz(y) or trapz(x, y): the trapezoidal estimate of an integral.

    `trapz(distance, force)` gives the work done; the result has the units of x times y (or of y
    alone when only the samples are given, where the spacing is one unit).
    """
    if len(args) == 1:
        values = numeric_items(args[0], "trapz")
        if len(values) < 2:
            raise ForgeEvalError("trapz() needs at least two values")
        dimension = values[0].dim
        total = sum(0.5 * (values[i].value + values[i + 1].value) for i in range(len(values) - 1))
        return Quantity(total, dimension)
    xs = numeric_items(args[0], "trapz")
    ys = numeric_items(args[1], "trapz")
    if len(xs) != len(ys):
        raise ForgeEvalError(f"trapz() needs x and y of the same length, found {len(xs)} and {len(ys)}")
    if len(xs) < 2:
        raise ForgeEvalError("trapz() needs at least two points")
    same_units(xs, "trapz")
    same_units(ys, "trapz")
    total = 0.0
    for index in range(len(xs) - 1):
        width = xs[index + 1].value - xs[index].value
        total += 0.5 * width * (ys[index].value + ys[index + 1].value)
    return Quantity(total, xs[0].dim * ys[0].dim)


def _linspace(args) -> Vector:
    start, stop, count = _scalars(args, "linspace")
    n = _plain_integer(count, "linspace() sample count")
    if n < 1 or n > 100000:
        raise ForgeEvalError("linspace() sample count must be between 1 and 100000")
    if start.dim != stop.dim:
        raise UnitError("linspace() endpoints must have matching units")
    if n == 1:
        return Vector((start,))
    return Vector(tuple(Quantity(start.value + i * (stop.value - start.value) / (n - 1), start.dim,
                                 start.unit) for i in range(n)))


def _logspace(args) -> Vector:
    start = _dimless(_scalar_in(args[0], "logspace"), "logspace")
    stop = _dimless(_scalar_in(args[1], "logspace"), "logspace")
    n = _plain_integer(args[2], "logspace() sample count") if len(args) == 3 else 50
    if n < 1 or n > 100000:
        raise ForgeEvalError("logspace() sample count must be between 1 and 100000")
    if n == 1:
        return Vector((Quantity(10.0 ** start),))
    return Vector(tuple(Quantity(10.0 ** (start + i * (stop - start) / (n - 1))) for i in range(n)))


def _reshape(args) -> Matrix:
    source, rows, columns = args
    items = _items(source, "reshape")
    r = _plain_integer(rows, "reshape() rows")
    c = _plain_integer(columns, "reshape() columns")
    if r * c != len(items):
        raise ForgeEvalError(f"reshape() needs {r}x{c} = {r * c} values, found {len(items)}")
    flat = []
    for item in items:
        if isinstance(item, Quantity):
            flat.append(item)
        else:
            flat.extend(item.items)  # rows are flattened
    return make_matrix([[flat[i * c + j] for j in range(c)] for i in range(r)])


def _surface(numeric, xs, ys, span=None) -> Matrix:
    """surface(f, xs, ys): rows follow ys (north-south), columns follow xs."""
    if not isinstance(xs, Vector) or not isinstance(ys, Vector):
        raise ForgeEvalError("surface() needs vectors of x and y coordinates", span)
    coordinates = [item for item in list(xs.items) + list(ys.items) if isinstance(item, Quantity)]
    if len(coordinates) != len(xs.items) + len(ys.items):
        raise ForgeEvalError("surface() needs numeric coordinates", span)
    return Matrix(tuple(
        tuple(Quantity(numeric(x.value, y.value)) for x in xs.items)  # type: ignore[union-attr]
        for y in ys.items
    ))


def _complex_part(name: str, q: Quantity) -> object:
    value = complex(q.value)
    keep = q.unit if q.unit is not None and not q.unit.affine else None
    if name == "real":
        return Quantity(value.real, q.dim, keep)
    if name == "imag":
        return Quantity(value.imag, q.dim, keep)
    if name == "mag":
        return Quantity(abs(value), q.dim, keep)
    if name == "arg":
        if value == 0:
            raise ForgeEvalError("arg() of zero has no phase angle")
        return Quantity(cmath.phase(value), ANGLE)
    return Quantity(complex(value.real, -value.imag), q.dim, keep)
