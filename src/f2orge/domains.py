"""Engineering domain objects: a rocket, a motor, and a battery you can calculate with.

Each object is a bundle of named quantities plus the formulas that apply to it, so a student can
write `rocket.mass` and `rocket.deltaV(...)` instead of rebuilding the physics every time.  The
objects keep F²ORGE's unit safety: every property is a Quantity, so adding a mass to a thrust fails
in exactly the same way it does everywhere else.

    r = Rocket(dryMass = 1200 kg, propellantMass = 2800 kg, isp = 311 s)
    r.deltaV                        # 3497.4 m/s, Tsiolkovsky's equation
    r.burnTime(engine.thrust)       # how long the propellant lasts
    r.gravityLoss(60 s, 9.81 m/s^2)

    m = Motor(torque = 2.5 N*m, speed = 3000 rpm)
    m.power                         # 785.4 W
    m.torqueAt(1500 rpm)            # half speed, same mechanical power limit

    b = Battery(capacity = 5 Ah, voltage = 11.1 V)
    b.energy                        # 199.8 kJ
    b.range(0.15 kWh/km)            # how far it goes
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional

from .errors import ForgeError, ForgeNameError, ForgeSyntaxError, Span
from .quantity import Quantity
from .units import Unit
from . import syntax as S

_G = 9.80665  # standard gravity, m/s²


def _unit(*atoms) -> Unit:
    from fractions import Fraction

    return Unit.from_atoms([(name, Fraction(power)) for name, power in atoms])


_SECOND = _unit(("s", 1))
_NEWTON = _unit(("N", 1))
_WATT = _unit(("W", 1))
_JOULE = _unit(("J", 1))
_METRE = _unit(("m", 1))
_RADIAN_PER_SECOND = _unit(("rad", 1), ("s", -1))

# Quantity takes a dimension, so formulas hand it `.dim` of the unit they mean.
_S, _N, _W, _J, _M = _SECOND.dim, _NEWTON.dim, _WATT.dim, _JOULE.dim, _METRE.dim
_NM = _N * _M
_KG_PER_S = _unit(("kg", 1), ("s", -1)).dim
_M_PER_S = _unit(("m", 1), ("s", -1)).dim
_M_PER_S2 = _unit(("m", 1), ("s", -2)).dim
_NM_PER_A = _unit(("N", 1), ("m", 1), ("A", -1)).dim
_VOLT = _unit(("V", 1)).dim


class DomainObject:
    """A named bundle of quantities with formulas over them.

    Subclasses list their properties in `PROPERTIES` (name -> unit) and their formulas in
    `FORMULAS` (name -> callable taking the object).  Both are read with `.`, so `rocket.mass` and
    `rocket.deltaV` look the same to the caller.
    """

    PROPERTIES: Dict[str, Unit] = {}
    FORMULAS: Dict[str, Callable] = {}
    DOMAIN = "object"

    def __init__(self, **values):
        self.values: Dict[str, Quantity] = {}
        for name, unit in self.PROPERTIES.items():
            if name not in values:
                raise ForgeError(f"{self.DOMAIN} needs a value for '{name}'", title="Missing property",
                                 hint=f"It takes: {', '.join(self.PROPERTIES)}")
            value = values[name]
            if not isinstance(value, Quantity):
                raise ForgeSyntaxError(f"'{name}' must be a quantity such as 5 {unit.symbol()}",
                                       hint=f"{name} is measured in {unit.symbol()}.")
            if value.is_plain and not unit.dim.is_dimensionless:
                value = Quantity(value.value, unit.dim, unit)
            elif value.dim != unit.dim:
                from .dimensions import describe_full

                raise ForgeError(
                    f"'{name}' of a {self.DOMAIN} is {describe_full(unit.dim)}, "
                    f"but this is {describe_full(value.dim)}", title="Unit mismatch")
            self.values[name] = Quantity(value.value, value.dim, value.unit or unit)
        extra = set(values) - set(self.PROPERTIES)
        if extra:
            raise ForgeNameError(
                f"a {self.DOMAIN} has no property named '{sorted(extra)[0]}'",
                hint=f"It takes: {', '.join(self.PROPERTIES)}")

    # ---- reading ------------------------------------------------------------------------------
    def get(self, name: str) -> object:
        if name in self.values:
            return self.values[name]
        if name in self.FORMULAS:
            return _BoundFormula(self, name, self.FORMULAS[name])
        # A computed value such as `rocket.deltaV` is a property of the class.
        computed = getattr(type(self), name, None)
        if isinstance(computed, property):
            return computed.__get__(self, type(self))
        raise ForgeNameError(f"a {self.DOMAIN} has no property or formula named '{name}'",
                             hint="It has: " + ", ".join(self.names()))

    def names(self) -> List[str]:
        """Every property and formula a reader can ask for, in a stable order."""
        computed = [name for name, value in vars(type(self)).items()
                    if isinstance(value, property) and not name.startswith("_")]
        return list(self.values) + computed + list(self.FORMULAS)

    def describe(self) -> List[str]:
        lines = [f"{type(self).__name__}:"]
        lines += [f"  {name} = {value}" for name, value in self.values.items()]
        lines += [f"  {name}(...)  a formula" for name in self.FORMULAS]
        return lines

    def __str__(self) -> str:
        return f"{type(self).__name__}({', '.join(f'{k} = {v}' for k, v in self.values.items())})"

    __repr__ = __str__


class _BoundFormula:
    """`rocket.deltaV` as a value: callable, and printed with its name."""

    __slots__ = ("owner", "name", "function")

    def __init__(self, owner: DomainObject, name: str, function):
        self.owner = owner
        self.name = name
        self.function = function

    def __call__(self, *args, **kwargs):
        return self.function(self.owner, *args, **kwargs)

    def __str__(self) -> str:
        return f"{type(self.owner).__name__}.{self.name}(...)"

    def __repr__(self) -> str:
        return str(self)


# ---- rocket -----------------------------------------------------------------------------------
class Rocket(DomainObject):
    """A rocket's mass budget; Tsiolkovsky's equation and the losses that follow from it."""

    DOMAIN = "rocket"
    PROPERTIES = {
        "dryMass": _unit(("kg", 1)),
        "propellantMass": _unit(("kg", 1)),
        "isp": _SECOND,
    }
    FORMULAS = {}

    @property
    def wetMass(self) -> Quantity:
        """The mass at ignition: dry mass plus propellant."""
        return self.values["dryMass"] + self.values["propellantMass"]

    @property
    def massRatio(self) -> Quantity:
        """Wet over dry mass: the number Tsiolkovsky's equation takes a logarithm of."""
        return Quantity(self.wetMass.value / self.values["dryMass"].value)

    @property
    def exhaustVelocity(self) -> Quantity:
        """Effective exhaust velocity, Isp times standard gravity."""
        return Quantity(self.values["isp"].value * _G, _M_PER_S)

    @property
    def deltaV(self) -> Quantity:
        """The velocity change the propellant can produce, with no losses (Tsiolkovsky)."""
        return Quantity(self.exhaustVelocity.value * math.log(self.massRatio.value),
                        self.exhaustVelocity.dim)

    def burnTime(self, thrust) -> Quantity:
        """How long the propellant lasts at a given thrust."""
        mass_flow = Quantity(thrust.value / self.exhaustVelocity.value, _KG_PER_S)
        return Quantity(self.values["propellantMass"].value / mass_flow.value, _S)

    def acceleration(self, thrust) -> Quantity:
        """Acceleration at ignition: thrust over the wet mass."""
        return Quantity(thrust.value / self.wetMass.value, _M_PER_S2)

    def gravityLoss(self, burn_time, gravity_rate=None) -> Quantity:
        """The velocity spent holding a rocket up: g times the burn time."""
        g = gravity_rate if isinstance(gravity_rate, Quantity) else Quantity(_G, _M_PER_S2)
        return g * burn_time

    def payloadFraction(self, payload) -> Quantity:
        """The share of the lift-off mass that is payload."""
        return Quantity(payload.value / self.wetMass.value)


