"""Quantity: a number carrying a physical dimension.

The value is always stored in coherent SI (metres, kilograms, seconds, kelvin ...).  `unit` is
only a *display hint* remembering how the quantity was written, so `150 kg` prints as kg while
`kg*m/s^2` prints as N.  The rules for which hint survives an operation:

    + and -        the left operand's hint (temperature differences become K)
    * and /        kept only when the other side is a plain number ("2 * 5 ft" -> "10 ft");
                   otherwise the result prints in simplified SI ("kg*m/s^2" -> "N")
    ^, functions   simplified SI
"""
from __future__ import annotations

import math
from fractions import Fraction
from typing import Optional, Union

from .dimensions import DIMLESS, Dim, describe_full
from .errors import ForgeEvalError, UnitError
from .units import KELVIN, Unit

Number = Union[int, float]


def format_number(x: float) -> str:
    """10 significant digits, no trailing zeros: 3.0480000000000005 -> '3.048', 2.0 -> '2'."""
    if x == 0:
        return "0"
    if not math.isfinite(x):
        return str(x)
    return f"{x:.10g}"


def _safe_pow(base: float, exp: float) -> float:
    try:
        return math.pow(base, exp)
    except ValueError:
        raise ForgeEvalError("cannot raise a negative number to a fractional power") from None
    except ZeroDivisionError:
        raise ForgeEvalError("division by zero (0 raised to a negative power)") from None
    except OverflowError:
        raise ForgeEvalError("the result is too large to represent") from None


class Quantity:
    __slots__ = ("value", "dim", "unit")

    def __init__(self, value: float, dim: Dim = DIMLESS, unit: Optional[Unit] = None):
        self.value = float(value)
        self.dim = dim
        self.unit = unit

    # ---- construction / conversion -------------------------------------------------------
    @staticmethod
    def from_unit(number: float, unit: Unit) -> "Quantity":
        return Quantity(number * unit.scale + unit.offset, unit.dim, unit)

    def magnitude(self, unit: Unit) -> float:
        """The number you would write next to `unit`."""
        return (self.value - unit.offset) / unit.scale

    def to(self, unit: Unit) -> "Quantity":
        if unit.dim != self.dim:
            raise UnitError(
                f"cannot convert {describe_full(self.dim)} to {describe_full(unit.dim)}",
                hint="Both sides of a conversion must measure the same kind of quantity.",
            )
        return Quantity(self.value, self.dim, unit)

    @property
    def is_plain(self) -> bool:
        """A bare number: dimensionless and with no unit hint."""
        return self.dim.is_dimensionless and self.unit is None

    # ---- arithmetic ----------------------------------------------------------------------
    def _check_same(self, other: "Quantity", verb: str) -> None:
        if self.dim != other.dim:
            if verb == "add":
                text = f"cannot add {describe_full(self.dim)} and {describe_full(other.dim)}"
            else:
                text = f"cannot subtract {describe_full(other.dim)} from {describe_full(self.dim)}"
            raise UnitError(text, hint="+ and - only work between quantities of the same kind.")

    def __add__(self, other: "Quantity") -> "Quantity":
        other = _q(other)
        self._check_same(other, "add")
        a_aff = self.unit is not None and self.unit.affine
        b_aff = other.unit is not None and other.unit.affine
        if a_aff and b_aff:
            raise UnitError(
                "cannot add two absolute temperatures",
                hint="Use K for temperature differences, e.g. 20 degC + 5 K.",
            )
        unit = other.unit if b_aff else (self.unit if self.unit is not None else other.unit)
        return Quantity(self.value + other.value, self.dim, unit)

    def __sub__(self, other: "Quantity") -> "Quantity":
        other = _q(other)
        self._check_same(other, "subtract")
        a_aff = self.unit is not None and self.unit.affine
        b_aff = other.unit is not None and other.unit.affine
        if b_aff:  # absolute - absolute is an interval, measured in K
            return Quantity(self.value - other.value, self.dim, KELVIN)
        unit = self.unit if self.unit is not None else other.unit
        return Quantity(self.value - other.value, self.dim, unit if (a_aff or unit is not None) else None)

    def __mul__(self, other: "Quantity") -> "Quantity":
        other = _q(other)
        unit = None
        if other.is_plain and self.unit is not None and not self.unit.affine:
            unit = self.unit
        elif self.is_plain and other.unit is not None and not other.unit.affine:
            unit = other.unit
        return Quantity(self.value * other.value, self.dim * other.dim, unit)

    def __truediv__(self, other: "Quantity") -> "Quantity":
        other = _q(other)
        if other.value == 0:
            raise ForgeEvalError("division by zero")
        unit = self.unit if (other.is_plain and self.unit is not None and not self.unit.affine) else None
        return Quantity(self.value / other.value, self.dim / other.dim, unit)

    def __pow__(self, other: "Quantity") -> "Quantity":
        other = _q(other)
        if not other.dim.is_dimensionless:
            raise UnitError(
                f"an exponent must be a plain number, found {describe_full(other.dim)}",
                hint="Divide by a reference quantity first if you need a dimensionless ratio.",
            )
        x = other.value
        if self.dim.is_dimensionless:
            return Quantity(_safe_pow(self.value, x))
        frac = Fraction(x).limit_denominator(1000)
        if abs(float(frac) - x) > 1e-9 * max(1.0, abs(x)):
            raise UnitError(
                f"cannot raise {describe_full(self.dim)} to the power {format_number(x)}",
                hint="A quantity with units needs a whole or simple fractional exponent such as 2 or 1/2.",
            )
        return Quantity(_safe_pow(self.value, x), self.dim ** frac)

    def __neg__(self) -> "Quantity":
        if self.unit is not None and self.unit.affine:
            raise UnitError(
                "cannot negate an absolute temperature",
                hint="Write the sign on the number, e.g. -40 degC, or work in K.",
            )
        return Quantity(-self.value, self.dim, self.unit)

    # ---- display -------------------------------------------------------------------------
    def __str__(self) -> str:
        if self.unit is not None:
            text = self.unit.symbol()
            number = format_number(self.magnitude(self.unit))
            return f"{number} {text}" if text else number
        if self.dim.is_dimensionless:
            return format_number(self.value)
        return f"{format_number(self.value)} {Unit.from_dim(self.dim).symbol()}"

    def __repr__(self) -> str:
        return f"Quantity({self})"


def _q(x: Union[Quantity, Number]) -> Quantity:
    return x if isinstance(x, Quantity) else Quantity(x)
