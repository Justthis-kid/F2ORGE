"""Built-in constants (feature 32) and engineering constant packs (feature 33).

All names are available everywhere.  Inside an `eq` a constant is overridden by declaring the
name as a variable ("R : ohm"), so a resistance called R never collides with the gas constant.
"""
from __future__ import annotations

import math
from fractions import Fraction as F
from typing import Dict, List, Tuple

from .quantity import Quantity
from .units import Unit


def _q(value: float, *atoms: Tuple[str, int]) -> Quantity:
    return Quantity.from_unit(value, Unit.from_atoms([(n, F(e)) for n, e in atoms]))


BOOLEANS = {"true": True, "false": False}

CONSTANTS: Dict[str, Quantity] = {
    # mathematics
    "pi": Quantity(math.pi),
    "e": Quantity(math.e),
    # general physics
    "g": _q(9.80665, ("m", 1), ("s", -2)),                       # standard gravity
    "G": _q(6.67430e-11, ("N", 1), ("m", 2), ("kg", -2)),        # Newtonian gravitation
    "R": _q(8.314462618, ("J", 1), ("mol", -1), ("K", -1)),      # molar gas constant
    "speedOfLight": _q(299792458.0, ("m", 1), ("s", -1)),
    "kB": _q(1.380649e-23, ("J", 1), ("K", -1)),                 # Boltzmann
    "NA": _q(6.02214076e23, ("mol", -1)),                        # Avogadro
    "sigmaSB": _q(5.670374419e-8, ("W", 1), ("m", -2), ("K", -4)),
    # aerospace pack
    "muEarth": _q(3.986004418e14, ("m", 3), ("s", -2)),          # Earth gravitational parameter
    "rEarth": _q(6378137.0, ("m", 1)),                           # equatorial radius
    "rhoSL": _q(1.225, ("kg", 1), ("m", -3)),                    # ISA sea-level density
    "pSL": _q(101325.0, ("Pa", 1)),                              # ISA sea-level pressure
    "TSL": _q(288.15, ("K", 1)),                                 # ISA sea-level temperature
}

PACKS: Dict[str, List[str]] = {
    "Mathematics": ["pi", "e"],
    "Physics": ["g", "G", "R", "speedOfLight", "kB", "NA", "sigmaSB"],
    "Aerospace": ["muEarth", "rEarth", "rhoSL", "pSL", "TSL"],
}
