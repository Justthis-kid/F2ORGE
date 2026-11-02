"""Equations as first-class objects (features 8, 11, 12, 13).

An Equation is a set of relations `lhs = rhs` plus metadata and optional unit declarations.

    eq Force {
        description = "Newton's second law"      # metadata
        m : kg "mass"                            # declaration: expected unit (+ documentation)
        F = m * a                                # relation
    }

* Outputs are the names defined by `name = ...` relations; inputs are every other variable
  (feature 11: nothing is declared by hand).
* Calling an equation evaluates the relations in dependency order.
* Declarations are optional.  With them, arguments are unit-checked and errors read
  "expected acceleration (m/s²), found mass (kg)"; without them units are still checked
  inside the formula itself.
"""
from __future__ import annotations

import difflib
from typing import Dict, List, Optional, Tuple

from . import syntax as S
from .constants import CONSTANTS
from .dimensions import Dim, describe_full
from .errors import ForgeError, ForgeSyntaxError, Source, Span, UnitError, ForgeEvalError
from .evaluator import Evaluator, Scope, UndefinedVariable
from .quantity import Quantity

# two probe assignments for static dimension checking; the second is a fallback for
# formulas whose domain rejects the first (asin, sqrt of a difference, ...)
_PROBES = (lambda i: 0.7 + 0.1 * i, lambda i: 1.9 + 0.3 * (7 - i))


