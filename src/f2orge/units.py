"""The unit registry: every built-in unit as (dimension, scale to SI, optional offset).

A unit converts to coherent SI like so:   value_SI = value * scale + offset
Only temperature scales (degC, degF) have an offset.  An affine unit is allowed on its own
("25 degC") but inside a compound unit ("W/(m*degC)") it means a temperature *difference*,
so only its scale is used.

SI prefixes are applied to units flagged `prefix`: km, mm, MPa, kN, uF ...  Exact table names
win over prefix splitting, so "min" is the minute and never "milli-inch".

Angles (`rad`, `deg`, `rev`) carry their own dimension, so `rad/s` is an angular velocity while
`1/s` is a frequency, and multiplying or dividing by an angle preserves it.  `sin`, `cos`, `tan`
accept angles (converted to radians) or plain numbers (radians).
"""
from __future__ import annotations

import difflib
import math
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

from .dimensions import DIMLESS, Dim, compose, si_atoms

ASCII_ONLY = False  # set by the CLI (--ascii) for terminals that cannot print superscripts


def set_ascii(flag: bool) -> None:
    global ASCII_ONLY
    ASCII_ONLY = flag


@dataclass(frozen=True)
class UnitDef:
    name: str
    dim: Dim
    scale: float
    offset: float = 0.0
    prefix: bool = False
    kind: str = ""


_BASE: Dict[str, UnitDef] = {}
_ALIAS: Dict[str, str] = {}

PREFIXES = {
    "T": 1e12, "G": 1e9, "M": 1e6, "k": 1e3, "c": 1e-2, "m": 1e-3,
    "u": 1e-6, "µ": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15,
}


def _add(name: str, dim: Dim, scale: float = 1.0, *, prefix: bool = False, offset: float = 0.0,
         aliases: Sequence[str] = (), kind: str = "") -> None:
    _BASE[name] = UnitDef(name, dim, scale, offset, prefix, kind)
    for alias in aliases:
        _ALIAS[alias] = name


