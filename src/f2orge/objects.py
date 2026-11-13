"""User-defined domain objects: `object Car { mass : kg = 1200 kg  energy = mass * v^2 }`.

A custom object is a named bundle of unit-checked properties and formulas, written in F²ORGE
source.  It behaves like the built-in `Rocket`, `Motor`, and `Battery`: `car.mass` reads a value,
`car.energy` evaluates a formula, and `car.range(5 km)` calls one with arguments.

Properties without a default must be supplied when the object is built; properties with a default
may be left out.  Units are checked at construction, so a mass given in metres is refused with the
same message every other unit error uses.
"""
from __future__ import annotations

from typing import Dict, List

from . import syntax as S
from .dimensions import describe_full
from .errors import ForgeError, ForgeNameError, ForgeSyntaxError
from .quantity import Quantity


class UserObjectType:
    """The class behind an `object` declaration: its properties, defaults, and formulas."""

    DOMAIN = "object"

    def __init__(self, definition: S.ObjectDef):
        self.definition = definition
        self.name = definition.name
        self.doc = definition.doc
        self.properties: Dict[str, S.PropertySpec] = {p.name: p for p in definition.properties}
        self.defaults: Dict[str, Quantity] = {}  # filled in by the interpreter, units checked
        self.formulas: Dict[str, S.FormulaSpec] = {f.name: f for f in definition.formulas}
        for formula in definition.formulas:
            for name in S.names_in(formula.body):
                # A formula may use properties, its own parameters, or an earlier formula.
                if name in formula.params or name in self.properties or name in self.formulas:
                    continue
                raise ForgeSyntaxError(
                    f"'{name}' is used in {self.name}.{formula.name} but is neither a property "
                    f"nor a parameter of the formula", formula.span,
                    hint="Declare it as a property, or add it as a parameter: "
                         f"{formula.name}({name}) = ...")

    # ---- construction -----------------------------------------------------------------------
    def build(self, values: Dict[str, Quantity], span=None) -> "UserObject":
        checked: Dict[str, Quantity] = {}
        for name, spec in self.properties.items():
            if name in values:
                value = values[name]
                if not isinstance(value, Quantity):
                    raise ForgeSyntaxError(f"'{name}' of a {self.name} must be a quantity", span)
                if value.dim != spec.unit.dim:
                    raise ForgeError(
                        f"'{name}' of a {self.name} is {describe_full(spec.unit.dim)}, "
                        f"but this is {describe_full(value.dim)}", span, title="Unit mismatch")
                checked[name] = Quantity(value.value, value.dim, value.unit or spec.unit)
            elif name in self.defaults and self.defaults[name] is not None:
                checked[name] = self.defaults[name]
            else:
                raise ForgeError(f"{self.name} needs a value for '{name}'", span,
                                 title="Missing property",
                                 hint=f"It takes: {', '.join(self.properties)}")
        extra = set(values) - set(self.properties)
        if extra:
            close = sorted(extra)[0]
            raise ForgeNameError(f"a {self.name} has no property named '{close}'", span,
                                 hint=f"It takes: {', '.join(self.properties)}")
        return UserObject(self, checked)

    # ---- display ------------------------------------------------------------------------------
    def describe(self) -> List[str]:
        lines = [f"object {self.name}:"]
        if self.doc:
            lines.append(f"  \"{self.doc}\"")
        for spec in self.properties.values():
            known = self.defaults.get(spec.name)
            default = f" = {known}" if known is not None else " (required)"
            unit = spec.unit.symbol() or "dimensionless"
            doc = f"  \"{spec.doc}\"" if spec.doc else ""
            lines.append(f"  {spec.name} : {unit}{default}{doc}")
        for formula in self.formulas.values():
            params = ", ".join(formula.params)
            lines.append(f"  {formula.name}({params}) = ..." if params else f"  {formula.name} = ...")
        return lines

    def __str__(self) -> str:
        return f"object {self.name}"


