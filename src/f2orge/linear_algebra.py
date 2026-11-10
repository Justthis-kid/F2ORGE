"""Unit-aware vector and matrix values and their linear algebra operations.

A vector holds quantities, and — for data work — nested vectors or text.  A matrix is a vector
of rows, so `<1, 2>` is a 1x2 row, `[<1, 2>, <3, 4>]` is a
2x2 matrix, and a "ragged matrix" of rows with different lengths is how a data table is passed
around.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple, Union

from .dimensions import Dim
from .errors import ForgeEvalError, UnitError
from .quantity import Quantity
from .text import Text

Element = Union[Quantity, "Vector", Text]


@dataclass(frozen=True)
class Vector:
    items: Tuple[Element, ...]

    def __str__(self) -> str:
        return "<" + ", ".join(map(str, self.items)) + ">"

    @property
    def values(self) -> Tuple[Quantity, ...]:
        return self.items  # type: ignore[return-value]


@dataclass(frozen=True)
class Matrix:
    rows: Tuple[Tuple[Quantity, ...], ...]

    def __str__(self) -> str:
        return "[" + ", ".join("[" + ", ".join(map(str, row)) + "]" for row in self.rows) + "]"

    @property
    def shape(self) -> Tuple[int, int]:
        return len(self.rows), len(self.rows[0])


LinearValue = Union[Vector, Matrix]
Value = Union[Quantity, Vector, Matrix, Text]




def make_vector(items: Sequence[Value]) -> Vector:
    if not items:
        return Vector(())  # <> is an empty vector, useful as the start of a loop accumulator
    if all(isinstance(item, Quantity) for item in items):
        return Vector(tuple(items))
    if any(isinstance(item, (Vector, Matrix)) for item in items):
        raise ForgeEvalError("a vector cannot contain nested vectors or matrices",
                             hint="Write a matrix as [<row 1>, <row 2>], and use a loop to collect rows.")
    return Vector(tuple(items))


def make_matrix(rows: Sequence[Sequence[Value]]) -> Matrix:
    """Rows of scalar quantities.  A one-row matrix is fine; ragged rows are rejected."""
    if not rows or not rows[0]:
        raise ForgeEvalError("a matrix must have at least one row and one column")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ForgeEvalError("all matrix rows must have the same number of values")
    if any(not isinstance(item, Quantity) for row in rows for item in row):
        raise ForgeEvalError("matrix elements must be scalar quantities")
    return Matrix(tuple(tuple(row) for row in rows))


def is_scalar(value: Value) -> bool:
    return isinstance(value, (Quantity, Text))


def size(value: Value) -> int:
    """Length of a vector, rows of a matrix, or 1 for a scalar or text."""
    if isinstance(value, Vector):
        return len(value.items)
    if isinstance(value, Matrix):
        return len(value.rows)
    return 1


# ---- predicates used by sort() / select() ------------------------------------------------------
def _quantity_key(item: Element):
    if isinstance(item, Vector):
        return item.items[0] if item.items else Quantity(0)
    return item


def ascending_all(items: Sequence[Element]) -> List[Element]:
    """Elements sorted by value: numbers numerically, text alphabetically, rows by first element."""
    elements = list(items)
    kinds = {type(_quantity_key(item)) for item in elements}
    if kinds == {Text}:
        return sorted(elements, key=lambda item: str(_quantity_key(item)))
    if any(not isinstance(_quantity_key(item), Quantity) for item in elements):
        raise ForgeEvalError("sort() needs values of one kind: all numbers or all text")
    return sorted(elements, key=lambda item: _quantity_key(item).value)


def descending_all(items: Sequence[Element]) -> List[Element]:
    return list(reversed(ascending_all(items)))


# ---- arithmetic ---------------------------------------------------------------------------------
def negate(value: Value) -> Value:
    if isinstance(value, Quantity):
        return -value
    if isinstance(value, Text):
        raise ForgeEvalError("cannot negate text")
    if isinstance(value, Vector):
        return Vector(tuple(negate(item) for item in value.items))
    return Matrix(tuple(tuple(-item for item in row) for row in value.rows))


def add(left: Value, right: Value) -> Value:
    if isinstance(left, Quantity) and isinstance(right, Quantity):
        return left + right
    if isinstance(left, Text) or isinstance(right, Text):
        raise ForgeEvalError("cannot add text with +", hint='Join text inside a quoted string, e.g. print "x:", x')
    if isinstance(left, Vector) and isinstance(right, Vector):
        if not left.items:
            return right
        if not right.items:
            return left
        if len(left.items) != len(right.items):
            raise ForgeEvalError("vectors must have the same length for addition")
        return Vector(tuple(add(a, b) for a, b in zip(left.items, right.items)))
    if isinstance(left, Matrix) and isinstance(right, Matrix):
        if left.shape != right.shape:
            raise ForgeEvalError("matrices must have the same shape for addition")
        return Matrix(tuple(tuple(a + b for a, b in zip(arow, brow))
                            for arow, brow in zip(left.rows, right.rows)))
    raise ForgeEvalError("addition requires values of the same kind and shape")


def subtract(left: Value, right: Value) -> Value:
    if isinstance(left, Quantity) and isinstance(right, Quantity):
        return left - right
    if isinstance(left, Text) or isinstance(right, Text):
        raise ForgeEvalError("cannot subtract text")
    if isinstance(left, Vector) and isinstance(right, Vector):
        if len(left.items) != len(right.items):
            raise ForgeEvalError("vectors must have the same length for subtraction")
        return Vector(tuple(subtract(a, b) for a, b in zip(left.items, right.items)))
    if isinstance(left, Matrix) and isinstance(right, Matrix):
        if left.shape != right.shape:
            raise ForgeEvalError("matrices must have the same shape for subtraction")
        return Matrix(tuple(tuple(a - b for a, b in zip(arow, brow))
                            for arow, brow in zip(left.rows, right.rows)))
    raise ForgeEvalError("subtraction requires values of the same kind and shape")


def multiply(left: Value, right: Value) -> Value:
    if isinstance(left, Quantity) and isinstance(right, Quantity):
        return left * right
    if isinstance(left, (Vector, Matrix)) and isinstance(right, Quantity):
        return scale(left, right, divide=False)
    if isinstance(left, Quantity) and isinstance(right, (Vector, Matrix)):
        return scale(right, left, divide=False)
    if isinstance(left, Vector) and isinstance(right, Vector):
        if len(left.items) != len(right.items):
            raise ForgeEvalError("vectors must have the same length for a dot product")
        if any(isinstance(item, (Vector, Text)) for item in left.items):
            raise ForgeEvalError("element-by-element products need numeric vectors")
        return _sum_products(tuple(zip(left.items, right.items)))  # type: ignore[arg-type]
    if isinstance(left, Matrix) and isinstance(right, Vector):
        rows, columns = left.shape
        if columns != len(right.items):
            raise ForgeEvalError(
                f"cannot multiply a {rows}x{columns} matrix by a vector of length {len(right.items)}"
            )
        return Vector(tuple(_sum_products(tuple(zip(row, right.items))) for row in left.rows))  # type: ignore[arg-type]
    if isinstance(left, Vector) and isinstance(right, Matrix):
        rows, columns = right.shape
        if len(left.items) != rows:
            raise ForgeEvalError(
                f"cannot multiply a vector of length {len(left.items)} by a {rows}x{columns} matrix"
            )
        return Vector(tuple(
            _sum_products(tuple((left.items[i], right.rows[i][j]) for i in range(rows)))  # type: ignore[arg-type]
            for j in range(columns)
        ))
    if isinstance(left, Matrix) and isinstance(right, Matrix):
        rows, inner = left.shape
        other_inner, columns = right.shape
        if inner != other_inner:
            raise ForgeEvalError(
                f"cannot multiply a {rows}x{inner} matrix by a {other_inner}x{columns} matrix"
            )
        return Matrix(tuple(tuple(
            _sum_products(tuple((left.rows[i][k], right.rows[k][j]) for k in range(inner)))
            for j in range(columns)) for i in range(rows)))
    if isinstance(left, Text) or isinstance(right, Text):
        raise ForgeEvalError("cannot multiply text")
    raise ForgeEvalError("unsupported multiplication between these values")


def divide(left: Value, right: Value) -> Value:
    if isinstance(left, Quantity) and isinstance(right, Quantity):
        return left / right
    if isinstance(left, (Vector, Matrix)) and isinstance(right, Quantity):
        return scale(left, right, divide=True)
    if isinstance(left, Text) or isinstance(right, Text):
        raise ForgeEvalError("cannot divide text")
    raise ForgeEvalError("cannot divide by a vector or matrix",
                         hint="Use inverse(A) * b to solve A x = b, or the ./ operator for element-by-element division.")


def elementwise(left: Value, right: Value, op: str) -> Value:
    """`.*` and `./`: multiply or divide matching elements.  A scalar applies to every element."""
    if isinstance(left, Quantity) and isinstance(right, Quantity):
        return multiply(left, right) if op == "*" else divide(left, right)
    if isinstance(left, Quantity):
        if op == "/":
            raise ForgeEvalError("cannot divide a plain value by a vector or matrix")
        return elementwise(right, left, op)
    if isinstance(right, Quantity):
        return scale(left, right, divide=(op == "/"))
    if type(left) is not type(right):
        raise ForgeEvalError(f"{op} needs two vectors or two matrices of the same shape")
    if isinstance(left, Vector) and isinstance(right, Vector):
        if len(left.items) != len(right.items):
            raise ForgeEvalError("vectors must have the same length for element-by-element operations")
        pairs = zip(left.items, right.items)
    elif isinstance(left, Matrix) and isinstance(right, Matrix):
        if left.shape != right.shape:
            raise ForgeEvalError("matrices must have the same shape for element-by-element operations")
        pairs = zip([item for row in left.rows for item in row], [item for row in right.rows for item in row])
    else:  # pragma: no cover
        raise ForgeEvalError(f"cannot apply {op}")
    results = []
    for a, b in pairs:
        if not isinstance(a, Quantity) or not isinstance(b, Quantity):
            raise ForgeEvalError("element-by-element operations need numeric values")
        results.append(a * b if op == "*" else a / b)
    if isinstance(left, Vector):
        return Vector(tuple(results))
    rows, columns = left.shape
    return Matrix(tuple(tuple(results[i * columns + j] for j in range(columns)) for i in range(rows)))





def scale(value: LinearValue, scalar: Quantity, *, divide: bool) -> LinearValue:
    if divide and scalar.value == 0:
        raise ForgeEvalError("division by zero")

    def apply(item):
        if not isinstance(item, Quantity):
            raise ForgeEvalError("only numeric vectors and matrices can be scaled")
        return item / scalar if divide else item * scalar

    if isinstance(value, Vector):
        return Vector(tuple(apply(item) for item in value.items))
    return Matrix(tuple(tuple(apply(item) for item in row) for row in value.rows))


def _sum_products(pairs: Sequence[Tuple[Quantity, Quantity]]) -> Quantity:
    products = [left * right for left, right in pairs]
    total = products[0]
    for product in products[1:]:
        total = total + product
    return total


def concatenate(values: Sequence[Value]) -> Value:
    """[a, b, c] for vectors, or rows combined with rows."""
    if not values:
        return Vector(())
    if all(isinstance(value, Vector) for value in values):
        items: List[Element] = []
        for value in values:
            items.extend(value.items)  # type: ignore[union-attr]
        return Vector(tuple(items))
    if all(isinstance(value, Matrix) for value in values):
        widths = {value.shape[1] for value in values}  # type: ignore[union-attr]
        if len(widths) != 1:
            raise ForgeEvalError("matrices joined with [,] need the same number of columns")
        rows: List[Tuple[Quantity, ...]] = []
        for value in values:
            rows.extend(value.rows)  # type: ignore[union-attr]
        return Matrix(tuple(rows))
    raise ForgeEvalError("[,] joins vectors into one vector, or matrices into more rows")


def transpose(matrix: Matrix) -> Matrix:
    rows, columns = matrix.shape
    return Matrix(tuple(tuple(matrix.rows[i][j] for i in range(rows)) for j in range(columns)))


def _matrix_dimensions(matrix: Matrix) -> Tuple[list, list]:
    """Factor a matrix's units into one dimension per row and one per column."""
    rows, columns = matrix.shape
    row_dims = [matrix.rows[i][0].dim for i in range(rows)]
    column_dims = [matrix.rows[0][j].dim / row_dims[0] for j in range(columns)]
    for i in range(rows):
        for j in range(columns):
            if matrix.rows[i][j].dim != row_dims[i] * column_dims[j]:
                raise UnitError(
                    "matrix units must factor consistently into row and column dimensions",
                    hint="Use one consistent unit per row and column before inverting or taking a determinant.",
                )
    return row_dims, column_dims


