"""Unit-aware vector and matrix values and their basic linear algebra operations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Tuple, Union

from .dimensions import Dim
from .errors import ForgeEvalError, UnitError
from .quantity import Quantity


@dataclass(frozen=True)
class Vector:
    items: Tuple[Quantity, ...]

    def __str__(self) -> str:
        return "<" + ", ".join(map(str, self.items)) + ">"


@dataclass(frozen=True)
class Matrix:
    rows: Tuple[Tuple[Quantity, ...], ...]

    def __str__(self) -> str:
        return "[" + ", ".join("[" + ", ".join(map(str, row)) + "]" for row in self.rows) + "]"

    @property
    def shape(self) -> Tuple[int, int]:
        return len(self.rows), len(self.rows[0])


LinearValue = Union[Vector, Matrix]
Value = Union[Quantity, Vector, Matrix]


def make_vector(items: Sequence[Value]) -> Vector:
    if not items:
        raise ForgeEvalError("a vector must contain at least one value")
    if any(not isinstance(item, Quantity) for item in items):
        raise ForgeEvalError("vector elements must be scalar quantities")
    return Vector(tuple(items))


def make_matrix(rows: Sequence[Sequence[Value]]) -> Matrix:
    if not rows or not rows[0]:
        raise ForgeEvalError("a matrix must have at least one row and one column")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ForgeEvalError("all matrix rows must have the same number of values")
    if any(not isinstance(item, Quantity) for row in rows for item in row):
        raise ForgeEvalError("matrix elements must be scalar quantities")
    return Matrix(tuple(tuple(row) for row in rows))


def negate(value: Value) -> Value:
    if isinstance(value, Quantity):
        return -value
    if isinstance(value, Vector):
        return Vector(tuple(-item for item in value.items))
    return Matrix(tuple(tuple(-item for item in row) for row in value.rows))


def add(left: Value, right: Value) -> Value:
    if isinstance(left, Quantity) and isinstance(right, Quantity):
        return left + right
    if isinstance(left, Vector) and isinstance(right, Vector):
        if len(left.items) != len(right.items):
            raise ForgeEvalError("vectors must have the same length for addition")
        return Vector(tuple(a + b for a, b in zip(left.items, right.items)))
    if isinstance(left, Matrix) and isinstance(right, Matrix):
        if left.shape != right.shape:
            raise ForgeEvalError("matrices must have the same shape for addition")
        return Matrix(tuple(tuple(a + b for a, b in zip(arow, brow))
                            for arow, brow in zip(left.rows, right.rows)))
    raise ForgeEvalError("addition requires values of the same kind and shape")


def subtract(left: Value, right: Value) -> Value:
    if isinstance(left, Quantity) and isinstance(right, Quantity):
        return left - right
    if isinstance(left, Vector) and isinstance(right, Vector):
        if len(left.items) != len(right.items):
            raise ForgeEvalError("vectors must have the same length for subtraction")
        return Vector(tuple(a - b for a, b in zip(left.items, right.items)))
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
        return _sum_products(tuple(zip(left.items, right.items)))
    if isinstance(left, Matrix) and isinstance(right, Vector):
        rows, columns = left.shape
        if columns != len(right.items):
            raise ForgeEvalError(
                f"cannot multiply a {rows}x{columns} matrix by a vector of length {len(right.items)}"
            )
        return Vector(tuple(_sum_products(tuple(zip(row, right.items))) for row in left.rows))
    if isinstance(left, Vector) and isinstance(right, Matrix):
        rows, columns = right.shape
        if len(left.items) != rows:
            raise ForgeEvalError(
                f"cannot multiply a vector of length {len(left.items)} by a {rows}x{columns} matrix"
            )
        return Vector(tuple(
            _sum_products(tuple((left.items[i], right.rows[i][j]) for i in range(rows)))
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
    raise ForgeEvalError("unsupported multiplication between these values")


def divide(left: Value, right: Value) -> Value:
    if isinstance(left, Quantity) and isinstance(right, Quantity):
        return left / right
    if isinstance(left, (Vector, Matrix)) and isinstance(right, Quantity):
        return scale(left, right, divide=True)
    raise ForgeEvalError("division is supported only by a scalar quantity")


def scale(value: LinearValue, scalar: Quantity, *, divide: bool) -> LinearValue:
    if divide and scalar.value == 0:
        raise ForgeEvalError("division by zero")

    def apply(item: Quantity) -> Quantity:
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
    return Vector((a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
                   a[0] * b[1] - a[1] * b[0]))


def index(value: Value, indices: Sequence[Value]) -> Value:
    """Zero-based indexing: v[i] for a vector, m[i] for a row, m[i, j] for one element."""
    if len(indices) not in (1, 2) or any(
        not isinstance(item, Quantity) or not item.is_plain or not item.value.is_integer()
        for item in indices
    ):
        raise ForgeEvalError("indices must be plain whole numbers (zero-based)")
    positions = [int(item.value) for item in indices]
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