class Equation:
    def __init__(self, definition: S.EqDef, source: Source):
        self.name = definition.name
        self.source = source
        self.span = definition.span
        self.name_span = definition.name_span
        self.metadata: Dict[str, str] = {}
        self.decls: Dict[str, S.Decl] = {}
        self.relations: List[S.Relation] = []
        for item in definition.items:
            if isinstance(item, S.Meta):
                self.metadata[item.key] = item.value
            elif isinstance(item, S.Decl):
                if item.name in self.decls:
                    raise ForgeSyntaxError(f"'{item.name}' is declared twice", item.span)
                self.decls[item.name] = item
            else:
                self.relations.append(item)
        if not self.relations:
            raise ForgeSyntaxError(f"The equation '{self.name}' has no formula", self.name_span,
                                   hint="Add a line such as:  F = m * a")
        self.inferred: Dict[str, Dim] = {}
        self._analyse()

    # ---- structure -------------------------------------------------------------------------
    def _analyse(self) -> None:
        defined: Dict[str, S.Relation] = {}
        for rel in self.relations:
            if isinstance(rel.lhs, S.Name):
                if rel.lhs.name in defined:
                    raise ForgeSyntaxError(f"'{rel.lhs.name}' is defined twice in {self.name}", rel.span,
                                           hint="Each output can be defined by one formula only.")
                defined[rel.lhs.name] = rel
        self.outputs: List[str] = list(defined)
        self.implicit: List[S.Relation] = [r for r in self.relations if not isinstance(r.lhs, S.Name)]
        self.callable = not self.implicit

        def is_variable(name: str) -> bool:
            return name in defined or name in self.decls or name not in CONSTANTS

        self.rel_vars: List[List[str]] = []
        self.variables: List[str] = []
        for rel in self.relations:
            names = [n for n in S.names_in(rel.lhs) + S.names_in(rel.rhs) if is_variable(n)]
            unique: List[str] = []
            for n in names:
                if n not in unique:
                    unique.append(n)
            self.rel_vars.append(unique)
            for n in unique:
                if n not in self.variables:
                    self.variables.append(n)
        self.inputs: List[str] = [v for v in self.variables if v not in defined]

        for name, decl in self.decls.items():
            if name not in self.variables:
                raise ForgeSyntaxError(
                    f"'{name}' is declared but never used in {self.name}", decl.span,
                    hint=f"Variables used here: {', '.join(self.variables)}")

        # evaluation order for definitional relations (dependencies first)
        deps = {n: [v for v in S.names_in(r.rhs) if v in defined] for n, r in defined.items()}
        order: List[S.Relation] = []
        state: Dict[str, int] = {}

        def visit(name: str, trail: List[str]) -> None:
            if state.get(name) == 2:
                return
            if state.get(name) == 1:
                cycle = " -> ".join(trail[trail.index(name):] + [name])
                raise ForgeSyntaxError(
                    f"The formulas of {self.name} depend on each other in a loop ({cycle})", defined[name].span,
                    hint="Simultaneous equations are not supported yet; use solve with one equation at a time.")
            state[name] = 1
            for d in deps[name]:
                visit(d, trail + [name])
            state[name] = 2
            order.append(defined[name])

        for name in defined:
            visit(name, [])
        self.order = order

        used_by_others = {v for r in self.relations for v in S.names_in(r.rhs)}
        sinks = [r.lhs.name for r in self.relations if isinstance(r.lhs, S.Name) and r.lhs.name not in used_by_others]
        if sinks:
            self.primary: Optional[str] = sinks[-1]
        else:
            self.primary = self.outputs[-1] if self.outputs else None

    def relation_for(self, output: str) -> Optional[S.Relation]:
        for rel in self.relations:
            if isinstance(rel.lhs, S.Name) and rel.lhs.name == output:
                return rel
        return None

    # ---- static dimension check (feature 4) --------------------------------------------------
    def validate(self, evaluator: Evaluator) -> None:
        """Check the formulas' dimensions at definition time, using declared units where present.

        Raises UnitError for a real inconsistency.  Parts that cannot be decided (an input with no
        declared unit) are skipped; they are still checked when the equation is called.
        """
        for probe in _PROBES:
            try:
                self._validate_once(evaluator, probe)
                return
            except _Skip:
                continue

    def _validate_once(self, evaluator: Evaluator, probe) -> None:
        values: Dict[str, Quantity] = {}
        for i, name in enumerate(self.inputs):
            if name in self.decls:
                values[name] = Quantity(probe(i), self.decls[name].unit.dim)
        scope = Scope(values, excluded=self.decls)
        inferred: Dict[str, Dim] = {}
        for rel in self.order:
            name = rel.lhs.name
            try:
                q = evaluator.eval(rel.rhs, scope)
            except UndefinedVariable:
                continue  # needs an input with no declared unit
            except ForgeEvalError:
                raise _Skip()
            if not isinstance(q, Quantity):
                raise ForgeSyntaxError(
                    "equation outputs must be scalar quantities; matrices and vectors are program values",
                    rel.rhs.span,
                    hint="Use matrix and vector operations in a program assignment instead.",
                )
            decl = self.decls.get(name)
            if decl is not None and decl.unit.dim != q.dim:
                raise UnitError(
                    f"{name} is declared as {describe_full(decl.unit.dim)} but this formula gives "
                    f"{describe_full(q.dim)}", rel.rhs.span,
                    hint=f"Check the declaration of {name} and the units of the inputs.",
                    notes=[f"in equation {self.name}"])
            inferred[name] = q.dim
            scope.set(name, Quantity(q.value, decl.unit.dim if decl else q.dim))
        for rel in self.implicit:
            try:
                left, right = evaluator.eval(rel.lhs, scope), evaluator.eval(rel.rhs, scope)
            except UndefinedVariable:
                continue
            except ForgeEvalError:
                raise _Skip()
            if not isinstance(left, Quantity) or not isinstance(right, Quantity):
                raise ForgeSyntaxError(
                    "implicit equation relations must compare scalar quantities",
                    rel.span,
                    hint="Matrices and vectors are currently program values, not solver relations.",
                )
            if left.dim != right.dim:
                raise UnitError(
                    f"the two sides of this equation measure different things: "
                    f"{describe_full(left.dim)} on the left, {describe_full(right.dim)} on the right",
                    rel.span, notes=[f"in equation {self.name}"])
        self.inferred = inferred

    # ---- calling -----------------------------------------------------------------------------
    def call(self, evaluator: Evaluator, args: Dict[str, Tuple[Quantity, Optional[Span]]],
             call_span: Optional[Span]) -> Dict[str, Quantity]:
        try:
            return self._call(evaluator, args, call_span)
        except ForgeError as err:
            if call_span is not None and err.span is not None and err.span.source is self.source:
                note = f"while calling {self.name}() at {call_span.location()}"
                if note not in err.notes:
                    err.notes.append(note)
            raise

    def _call(self, evaluator: Evaluator, args, call_span) -> Dict[str, Quantity]:
        if not self.callable:
            raise ForgeError(
                f"{self.name} states a relationship but does not define an output",
                call_span, title="Cannot call",
                hint=f"Use: solve {self.name} for <variable> {{ ... }}")
        for name, (_, span) in args.items():
            if name in self.outputs:
                raise ForgeError(
                    f"'{name}' is an output of {self.name}, not an input", span or call_span, title="Cannot call",
                    hint=f"To find an input from an output use: solve {self.name} for <input> {{ {name} = ... }}")
            if name not in self.inputs:
                close = difflib.get_close_matches(name, self.inputs, n=1, cutoff=0.5)
                tip = f"Did you mean '{close[0]}'? " if close else ""
                raise ForgeError(f"{self.name} has no input named '{name}'", span or call_span, title="Cannot call",
                                 hint=f"{tip}Its inputs are: {', '.join(self.inputs)}")
        missing = [n for n in self.inputs if n not in args]
        if missing:
            first = missing[0]
            raise ForgeError(
                f"{self.name} needs a value for: {', '.join(missing)}", call_span, title="Cannot call",
                hint=f"To find {first} from the other values instead, use: "
                     f"solve {self.name} for {first} {{ ... }}")
        values: Dict[str, Quantity] = {}
        for name, (q, span) in args.items():
            if not isinstance(q, Quantity):
                raise ForgeSyntaxError(
                    f"{name} of {self.name} must be a scalar quantity",
                    span or call_span,
                    hint="Matrices and vectors are currently supported as program values, not equation inputs.",
                )
            decl = self.decls.get(name)
            if decl is not None and decl.unit.dim != q.dim:
                raise UnitError(
                    f"{name} of {self.name} expects {describe_full(decl.unit.dim)}, "
                    f"but this is {describe_full(q.dim)}", span or call_span,
                    hint=f"{name} is declared as '{decl.unit.symbol()}'. Convert or correct the value.")
            values[name] = q
        scope = Scope(values, excluded=self.decls)
        for rel in self.order:
            name = rel.lhs.name
            value = evaluator.eval(rel.rhs, scope)
            if not isinstance(value, Quantity):
                raise ForgeSyntaxError(
                    "equation outputs must be scalar quantities",
                    rel.rhs.span,
                    hint="Matrices and vectors are currently supported as program values, not equation outputs.",
                )
            decl = self.decls.get(name)
            if decl is not None:
                if decl.unit.dim != value.dim:
                    raise UnitError(
                        f"{name} is declared as {describe_full(decl.unit.dim)} but this formula gives "
                        f"{describe_full(value.dim)}", rel.rhs.span,
                        hint="Check the declaration of the output and the units of the inputs.")
                value = Quantity(value.value, decl.unit.dim, decl.unit)
            scope.set(name, value)
        return {name: scope.values[name] for name in self.outputs}


class _Skip(Exception):
    """Internal: this probe assignment hit a math-domain error; try the next."""