def _product_dims(row_dims: Sequence[Dim], column_dims: Sequence[Dim]) -> Dim:
    result = Dim.of()
    for dim in list(row_dims) + list(column_dims):
        result = result * dim
    return result


def inverse(matrix: Matrix) -> Matrix:
    rows, columns = matrix.shape
    if rows != columns:
        raise ForgeEvalError(f"inverse() requires a square matrix, found {rows}x{columns}")
    row_dims, column_dims = _matrix_dimensions(matrix)

    work = [[item.value for item in row] +
            [1.0 if i == j else 0.0 for j in range(rows)]
            for i, row in enumerate(matrix.rows)]
    for column in range(rows):
        pivot = max(range(column, rows), key=lambda row: abs(work[row][column]))
        if abs(work[pivot][column]) <= 1e-15:
            raise ForgeEvalError("inverse() cannot invert a singular matrix")
        work[column], work[pivot] = work[pivot], work[column]
        divisor = work[column][column]
        work[column] = [value / divisor for value in work[column]]
        for row in range(rows):
            if row == column:
                continue
            factor = work[row][column]
            work[row] = [value - factor * pivot_value
                         for value, pivot_value in zip(work[row], work[column])]
    return Matrix(tuple(
        tuple(Quantity(work[i][rows + j], (column_dims[i] * row_dims[j]) ** -1)
              for j in range(rows))
        for i in range(rows)
    ))