class UserObject:
    """An instance of a user-defined object: its values plus the formulas over them."""

    def __init__(self, kind: UserObjectType, values: Dict[str, Quantity]):
        self.kind = kind
        self.values = values

    @property
    def DOMAIN(self) -> str:
        return self.kind.name

    def get(self, name: str) -> object:
        if name in self.values:
            return self.values[name]
        formula = self.kind.formulas.get(name)
        if formula is not None:
            return BoundFormula(self, formula)
        raise ForgeNameError(f"a {self.kind.name} has no property or formula named '{name}'",
                             hint="It has: " + ", ".join(list(self.values) + list(self.kind.formulas)))

    def evaluate(self, formula: S.FormulaSpec, args, evaluator, span, kwargs=None):
        """Evaluate a formula's body with the properties and parameters in scope."""
        from .evaluator import Scope

        if kwargs:
            raise ForgeSyntaxError(
                f"{self.kind.name}.{formula.name} takes plain values, not name = value pairs", span)
        if len(args) != len(formula.params):
            raise ForgeSyntaxError(
                f"{self.kind.name}.{formula.name} takes {len(formula.params)} value(s) but got {len(args)}",
                span, hint=f"Write: {self.kind.name}.{formula.name}({', '.join(formula.params)})")
        # Properties first, then the other formulas, then this call's parameters (which win).
        values = dict(self.values)
        for other in self.kind.formulas:
            if other != formula.name:
                values[other] = _Computed(self, other)
        values.update(zip(formula.params, args))
        result = evaluator.eval(formula.body, Scope(values, constants=True))
        if not isinstance(result, Quantity):
            raise ForgeSyntaxError(f"{self.kind.name}.{formula.name} must give a scalar quantity", span)
        if formula.unit is not None:
            # A formula may state its result's unit; a parameter declared `seconds : s` makes
            # `v * seconds` a length, and the annotation says which length it must be.
            if result.dim != formula.unit.dim:
                raise ForgeError(
                    f"{self.kind.name}.{formula.name} should give "
                    f"{describe_full(formula.unit.dim)}, but it gives {describe_full(result.dim)}",
                    span, title="Unit mismatch")
            result = Quantity(result.value, result.dim, formula.unit)
        return result

    def describe(self) -> List[str]:
        lines = [f"{self.kind.name} ({self.kind.doc})" if self.kind.doc else self.kind.name]
        lines += [f"  {name} = {value}" for name, value in self.values.items()]
        return lines

    def __str__(self) -> str:
        body = ", ".join(f"{name} = {value}" for name, value in self.values.items())
        return f"{self.kind.name}({body})"

    __repr__ = __str__


class _Computed:
    """One formula seen from inside another formula, evaluated on demand (`range` uses `energy`)."""

    __slots__ = ("owner", "name")

    def __init__(self, owner: "UserObject", name: str):
        self.owner = owner
        self.name = name

    def resolve(self, evaluator) -> Quantity:
        formula = self.owner.kind.formulas[self.name]
        if formula.params:
            raise ForgeNameError(
                f"{self.owner.kind.name}.{self.name} needs {len(formula.params)} value(s); call it"
                f" instead", formula.span)
        return self.owner.evaluate(formula, (), evaluator, formula.span)

    def __str__(self) -> str:
        return f"{self.owner.kind.name}.{self.name}"


class BoundFormula:
    """`car.energy` or `car.range`: callable when it has parameters, a value when it does not."""

    __slots__ = ("owner", "formula", "evaluator")

    def __init__(self, owner: UserObject, formula: S.FormulaSpec):
        self.owner = owner
        self.formula = formula

    def value(self, evaluator):
        return self.owner.evaluate(self.formula, (), evaluator, self.formula.span)

    def __call__(self, *args, evaluator=None):
        if evaluator is None:
            raise ForgeNameError(f"{self.owner.kind.name}.{self.formula.name} needs a running interpreter")
        return self.owner.evaluate(self.formula, list(args), evaluator, self.formula.span)

    def __str__(self) -> str:
        return f"{self.owner.kind.name}.{self.formula.name}"