Rocket.FORMULAS = {
    "burnTime": Rocket.burnTime,
    "acceleration": Rocket.acceleration,
    "gravityLoss": Rocket.gravityLoss,
    "payloadFraction": Rocket.payloadFraction,
}


# ---- motor ------------------------------------------------------------------------------------
class Motor(DomainObject):
    """A rotating machine: torque, speed, power, and efficiency."""

    DOMAIN = "motor"
    PROPERTIES = {
        "torque": _unit(("N", 1), ("m", 1)),
        "speed": _unit(("rad", 1), ("s", -1)),
    }
    FORMULAS = {}

    @property
    def power(self) -> Quantity:
        """Mechanical power: torque times angular speed."""
        return Quantity(self.values["torque"].value * self.values["speed"].value, _W)

    def torqueAt(self, speed) -> Quantity:
        """Torque at another speed, holding the mechanical power constant."""
        return Quantity(self.power.value / speed.value, _NM, _unit(("N", 1), ("m", 1)))

    def torquePerAmp(self, current) -> Quantity:
        """The torque constant: torque divided by an armature current."""
        return Quantity(self.values["torque"].value / current.value, _NM_PER_A)

    def efficiency(self, electrical_power) -> Quantity:
        """Mechanical power out over electrical power in."""
        return Quantity(self.power.value / electrical_power.value)


Motor.FORMULAS = {"torqueAt": Motor.torqueAt, "torquePerAmp": Motor.torquePerAmp,
                  "efficiency": Motor.efficiency}


# ---- battery ----------------------------------------------------------------------------------
class Battery(DomainObject):
    """A battery's energy budget: capacity, voltage, energy, and how far it goes."""

    DOMAIN = "battery"
    PROPERTIES = {
        "capacity": _unit(("A", 1), ("s", 1)),
        "voltage": _unit(("V", 1)),
    }
    FORMULAS = {}

    @property
    def charge(self) -> Quantity:
        """Capacity in coulombs: amp-hours times 3600."""
        return self.values["capacity"]

    @property
    def energy(self) -> Quantity:
        """Stored energy: voltage times charge."""
        return Quantity(self.values["voltage"].value * self.charge.value, _J)

    def runtime(self, load) -> Quantity:
        """How long the battery lasts at a given current."""
        if load.value == 0:
            raise ForgeError("a zero load runs forever", title="Cannot calculate")
        return Quantity(self.values["capacity"].value / load.value, _S)

    def range(self, consumption) -> Quantity:
        """How far a vehicle goes, given energy used per metre."""
        return Quantity(self.energy.value / consumption.value, _M)

    def energyDensity(self) -> Quantity:
        """Energy per unit of capacity, a rough quality figure: joules per coulomb."""
        return Quantity(self.energy.value / self.charge.value, _VOLT)


Battery.FORMULAS = {"runtime": Battery.runtime, "range": Battery.range,
                    "energyDensity": Battery.energyDensity}

DOMAINS: Dict[str, type] = {"Rocket": Rocket, "Motor": Motor, "Battery": Battery}