def determinant(matrix: Matrix) -> Quantity:
    rows, columns = matrix.shape
    if rows != columns:
        raise ForgeEvalError(f"det() requires a square matrix, found {rows}x{columns}")
    row_dims, column_dims = _matrix_dimensions(matrix)
    work = [[item.value for item in row] for row in matrix.rows]
    result = 1.0
    for column in range(rows):
        pivot = max(range(column, rows), key=lambda row: abs(work[row][column]))
        if work[pivot][column] == 0:
            return Quantity(0, _product_dims(row_dims, column_dims))
        if pivot != column:
            work[column], work[pivot] = work[pivot], work[column]
            result *= -1
        value = work[column][column]
        result *= value
        for row in range(column + 1, rows):
            factor = work[row][column] / value
            for j in range(column + 1, rows):
                work[row][j] -= factor * work[column][j]
    return Quantity(result, _product_dims(row_dims, column_dims))


def cross(left: Vector, right: Vector) -> Vector:
    if len(left.items) != 3 or len(right.items) != 3:
        raise ForgeEvalError("cross() requires two vectors of length 3")
    a, b = left.items, right.items
    if any(not isinstance(item, Quantity) for item in a + b):
        raise ForgeEvalError("cross() requires numeric vectors")
    return Vector((a[1] * b[2] - a[2] * b[1],  # type: ignore[operator]
                   a[2] * b[0] - a[0] * b[2],  # type: ignore[operator]
                   a[0] * b[1] - a[1] * b[0]))  # type: ignore[operator]