def _build() -> None:
    LEN, MASS, TIME = Dim.of(L=1), Dim.of(M=1), Dim.of(T=1)
    # length
    _add("m", LEN, prefix=True, kind="length")
    _add("in", LEN, 0.0254, kind="length", aliases=("inch",))
    _add("ft", LEN, 0.3048, kind="length", aliases=("foot", "feet"))
    _add("yd", LEN, 0.9144, kind="length")
    _add("mi", LEN, 1609.344, kind="length")
    _add("nmi", LEN, 1852.0, kind="length")
    # mass (g is prefixable, so kg = k + g = 1000 * 1e-3 = 1 kg exactly)
    _add("g", MASS, 1e-3, prefix=True, kind="mass")
    _add("lb", MASS, 0.45359237, kind="mass", aliases=("lbm", "lbs"))
    _add("oz", MASS, 0.028349523125, kind="mass")
    _add("slug", MASS, 14.5939029372, kind="mass")
    _add("t", MASS, 1000.0, kind="mass", aliases=("tonne",))
    # time
    _add("s", TIME, prefix=True, kind="time", aliases=("sec",))
    _add("min", TIME, 60.0, kind="time")
    _add("h", TIME, 3600.0, kind="time", aliases=("hr",))
    _add("day", TIME, 86400.0, kind="time")
    _add("Hz", Dim.of(T=-1), prefix=True, kind="frequency")
    # force
    _add("N", Dim.of(L=1, M=1, T=-2), prefix=True, kind="force")
    _add("lbf", Dim.of(L=1, M=1, T=-2), 4.4482216152605, kind="force")
    _add("kgf", Dim.of(L=1, M=1, T=-2), 9.80665, kind="force")
    _add("dyn", Dim.of(L=1, M=1, T=-2), 1e-5, kind="force")
    # energy and power
    ENERGY = Dim.of(L=2, M=1, T=-2)
    _add("J", ENERGY, prefix=True, kind="energy")
    _add("cal", ENERGY, 4.184, prefix=True, kind="energy")
    _add("BTU", ENERGY, 1055.05585262, kind="energy", aliases=("Btu",))
    _add("Wh", ENERGY, 3600.0, prefix=True, kind="energy")
    _add("eV", ENERGY, 1.602176634e-19, prefix=True, kind="energy")
    _add("ftlbf", ENERGY, 1.3558179483314004, kind="energy")
    _add("W", Dim.of(L=2, M=1, T=-3), prefix=True, kind="power")
    _add("hp", Dim.of(L=2, M=1, T=-3), 745.6998715822702, kind="power")
    # pressure
    PRESSURE = Dim.of(L=-1, M=1, T=-2)
    _add("Pa", PRESSURE, prefix=True, kind="pressure")
    _add("bar", PRESSURE, 1e5, prefix=True, kind="pressure")
    _add("atm", PRESSURE, 101325.0, kind="pressure")
    _add("psi", PRESSURE, 6894.757293168361, kind="pressure")
    _add("ksi", PRESSURE, 6894757.293168361, kind="pressure")
    _add("torr", PRESSURE, 133.32236842105263, kind="pressure")
    _add("mmHg", PRESSURE, 133.322387415, kind="pressure")
    _add("inHg", PRESSURE, 3386.389, kind="pressure")
    # temperature: K is absolute; degC / degF carry an offset; degR is the absolute Rankine scale
    TEMP = Dim.of(Th=1)
    _add("K", TEMP, prefix=True, kind="temperature")
    _add("degC", TEMP, 1.0, offset=273.15, kind="temperature", aliases=("°C", "celsius"))
    _add("degF", TEMP, 5.0 / 9.0, offset=459.67 * 5.0 / 9.0, kind="temperature", aliases=("°F",))
    _add("degR", TEMP, 5.0 / 9.0, kind="temperature")
    # electrical
    _add("A", Dim.of(I=1), prefix=True, kind="electrical")
    _add("V", Dim.of(L=2, M=1, T=-3, I=-1), prefix=True, kind="electrical")
    _add("ohm", Dim.of(L=2, M=1, T=-3, I=-2), prefix=True, kind="electrical", aliases=("Ω", "Ohm"))
    _add("F", Dim.of(L=-2, M=-1, T=4, I=2), prefix=True, kind="electrical")
    _add("H", Dim.of(L=2, M=1, T=-2, I=-2), prefix=True, kind="electrical")
    _add("C", Dim.of(T=1, I=1), prefix=True, kind="electrical")
    _add("S", Dim.of(L=-2, M=-1, T=3, I=2), prefix=True, kind="electrical")
    _add("Wb", Dim.of(L=2, M=1, T=-2, I=-1), prefix=True, kind="electrical")
    _add("T", Dim.of(M=1, T=-2, I=-1), prefix=True, kind="electrical")
    _add("mol", Dim.of(N=1), prefix=True, kind="amount")
    # Battery capacity is charge: 1 Ah is 3600 coulombs.
    _add("Ah", Dim.of(T=1, I=1), 3600.0, prefix=True, kind="electrical")
    # volume, speed, angle
    _add("L", Dim.of(L=3), 1e-3, prefix=True, kind="volume", aliases=("l",))
    _add("gal", Dim.of(L=3), 0.003785411784, kind="volume")
    _add("qt", Dim.of(L=3), 0.000946352946, kind="volume")
    _add("mph", Dim.of(L=1, T=-1), 0.44704, kind="speed")
    _add("kph", Dim.of(L=1, T=-1), 1000.0 / 3600.0, kind="speed")
    _add("kn", Dim.of(L=1, T=-1), 1852.0 / 3600.0, kind="speed", aliases=("knot",))
    angle = Dim.of(Angle=1)
    _add("rad", angle, 1.0, prefix=True, kind="angle")
    _add("deg", angle, math.pi / 180.0, kind="angle", aliases=("°",))
    _add("rev", angle, 2 * math.pi, kind="angle")
    _add("grad", angle, math.pi / 200.0, kind="angle", aliases=("gon",), prefix=True)
    _add("arcmin", angle, math.pi / 10800.0, kind="angle")
    _add("arcsec", angle, math.pi / 648000.0, kind="angle")
    # rpm is revolutions per minute: an angular velocity, so it converts to rad/s (60 rpm = 2*pi
    # rad/s) and never to a frequency like 1/s or Hz.
    _add("rps", Dim.of(Angle=1, T=-1), 2 * math.pi, kind="angular velocity")
    _add("rpm", Dim.of(Angle=1, T=-1), 2 * math.pi / 60, kind="angular velocity")
    _add("dB", Dim.of(Log=1), kind="logarithmic level")
    _add("dBm", Dim.of(Log=1), kind="logarithmic level")  # level above 1 mW
    _add("Np", Dim.of(Log=1), math.log(10.0) / 2.0, kind="logarithmic level")  # 1 Np = 8.686 dB
    _add("%", DIMLESS, 0.01, kind="ratio", aliases=("percent", "pct"))
    _add("ppm", DIMLESS, 1e-6, kind="ratio")
    for currency in ("USD", "EUR", "GBP", "JPY", "CAD", "AUD"):
        _add(currency, Dim.of(**{currency: 1}), kind="currency")


