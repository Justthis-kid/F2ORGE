"""Documentation generation (feature 14): Formula, Inputs, Outputs, Units, Description."""
from __future__ import annotations

from typing import Iterable, List

from .dimensions import describe
from .equation import Equation
from .printer import format_relation
from .solver import rearrangements
from .units import Unit


def _unit_text(eq: Equation, name: str) -> str:
    decl = eq.decls.get(name)
    if decl is not None:
        return decl.unit.symbol() or "dimensionless"
    dim = eq.inferred.get(name)
    if dim is not None:  # worked out from the formula and the declared inputs
        return (Unit.from_dim(dim).symbol() or "dimensionless") + " (derived)"
    return "any"


def _kind_text(eq: Equation, name: str) -> str:
    decl = eq.decls.get(name)
    dim = decl.unit.dim if decl is not None else eq.inferred.get(name)
    return describe(dim) if dim is not None else ""


def document(eq: Equation) -> str:
    lines: List[str] = [f"# {eq.name}", ""]
    if "description" in eq.metadata:
        lines += [f"> {eq.metadata['description']}", ""]
    lines += ["## Formula", "", "```"] + [format_relation(r) for r in eq.relations] + ["```", ""]

    def table(title: str, names: List[str]) -> None:
        if not names:
            return
        lines.extend([f"## {title}", "", "| Name | Unit | Kind | Description |", "|---|---|---|---|"])
        for n in names:
            doc = eq.decls[n].doc if n in eq.decls and eq.decls[n].doc else ""
            lines.append(f"| `{n}` | {_unit_text(eq, n)} | {_kind_text(eq, n)} | {doc} |")
        lines.append("")

    table("Inputs" if eq.callable else "Variables", eq.inputs if eq.callable else eq.variables)
    table("Outputs", eq.outputs)

    forms = rearrangements(eq)
    if forms:
        lines += ["## Solve for any variable", ""] + [f"- `{f}`" for f in forms] + [""]
    extra = {k: v for k, v in eq.metadata.items() if k != "description"}
    if extra:
        lines += ["## Details", ""] + [f"- **{k}**: {v}" for k, v in extra.items()] + [""]
    return "\n".join(lines).rstrip() + "\n"


def document_all(equations: Iterable[Equation]) -> str:
    return "\n".join(document(eq) for eq in equations)