def index(value: Value, indices: Sequence[Value]) -> Value:
    """Zero-based indexing: v[i] for a vector, m[i] for a row, m[i, j] for one element."""
    if len(indices) not in (1, 2) or any(
        not isinstance(item, Quantity) or not item.is_plain or not item.value.is_integer()
        for item in indices
    ):
        raise ForgeEvalError("indices must be plain whole numbers (zero-based)")
    positions = [int(item.value) for item in indices]  # type: ignore[union-attr]
    if any(position < 0 for position in positions):
        raise ForgeEvalError("indices must be non-negative")
    if isinstance(value, Vector) and len(positions) == 1:
        if positions[0] >= len(value.items):
            raise ForgeEvalError("vector index is out of range")
        return value.items[positions[0]]
    if isinstance(value, Matrix) and len(positions) == 1:
        if positions[0] >= value.shape[0]:
            raise ForgeEvalError("matrix row index is out of range")
        return Vector(value.rows[positions[0]])
    if isinstance(value, Matrix) and len(positions) == 2:
        if positions[0] >= value.shape[0] or positions[1] >= value.shape[1]:
            raise ForgeEvalError("matrix index is out of range")
        return value.rows[positions[0]][positions[1]]
    raise ForgeEvalError("indexing expects a vector with one index or a matrix with one or two indices")


