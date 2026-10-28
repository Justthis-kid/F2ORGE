"""Physical dimensions: exponents of the seven SI base quantities.

A dimension is a vector of exponents (length, mass, time, current, temperature, amount,
luminous intensity).  Multiplying quantities adds exponents, dividing subtracts them, powers
scale them.  Using exact fractions means sqrt(m^2) really is m and m^(1/2) round-trips.

    kg*m/s^2  ->  (1, 1, -2, 0, 0, 0, 0)  ->  named derived unit "N"

This single mechanism is what powers unit conversion, unit-safety checking and the automatic
simplification of results to named units.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Dict, Iterable, List, Tuple

SUPERSCRIPTS = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")
BASE_SYMBOLS = ("m", "kg", "s", "A", "K", "mol", "cd")  # index order of Dim.exps
DISPLAY_ORDER = (1, 0, 2, 3, 4, 5, 6)  # print kg before m, as in kg*m/s^2
DISPLAY_NAMES = {"ohm": "Ω", "degC": "°C", "degF": "°F"}


@dataclass(frozen=True)
class Dim:
    exps: Tuple[Fraction, ...]

    @staticmethod
    def of(L=0, M=0, T=0, I=0, Th=0, N=0, J=0) -> "Dim":
        return Dim(tuple(Fraction(x) for x in (L, M, T, I, Th, N, J)))

    def __mul__(self, other: "Dim") -> "Dim":
        return Dim(tuple(a + b for a, b in zip(self.exps, other.exps)))

    def __truediv__(self, other: "Dim") -> "Dim":
        return Dim(tuple(a - b for a, b in zip(self.exps, other.exps)))

    def __pow__(self, power) -> "Dim":
        p = Fraction(power)
        return Dim(tuple(a * p for a in self.exps))

    @property
    def is_dimensionless(self) -> bool:
        return not any(self.exps)


DIMLESS = Dim.of()

# Named derived units: the dimension -> symbol used when a result is simplified.
# Hz is left out on purpose: a bare 1/s is usually a rate, and "10 Hz" would surprise people.
DERIVED: Dict[Dim, str] = {
    Dim.of(L=1, M=1, T=-2): "N",
    Dim.of(L=2, M=1, T=-2): "J",
    Dim.of(L=2, M=1, T=-3): "W",
    Dim.of(L=-1, M=1, T=-2): "Pa",
    Dim.of(T=1, I=1): "C",
    Dim.of(L=2, M=1, T=-3, I=-1): "V",
    Dim.of(L=2, M=1, T=-3, I=-2): "ohm",
    Dim.of(L=-2, M=-1, T=4, I=2): "F",
    Dim.of(L=2, M=1, T=-2, I=-2): "H",
    Dim.of(L=-2, M=-1, T=3, I=2): "S",
    Dim.of(L=2, M=1, T=-2, I=-1): "Wb",
    Dim.of(M=1, T=-2, I=-1): "T",
}

# Human names used in error messages ("expected acceleration, found mass").
NAMES: Dict[Dim, str] = {
    DIMLESS: "a plain number",
    Dim.of(L=1): "length",
    Dim.of(M=1): "mass",
    Dim.of(T=1): "time",
    Dim.of(I=1): "electric current",
    Dim.of(Th=1): "temperature",
    Dim.of(N=1): "amount of substance",
    Dim.of(J=1): "luminous intensity",
    Dim.of(L=2): "area",
    Dim.of(L=3): "volume",
    Dim.of(L=1, T=-1): "velocity",
    Dim.of(L=1, T=-2): "acceleration",
    Dim.of(L=1, M=1, T=-2): "force",
    Dim.of(L=-1, M=1, T=-2): "pressure",
    Dim.of(L=2, M=1, T=-2): "energy (or torque)",
    Dim.of(L=2, M=1, T=-3): "power",
    Dim.of(T=-1): "frequency (1/time)",
    Dim.of(L=-3, M=1): "density",
    Dim.of(L=1, M=1, T=-1): "momentum",
    Dim.of(L=2, M=1, T=-1): "angular momentum",
    Dim.of(T=1, I=1): "electric charge",
    Dim.of(L=2, M=1, T=-3, I=-1): "voltage",
    Dim.of(L=2, M=1, T=-3, I=-2): "resistance",
    Dim.of(L=-2, M=-1, T=4, I=2): "capacitance",
    Dim.of(L=2, M=1, T=-2, I=-2): "inductance",
    Dim.of(L=-2, M=-1, T=3, I=2): "conductance",
    Dim.of(L=2, M=1, T=-2, I=-1): "magnetic flux",
    Dim.of(M=1, T=-2, I=-1): "magnetic flux density",
    Dim.of(L=-1, M=1, T=-1): "dynamic viscosity",
    Dim.of(L=2, T=-1): "kinematic viscosity",
    Dim.of(M=1, T=-1): "mass flow rate",
    Dim.of(L=3, T=-1): "volumetric flow rate",
    Dim.of(L=2, T=-2): "specific energy",
    Dim.of(L=3, T=-2): "gravitational parameter",
    Dim.of(L=2, T=-2, Th=-1): "specific heat capacity",
    Dim.of(L=2, M=1, T=-2, Th=-1): "heat capacity",
    Dim.of(L=1, M=1, T=-3, Th=-1): "thermal conductivity",
    Dim.of(M=1, T=-2): "force per length",
    Dim.of(M=1, L=-2): "mass per area",
}


def _exp_text(e: Fraction, ascii_only: bool) -> str:
    """Exponent suffix for |e| (the sign is carried by numerator/denominator placement)."""
    if e == 1:
        return ""
    if e.denominator == 1:
        digits = str(e.numerator)
        return "^" + digits if ascii_only or e.numerator > 9 else digits.translate(SUPERSCRIPTS)
    return f"^({e.numerator}/{e.denominator})"


def compose(parts: Iterable[Tuple[str, Fraction]], ascii_only: bool = False) -> str:
    """Render [(symbol, exponent), ...] as e.g. 'kg*m/s²' or 'm/(s*K)'."""
    num: List[str] = []
    den: List[str] = []
    for symbol, e in parts:
        e = Fraction(e)
        if e == 0:
            continue
        shown = symbol if ascii_only else DISPLAY_NAMES.get(symbol, symbol)
        (num if e > 0 else den).append(shown + _exp_text(abs(e), ascii_only))
    top = "*".join(num) if num else "1"
    if not den:
        return top
    return f"{top}/{den[0]}" if len(den) == 1 else f"{top}/({'*'.join(den)})"


def si_atoms(dim: Dim) -> List[Tuple[str, Fraction]]:
    """The coherent SI unit for a dimension, as unit atoms: a named unit (N) or base units."""
    if dim in DERIVED:
        return [(DERIVED[dim], Fraction(1))]
    return [(BASE_SYMBOLS[i], dim.exps[i]) for i in DISPLAY_ORDER if dim.exps[i] != 0]


def si_symbol(dim: Dim, ascii_only: bool = False) -> str:
    return compose(si_atoms(dim), ascii_only)


def describe(dim: Dim) -> str:
    """'acceleration', 'mass', ... or the SI unit text when the dimension has no common name."""
    return NAMES.get(dim) or f"a quantity measured in {si_symbol(dim)}"


def describe_full(dim: Dim) -> str:
    """'acceleration (m/s²)' — the kind of quantity plus its SI unit."""
    if dim.is_dimensionless:
        return NAMES[DIMLESS]
    name = NAMES.get(dim)
    return f"{name} ({si_symbol(dim)})" if name else f"a quantity measured in {si_symbol(dim)}"