_build()


class UnknownUnit(ValueError):
    def __init__(self, name: str, suggestions: Sequence[str] = ()):
        super().__init__(name)
        self.name = name
        self.suggestions = list(suggestions)


@lru_cache(maxsize=None)
def lookup_unit(name: str) -> Optional[UnitDef]:
    """Find a unit by exact name, alias, or SI-prefix + prefixable base unit."""
    if name in _BASE:
        return _BASE[name]
    if name in _ALIAS:
        return _BASE[_ALIAS[name]]
    if len(name) >= 2 and name[0] in PREFIXES:
        rest = _ALIAS.get(name[1:], name[1:])
        base = _BASE.get(rest)
        if base is not None and base.prefix:
            return UnitDef(name, base.dim, base.scale * PREFIXES[name[0]], 0.0, False, base.kind)
    return None


def unit_named(name: str) -> Optional["Unit"]:
    """The writable Unit for a unit name (with its atoms), or None when it is not a unit."""
    if lookup_unit(name) is None:
        return None
    return Unit.from_atoms([(name, Fraction(1))])


def all_unit_names() -> List[str]:
    return sorted(set(_BASE) | set(_ALIAS))


def suggest_units(name: str) -> List[str]:
    return difflib.get_close_matches(name, all_unit_names(), n=3, cutoff=0.6)


def units_by_kind() -> Dict[str, List[UnitDef]]:
    groups: Dict[str, List[UnitDef]] = {}
    for u in _BASE.values():
        groups.setdefault(u.kind, []).append(u)
    return groups


def _display_name(name: str) -> str:
    """Show a typed 'um' / 'uF' as 'µm' / 'µF'."""
    if len(name) >= 2 and name[0] == "u" and name not in _BASE and name not in _ALIAS:
        return "µ" + name[1:]
    return name


@dataclass(frozen=True)
class Unit:
    """A concrete unit: dimension + conversion to SI + the atoms it was written with."""

    dim: Dim
    scale: float
    offset: float = 0.0
    atoms: Tuple[Tuple[str, Fraction], ...] = ()

    @property
    def affine(self) -> bool:
        return self.offset != 0.0

    @staticmethod
    def from_atoms(atoms: Sequence[Tuple[str, Fraction]]) -> "Unit":
        """Combine (name, exponent) atoms.  Raises UnknownUnit for a name that is not registered."""
        merged: Dict[str, Fraction] = {}
        for name, exp in atoms:
            merged[name] = merged.get(name, Fraction(0)) + Fraction(exp)
        clean = tuple((n, e) for n, e in merged.items() if e != 0)
        dim = DIMLESS
        scale = 1.0
        offset = 0.0
        for name, exp in clean:
            u = lookup_unit(name)
            if u is None:
                raise UnknownUnit(name, suggest_units(name))
            dim = dim * (u.dim ** exp)
            scale *= u.scale ** float(exp)
        if len(clean) == 1 and clean[0][1] == 1:
            offset = lookup_unit(clean[0][0]).offset
        return Unit(dim, scale, offset, clean)

    @staticmethod
    def from_dim(dim: Dim) -> "Unit":
        """Coherent SI unit for a dimension: N for force, m/s² for acceleration, ..."""
        return Unit.from_atoms(si_atoms(dim))

    def symbol(self, ascii_only: Optional[bool] = None) -> str:
        use_ascii = ASCII_ONLY if ascii_only is None else ascii_only
        if not self.atoms:
            return ""  # dimensionless: nothing to print after the number
        parts = [(n if use_ascii else _display_name(n), e) for n, e in self.atoms]
        return compose(parts, use_ascii)


KELVIN = Unit.from_atoms([("K", Fraction(1))])