def select(value: Value, indices: Sequence[Value], count: Optional[Value] = None) -> List[Value]:
    """Rows, columns, or individual elements: x[i], M[i], M[:, j], M[:, j:j+n], M[i, :]."""
    if not isinstance(value, (Vector, Matrix)):
        raise ForgeEvalError("cardinal indexing needs a vector or a matrix")
    take = size(value)
    if count is None:
        if len(indices) > 2:
            raise ForgeEvalError("cardinal indexing takes at most two indices")
    elif len(indices) != 1:
        raise ForgeEvalError("a counted selection such as M[:, j:k] needs exactly one index")

    def positions_of(selector: Value, limit: int, what: str) -> List[int]:
        if isinstance(selector, Vector):
            if count is not None:
                raise ForgeEvalError("a counted selection uses a plain number after ':'")
            out = []
            for item in selector.items:
                if not isinstance(item, Quantity) or not item.is_plain or not item.value.is_integer():
                    raise ForgeEvalError(f"{what} positions must be whole numbers")
                if not 0 <= int(item.value) < limit:
                    raise ForgeEvalError(f"{what} index {int(item.value)} is out of range")
                out.append(int(item.value))
            return out
        if not isinstance(selector, Quantity) or not selector.is_plain or not selector.value.is_integer():
            raise ForgeEvalError(f"{what} position must be a whole number")
        first = int(selector.value)
        last = first if count is None else first + (int(count.value) if isinstance(count, Quantity) else 0)
        if count is not None and not count.value.is_integer():
            raise ForgeEvalError("a counted selection needs a whole number after ':'")
        if last < first:
            raise ForgeEvalError(f"the end of a counted selection must not come before its start")
        if first < 0 or last > limit:
            raise ForgeEvalError(f"{what} index is out of range")
        return list(range(first, last))

    if isinstance(value, Vector):
        if len(indices) > 1:
            raise ForgeEvalError("a vector takes one index")
        chosen = positions_of(indices[0], take, "vector")
        items: List[Element] = [value.items[i] for i in chosen]
        return [Vector(tuple(items))] if count is not None else items

    rows, columns = value.shape
    if len(indices) == 2:
        row_positions = positions_of(indices[0], rows, "row")
        column_positions = positions_of(indices[1], columns, "column")
        cells = [[value.rows[i][j] for j in column_positions] for i in row_positions]
        if count is not None:
            return [Matrix(tuple(tuple(row) for row in cells))]
        return [Vector(tuple(row)) for row in cells]
    chosen_rows = positions_of(indices[0], rows, "row")
    if count is not None:
        return [Matrix(tuple(value.rows[i] for i in chosen_rows))]
    return [Vector(value.rows[i]) for i in chosen_rows]


def make_range(start: Value, stop: Value, step: Value) -> Vector:
    """range(a, b, step): a numeric sequence with both endpoints included."""
    for item, label in ((start, "start"), (stop, "stop"), (step, "step")):
        if not isinstance(item, Quantity):
            raise ForgeEvalError(f"range() {label} must be a number, found {item}")
    if step.value == 0:
        raise ForgeEvalError("range() step cannot be zero")
    if start.dim != stop.dim:
        raise UnitError("range() start and stop must have compatible units")
    if step.is_plain and not start.dim.is_dimensionless:
        step = Quantity(step.value, start.dim, start.unit)
    if step.dim != start.dim:
        raise UnitError("range() step must have compatible units")
    values = []
    current = start.value
    predicate = (lambda x: x <= stop.value + 1e-12 * max(1.0, abs(stop.value))) if step.value > 0 \
        else (lambda x: x >= stop.value - 1e-12 * max(1.0, abs(stop.value)))
    while predicate(current):
        if len(values) >= 1000000:
            raise ForgeEvalError("range() is limited to 1000000 values")
        values.append(Quantity(current, start.dim, start.unit))
        current += step.value
    return Vector(tuple(values))


