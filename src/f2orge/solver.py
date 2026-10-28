"""Solving for a variable (features 16, 17, 18).

Strategy, in order of preference:

1. Rearrange symbolically.  If the unknown appears exactly once in a relation, peel the
   expression tree away from the unknown, inverting one operation at a time:

       F = m * a      solve for a:   a = F / m
       v^2 = u^2 + 2*a*s   for u:    u = sqrt(v^2 - 2*a*s)

   The result is an expression tree that is then evaluated with unit-checked arithmetic, so the
   dimensions of the answer come out right by construction.  (Feature 17.)

2. Propagate through several relations.  A relation with exactly one unknown yields that
   unknown, which may unlock the next relation, until the requested variable is known.

3. Numeric fallback.  If the unknown appears more than once (x + x^2 = 6) the relation cannot
   be rearranged by peeling, so the residual lhs - rhs is scanned for sign changes over many
   orders of magnitude and each bracket is refined by bisection.  This needs the unknown's
   unit to be declared, since its dimension cannot be inferred.

When the information is insufficient the error names exactly what is missing.  (Feature 18.)
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from . import syntax as S
from .dimensions import describe_full
from .errors import ForgeError, ForgeEvalError, SolveError, Span, UnitError
from .evaluator import Evaluator, Scope
from .printer import format_expr, format_relation
from .quantity import Quantity

_INVERSE = {"ln": "exp", "exp": "ln", "sin": "asin", "cos": "acos", "tan": "atan",
            "asin": "sin", "acos": "cos", "atan": "tan"}
_PRINCIPAL = {"sin": "asin", "cos": "acos", "tan": "atan"}


@dataclass
class Solution:
    target: str
    value: Quantity
    steps: List[str] = field(default_factory=list)  # the rearranged formulas that were used
    notes: List[str] = field(default_factory=list)  # caveats such as "x^2 also has a negative root"


# ---- symbolic rearrangement ---------------------------------------------------------------
def isolate(lhs, rhs, var: str) -> Optional[Tuple[object, List[str]]]:
    """Return (expr, notes) with `var = expr`, or None if var is not isolable by peeling."""
    in_left, in_right = S.count_name(lhs, var), S.count_name(rhs, var)
    if in_left + in_right != 1:
        return None
    node, other = (lhs, rhs) if in_left == 1 else (rhs, lhs)
    notes: List[str] = []
    while True:
        if isinstance(node, S.Name):
            return other, notes
        if isinstance(node, S.Unary):
            other, node = S.Unary("-", other), node.operand
        elif isinstance(node, S.Binary):
            left_has = S.count_name(node.left, var) == 1
            a, b = node.left, node.right
            if node.op == "+":
                other, node = (S.Binary("-", other, b), a) if left_has else (S.Binary("-", other, a), b)
            elif node.op == "-":
                other, node = (S.Binary("+", other, b), a) if left_has else (S.Binary("-", a, other), b)
            elif node.op == "*":
                other, node = (S.Binary("/", other, b), a) if left_has else (S.Binary("/", other, a), b)
            elif node.op == "/":
                other, node = (S.Binary("*", other, b), a) if left_has else (S.Binary("/", a, other), b)
            else:  # '^'
                if left_has:
                    is_even = (isinstance(b, S.Number) and float(b.value).is_integer()
                               and int(b.value) % 2 == 0)
                    if is_even:
                        notes.append(f"{format_expr(a)}^{int(b.value)} also has a negative solution; "
                                     "the positive one is shown")
                    if isinstance(b, S.Number) and b.value == 2:
                        other = S.Call("sqrt", (other,))
                    else:
                        other = S.Binary("^", other, S.Binary("/", S.Number(1.0), b))
                    node = a
                else:
                    other = S.Binary("/", S.Call("ln", (other,)), S.Call("ln", (a,)))
                    node = b
        elif isinstance(node, S.Call) and len(node.args) == 1 and not node.kwargs:
            f = node.func
            if f in _INVERSE:
                if f in _PRINCIPAL:
                    notes.append(f"{f}() repeats, so {_INVERSE[f]}() gives only the principal angle")
                other, node = S.Call(_INVERSE[f], (other,)), node.args[0]
            elif f == "log":
                other, node = S.Binary("^", S.Number(10.0), other), node.args[0]
            elif f == "sqrt":
                other, node = S.Binary("^", other, S.Number(2.0)), node.args[0]
            else:
                return None
        else:
            return None


# ---- numeric fallback ---------------------------------------------------------------------
def _grid() -> List[float]:
    mags = [10.0 ** (k / 2.0) for k in range(-18, 25)]  # 1e-9 .. 1e12 SI units
    return sorted({-m for m in mags} | {0.0} | set(mags))


def _numeric(eq, idx: int, var: str, known: Dict[str, Quantity], evaluator: Evaluator,
             call_span: Optional[Span]) -> Tuple[Quantity, List[str]]:
    rel = eq.relations[idx]
    text = format_relation(rel)
    decl = eq.decls.get(var)
    if decl is None:
        raise SolveError(
            f"'{var}' appears more than once in {text}, so it cannot be rearranged by hand", call_span,
            hint=f"Declare its unit in the equation (for example '{var} : m') so it can be solved numerically.",
            notes=[f"in equation {eq.name}"])
    dim = decl.unit.dim
    excluded = set(eq.decls)

    def residual(x: float) -> Optional[float]:
        scope = Scope({**known, var: Quantity(x, dim)}, excluded=excluded)
        try:
            left, right = evaluator.eval(rel.lhs, scope), evaluator.eval(rel.rhs, scope)
        except (ForgeEvalError, OverflowError, ZeroDivisionError, ValueError):
            return None
        if left.dim != right.dim:
            raise UnitError(
                f"the two sides of {text} measure different things: {describe_full(left.dim)} vs "
                f"{describe_full(right.dim)}", call_span, hint="Check the units of the known values.")
        r = left.value - right.value
        return r if r == r and abs(r) != float("inf") else None

    pts = [(x, residual(x)) for x in _grid()]
    roots: List[float] = []
    for (x0, r0), (x1, r1) in zip(pts, pts[1:]):
        if r0 is None or r1 is None:
            continue
        if r0 == 0.0:
            roots.append(x0)
        if r0 * r1 < 0.0:
            lo, hi, rlo = x0, x1, r0
            scale = max(abs(r0), abs(r1))
            for _ in range(200):
                mid = 0.5 * (lo + hi)
                rm = residual(mid)
                if rm is None:
                    break
                if rm == 0.0 or abs(hi - lo) <= 1e-15 * max(abs(lo), abs(hi), 1e-300):
                    lo = hi = mid
                    break
                if rlo * rm < 0.0:
                    hi = mid
                else:
                    lo, rlo = mid, rm
            root = 0.5 * (lo + hi)
            rr = residual(root)
            if rr is not None and abs(rr) <= 1e-6 * scale:  # a pole (1/x) flips sign without a root
                roots.append(root)
    if pts[-1][1] == 0.0:
        roots.append(pts[-1][0])
    unique: List[float] = []
    for r in sorted(roots):
        if not unique or abs(r - unique[-1]) > 1e-9 * max(abs(r), 1e-300):
            unique.append(r)
    if not unique:
        raise SolveError(f"no solution for {var} found in {text}", call_span,
                         hint="Searched 1e-9 to 1e12 in both signs, in SI units. Check the known values.",
                         notes=[f"in equation {eq.name}"])
    positive = [r for r in unique if r > 0]
    chosen = min(positive) if positive else min(unique, key=abs)
    notes = [f"{var} appears more than once in {text}, so it was solved numerically"]
    if len(unique) > 1:
        others = ", ".join(str(Quantity(r, dim, decl.unit)) for r in unique if r != chosen)
        notes.append(f"there are other solutions: {others}")
    return Quantity(chosen, dim, decl.unit), notes


# ---- driver -------------------------------------------------------------------------------
def solve(eq, target: str, givens: Dict[str, Tuple[Quantity, Optional[Span]]], evaluator: Evaluator,
          call_span: Optional[Span] = None, target_span: Optional[Span] = None) -> Solution:
    def suggestion(name: str) -> str:
        close = difflib.get_close_matches(name, eq.variables, n=1, cutoff=0.5)
        return (f"Did you mean '{close[0]}'? " if close else "") + f"Variables of {eq.name}: {', '.join(eq.variables)}"

    if target not in eq.variables:
        raise SolveError(f"{eq.name} has no variable named '{target}'", target_span or call_span,
                         hint=suggestion(target))
    for name, (_, span) in givens.items():
        if name not in eq.variables:
            raise SolveError(f"{eq.name} has no variable named '{name}'", span or call_span, hint=suggestion(name))
    if target in givens:
        raise SolveError(f"'{target}' is given a value, so there is nothing to solve for",
                         givens[target][1] or call_span, hint=f"Remove '{target}' from the known values.")

    known: Dict[str, Quantity] = {}
    for name, (q, span) in givens.items():
        decl = eq.decls.get(name)
        if decl is not None and decl.unit.dim != q.dim:
            raise UnitError(f"{name} of {eq.name} expects {describe_full(decl.unit.dim)}, "
                            f"but this is {describe_full(q.dim)}", span or call_span,
                            hint=f"{name} is declared as '{decl.unit.symbol()}'.")
        known[name] = q

    steps: List[str] = []
    notes: List[str] = []
    done: Set[int] = set()

    def finish(var: str, value: Quantity, idx: int) -> Quantity:
        decl = eq.decls.get(var)
        if decl is not None:
            if decl.unit.dim != value.dim:
                raise UnitError(
                    f"solving gives {describe_full(value.dim)} but {var} is declared as "
                    f"{describe_full(decl.unit.dim)}", call_span,
                    hint="One of the known values probably has the wrong unit.",
                    notes=[f"using {format_relation(eq.relations[idx])} in {eq.name}"])
            value = Quantity(value.value, decl.unit.dim, decl.unit)
        return value

    while target not in known:
        progress = False
        for idx, rel in enumerate(eq.relations):
            if idx in done:
                continue
            unknown = [v for v in eq.rel_vars[idx] if v not in known]
            if not unknown:
                done.add(idx)
                continue
            if len(unknown) != 1:
                continue
            var = unknown[0]
            iso = isolate(rel.lhs, rel.rhs, var)
            if iso is not None:
                expr, inv_notes = iso
                try:
                    value = evaluator.eval(expr, Scope(known, excluded=eq.decls))
                except ForgeError as err:
                    if err.span is None or err.span.source is not (call_span.source if call_span else None):
                        err.span = call_span if call_span is not None else err.span
                    err.notes.append(f"while rearranging {format_relation(rel)} in {eq.name} to {var} = {format_expr(expr)}")
                    raise
                steps.append(f"{var} = {format_expr(expr)}")
                notes.extend(inv_notes)
            else:
                value, num_notes = _numeric(eq, idx, var, known, evaluator, call_span)
                steps.append(f"{var}: solved numerically from {format_relation(rel)}")
                notes.extend(num_notes)
            known[var] = finish(var, value, idx)
            done.add(idx)
            progress = True
            if var == target:
                break
        if not progress:
            break

    if target not in known:
        best_idx, best_unknown = None, None
        for idx, vars_ in enumerate(eq.rel_vars):
            if target in vars_:
                unknown = [v for v in vars_ if v not in known]
                if best_unknown is None or len(unknown) < len(best_unknown):
                    best_idx, best_unknown = idx, unknown
        others = [v for v in (best_unknown or []) if v != target]
        rel_text = format_relation(eq.relations[best_idx])
        who = ", ".join(others)
        verb = "is" if len(others) == 1 else "are"
        raise SolveError(
            f"cannot find {target} from {rel_text}: {who} {verb} unknown as well", call_span,
            hint=f"Add {'a value for ' + who if len(others) == 1 else 'values for: ' + who} to the solve block.",
            notes=[f"in equation {eq.name}"])
    return Solution(target, known[target], steps, notes)


def rearrangements(eq) -> List[str]:
    """Every `var = ...` form the solver can derive from single relations (for the generated docs)."""
    out: List[str] = []
    for idx, rel in enumerate(eq.relations):
        for var in eq.rel_vars[idx]:
            if isinstance(rel.lhs, S.Name) and rel.lhs.name == var:
                continue  # that is the formula itself
            iso = isolate(rel.lhs, rel.rhs, var)
            if iso is not None:
                text = f"{var} = {format_expr(iso[0])}"
                if text not in out:
                    out.append(text)
    return out
