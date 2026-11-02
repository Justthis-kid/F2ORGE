"""Unit-aware vector and matrix values and their basic linear algebra operations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Tuple, Union

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


def inverse(matrix: Matrix) -> Matrix:
    rows, columns = matrix.shape
    if rows != columns:
        raise ForgeEvalError(f"inverse() requires a square matrix, found {rows}x{columns}")
    if any(not item.dim.is_dimensionless for row in matrix.rows for item in row):
        raise UnitError("inverse() currently requires a dimensionless matrix",
                        hint="Scale the matrix to dimensionless ratios before inverting it.")

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
    return Matrix(tuple(tuple(Quantity(value) for value in row[rows:]) for row in work))