# ---- statistics ---------------------------------------------------------------------------------
def numeric_items(value: Value, function: str) -> List[Quantity]:
    if isinstance(value, Matrix):
        items = [item for row in value.rows for item in row]
    elif isinstance(value, Vector):
        items = list(value.items)
    else:
        raise ForgeEvalError(f"{function}() requires a vector or matrix of numbers")
    if not items or any(not isinstance(item, Quantity) for item in items):
        raise ForgeEvalError(f"{function}() requires numbers, found text or rows")
    return items  # type: ignore[return-value]


def _same_dim(items: Sequence[Quantity], function: str) -> Dim:
    first = items[0].dim
    if any(item.dim != first for item in items):
        raise UnitError(f"{function}() requires values with matching units")
    return first


def mean(items: Sequence[Quantity], function: str = "mean") -> Quantity:
    dim = _same_dim(items, function)
    unit = next((item.unit for item in items if item.unit is not None), None)
    return Quantity(sum(item.value for item in items) / len(items), dim, unit)


def median(items: Sequence[Quantity]) -> Quantity:
    _same_dim(items, "median")
    numbers = sorted(items, key=lambda item: item.value)
    middle = len(numbers) // 2
    if len(numbers) % 2:
        return numbers[middle]
    halfway = Quantity((numbers[middle - 1].value + numbers[middle].value) / 2, numbers[0].dim)
    return halfway


def percentile(items: Sequence[Quantity], fraction: float) -> Quantity:
    """Percentile with linear interpolation between closest ranks."""
    _same_dim(items, "percentile")
    numbers = sorted(item.value for item in items)
    if not numbers:
        raise ForgeEvalError("percentile() needs at least one value")
    if not 0 <= fraction <= 1:
        raise ForgeEvalError("percentile() needs a fraction from 0 to 1")
    position = (len(numbers) - 1) * fraction
    low = math.floor(position)
    high = min(low + 1, len(numbers) - 1)
    weight = position - low
    value = numbers[low] + (numbers[high] - numbers[low]) * weight
    return Quantity(value, items[0].dim)


def variance(items: Sequence[Quantity], sample: bool = True) -> Quantity:
    _same_dim(items, "variance" if sample else "populationVariance")
    if sample and len(items) < 2:
        raise ForgeEvalError("variance() needs at least two values; use populationVariance()")
    average = sum(item.value for item in items) / len(items)
    total = sum((item.value - average) ** 2 for item in items)
    return Quantity(total / (len(items) - 1 if sample else len(items)), items[0].dim ** 2)


def standard_deviation(items: Sequence[Quantity], sample: bool = True) -> Quantity:
    squared = variance(items, sample)
    return Quantity(math.sqrt(squared.value), items[0].dim)


def cumsum(items: Sequence[Quantity], function: str = "cumsum") -> Vector:
    _same_dim(items, function)
    total = items[0]
    out = [total]
    for item in items[1:]:
        total = total + item
        out.append(total)
    return Vector(tuple(out))


def normalize(items: Sequence[Quantity], function: str = "normalize") -> Vector:
    total = sum(item.value for item in items)
    if total == 0:
        raise ForgeEvalError(f"{function}() needs values that do not sum to zero")
    return Vector(tuple(Quantity(item.value / total) for item in items))


def diff(items: Sequence[Quantity]) -> Vector:
    _same_dim(items, "diff")
    return Vector(tuple(items[i + 1] - items[i] for i in range(len(items) - 1)))


def linear_regression(x: Sequence[Quantity], y: Sequence[Quantity]) -> Tuple[Quantity, Quantity, float]:
    """Least-squares y = slope*x + intercept, and the coefficient of determination R²."""
    if len(x) != len(y):
        raise ForgeEvalError("linreg() needs x and y with the same length")
    if len(x) < 2:
        raise ForgeEvalError("linreg() needs at least two points")
    _same_dim(x, "linreg")  # x values share a unit; y too
    _same_dim(y, "linreg")
    xs = [item.value for item in x]
    ys = [item.value for item in y]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    sxx = sum((value - x_mean) ** 2 for value in xs)
    if sxx == 0:
        raise ForgeEvalError("linreg() needs at least two different x values")
    sxy = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(len(xs)))
    slope = sxy / sxx
    intercept = y_mean - slope * x_mean
    ss_total = sum((value - y_mean) ** 2 for value in ys)
    predicted = [slope * value + intercept for value in xs]
    ss_residual = sum((ys[i] - predicted[i]) ** 2 for i in range(len(ys)))
    r_squared = 1.0 if ss_total == 0 else 1.0 - ss_residual / ss_total
    return (Quantity(slope, y[0].dim / x[0].dim), Quantity(intercept, y[0].dim), r_squared)


# ---- simultaneous linear systems ---------------------------------------------------------------
def solve_linear(coefficients: Sequence[Sequence[Quantity]], constants: Sequence[Quantity]) -> List[Quantity]:
    """Gaussian elimination with partial pivoting on A x = b, keeping units exact.

    Each row may have its own unit; each unknown gets the unit that makes every row consistent.
    """
    n = len(constants)
    if n == 0 or len(coefficients) != n:
        raise ForgeEvalError("solve_system() needs as many equations as unknowns")
    if any(len(row) != n for row in coefficients):
        raise ForgeEvalError("solve_system() needs as many equations as unknowns")
    # The unit of an unknown is whatever makes its first equation balance.
    unknown_dims: List[Dim] = [Dim.of()] * n
    for i, row in enumerate(coefficients):
        for j, item in enumerate(row):
            if unknown_dims[j].is_dimensionless and not item.dim.is_dimensionless:
                unknown_dims[j] = constants[i].dim / item.dim
    for i, row in enumerate(coefficients):
        for j, item in enumerate(row):
            if item.dim * unknown_dims[j] != constants[i].dim:
                raise UnitError(
                    "the units of this equation cannot be balanced for the unknowns",
                    hint="Every term on one side of an equation must measure the same kind of quantity.",
                )
    work = [[coefficients[i][j].value for j in range(n)] + [constants[i].value] for i in range(n)]
    for column in range(n):
        pivot = max(range(column, n), key=lambda row: abs(work[row][column]))
        if abs(work[pivot][column]) <= 1e-14:
            raise ForgeEvalError("this system has no single solution: a combination of the equations "
                                 "degenerates into 0 = 0 or contradicts itself")
        work[column], work[pivot] = work[pivot], work[column]
        divisor = work[column][column]
        work[column] = [value / divisor for value in work[column]]
        for row in range(n):
            if row == column:
                continue
            factor = work[row][column]
            work[row] = [value - factor * pivot_value
                         for value, pivot_value in zip(work[row], work[column])]
    return [Quantity(work[i][n], unknown_dims[i]) for i in range(n)]


def polynomial_roots(coefficients: Sequence[float]) -> List[float]:
    """Real roots of a[0] + a[1]x + ... + a[n]x^n."""
    coefficients = list(coefficients)
    while coefficients and abs(coefficients[-1]) < 1e-300:
        coefficients.pop()
    degree = len(coefficients) - 1
    if degree < 1:
        return []
    if degree == 1:
        return [-coefficients[0] / coefficients[1]]
    if degree == 2:
        a, b, c = coefficients[2], coefficients[1], coefficients[0]
        discriminant = b * b - 4 * a * c
        if discriminant < 0:
            return []
        root = math.sqrt(discriminant)
        return [(-b - root) / (2 * a), (-b + root) / (2 * a)]
    # Durand–Kerner iteration finds all (complex) roots reliably for moderate degrees.
    n = degree
    top = coefficients[-1]
    normalized = [value / top for value in coefficients[:-1]]
    roots = [complex(0.4 + 0.9j) ** k for k in range(1, n + 1)]
    for _ in range(500):
        delta = 0.0
        for i in range(n):
            value = 1 + 0j
            for k in range(n - 1, -1, -1):
                value = value * roots[i] + normalized[k]
            product = 1 + 0j
            for j in range(n):
                if j != i:
                    product *= roots[i] - roots[j]
            if product == 0:
                continue
            change = value / product
            roots[i] -= change
            delta = max(delta, abs(change))
        if delta < 1e-14:
            break
    real = [root.real for root in roots if abs(root.imag) <= 1e-8 * max(1.0, abs(root.real))]
    return real



