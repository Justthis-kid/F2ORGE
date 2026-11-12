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
from fractions import Fraction
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

# ---- simultaneous systems -------------------------------------------------------------------
@dataclass
class SystemSolution:
    """The unknowns of `solve A, B for x, y` and how they were found."""

    values: Dict[str, Quantity] = field(default_factory=dict)
    method: str = "newton"  # "newton" (damped iteration)
    steps: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def solve_system(equations: List["Equation"], unknowns: List[str],
                 givens: Dict[str, Tuple[Quantity, Optional[Span]]], evaluator: Evaluator,
                 call_span: Optional[Span] = None) -> SystemSolution:
    """Solve several equations for several unknowns at once.

    Units are inferred from the relations themselves, so `x + y = s` with s in metres makes x and
    y lengths while `I3 * 4 ohm = I2 * 3 ohm` makes them currents.  The system is then solved by
    a damped Newton iteration, which handles linear and nonlinear systems alike; a declared unit
    on an unknown (`I1 : A`) or a relation that pins it down settles what its unit is.
    """
    if len(equations) != len(unknowns):
        raise SolveError(
            f"{len(equations)} equation(s) cannot determine {len(unknowns)} unknowns", call_span,
            hint="Give one equation for each unknown, or remove an unknown from the list.")
    known: Dict[str, Quantity] = {name: q for name, (q, _) in givens.items()}
    for name in unknowns:
        if name in known:
            raise SolveError(f"'{name}' is given a value, so there is nothing to solve for", call_span)
    available: List[str] = []
    for eq in equations:
        for name in eq.variables:
            if name not in available:
                available.append(name)
    for name in unknowns:
        if name not in available:
            close = difflib.get_close_matches(name, available, n=1, cutoff=0.5)
            tip = (f"Did you mean '{close[0]}'? " if close else "") + f"Variables: {', '.join(available)}"
            raise SolveError(f"No equation has a variable named '{name}'", call_span, hint=tip)
    relations: List[Tuple["Equation", S.Relation]] = []
    for eq in equations:
        if not eq.relations:
            raise SolveError(f"{eq.name} has no relations to solve", call_span)
        relations.extend((eq, rel) for rel in eq.relations)

    dims, known_units = _unknown_dimensions(relations, unknowns, known, call_span)
    residual = _residual_function(relations, unknowns, known, dims, evaluator, call_span)
    guess = [_initial_guess(name, equations, dims[name]) for name in unknowns]
    solution = _newton(residual, unknowns, dims, guess, call_span)
    for name in unknowns:
        if name in known_units:
            value = solution.values[name]
            solution.values[name] = Quantity(value.value, value.dim, known_units[name])
    return solution


def _relation_vars(rel: S.Relation) -> List[str]:
    out: List[str] = []
    for name in S.names_in(rel.lhs) + S.names_in(rel.rhs):
        if name not in out:
            out.append(name)
    return out


# ---- unit inference --------------------------------------------------------------------------
def _unknown_dimensions(relations, unknowns, known, call_span=None):
    """The unit of each unknown, inferred from the equations that mention it.

    `x + y = s` with s in metres makes x and y lengths; `x^2 + y^2 = r2` with r2 in m² makes them
    lengths too, and `I3 * 4 ohm = I2 * 3 ohm` makes both currents.  A sum with no term whose size
    is known (`I1 - I2 - I3 = 0`) leaves its unknowns undecided until another relation settles one.
    """
    from .dimensions import Dim

    dims: Dict[str, Dim] = {}
    units: Dict[str, object] = {}
    for eq, rel in relations:
        for name in _relation_vars(rel):
            decl = eq.decls.get(name)
            if name in unknowns and decl is not None:
                dims[name] = decl.unit.dim
                units[name] = decl.unit
    # A sum whose terms include unknowns shares one dimension.  Remember which names are tied
    # together so a later relation that settles one of them settles them all.
    groups: List[List[str]] = []
    for _ in range(6):  # a few passes settle chains such as x = 2*y, y = z
        before = (dict(dims), [list(g) for g in groups])
        for eq, rel in relations:
            _infer_relation(rel, unknowns, dims, known, groups)
        _spread_groups(groups, dims)
        if (dims, groups) == before:
            break
    for name in unknowns:
        dims.setdefault(name, Dim.of())
    return dims, units


def _infer_relation(rel, unknowns, dims, known, groups):
    missing_left = [n for n in S.names_in(rel.lhs) if _open(n, unknowns, dims)]
    missing_right = [n for n in S.names_in(rel.rhs) if _open(n, unknowns, dims)]
    # Every term of a sum shares one dimension, whatever the sum turns out to measure.
    for side in (rel.lhs, rel.rhs):
        shared: List[str] = []
        for nodes in _sum_terms(side):
            for name in S.names_in(nodes):
                if name in unknowns and name not in shared:
                    shared.append(name)
        if len(shared) > 1 and shared not in groups:
            groups.append(shared)
    if not missing_left and not missing_right and not _runs_through_unknowns(rel, unknowns):
        return
    if missing_left and missing_right:
        _infer_proportional(rel, unknowns, dims, known)
        _infer_sum(rel, unknowns, dims, known, missing_left + missing_right)
        return
    # Unknowns on one side only: their sum must match the other side's dimension, which also
    # settles ties (I1 - I2 - I3 = 0 has unknowns on the left and a bare 0 on the right).
    _infer_sum(rel, unknowns, dims, known, missing_left + missing_right)
    for name in missing_left or missing_right:
        if not _open(name, unknowns, dims):
            continue
        shape = _dimension_for(rel, name, dims, known)
        if shape is not None and (not shape.is_dimensionless or _is_plain(rel)):
            dims[name] = shape


def _runs_through_unknowns(rel, unknowns) -> bool:
    """Does a relation multiply unknowns by units, so their real kind is still open?

    `I1 - I2 - I3 = 0` alone makes them plain numbers, but `I3 * 4 ohm = I2 * 3 ohm` shows they
    are currents; ties recorded here let the second relation correct the first.
    """
    for side in (rel.lhs, rel.rhs):
        for nodes in _sum_terms(side):
            if isinstance(nodes, S.Binary) and nodes.op == "*" \
                    and any(n in unknowns for n in S.names_in(nodes)):
                return True
    return False


def _is_plain(rel) -> bool:
    """Does the relation itself involve no units at all, so dimensionless answers are real?"""
    from .syntax import walk
    return not any(isinstance(node, S.QuantityLit) for node in walk(rel.lhs)) and \
        not any(isinstance(node, S.QuantityLit) for node in walk(rel.rhs))


def _infer_sum(rel, unknowns, dims, known, missing):
    """Settle the unknowns of a relation whose sides are sums of terms, term by term.

    Every term of one sum measures the same kind of quantity.  That quantity comes from the other
    side when it is fully known (`x^2 + y^2 = r2`, r2 in m²), from a known term of the same sum
    (`I1 - I2 - I3 = 0` alone gives nothing; `6 V = I1 * 2 ohm + ...` gives volts), and otherwise
    stays undecided until another relation settles one of the tied names.
    """
    for side, other in ((rel.lhs, rel.rhs), (rel.rhs, rel.lhs)):
        terms = _sum_terms(side)
        if not any(n in unknowns for n in S.names_in(side)):
            continue  # this side is known; the other one is the sum being measured
        term_dim = _side_dimension(other, unknowns, dims, known)
        if term_dim is None:
            # The other side itself has unknowns (`I1 - I2 - I3 = 0`): the sum's own terms are the
            # only clue left, and only a term with known units (`6 V`) can give one.
            term_dim = _known_term_dimension(_sum_terms(other), unknowns, dims, known)
        if term_dim is None:
            # `I1 - I2 - I3 = 0` has no term of known size, but its names share one dimension.
            # A later pass settles it once another relation has given one of them a dimension
            # (see _spread_groups); nothing can be said yet.
            continue
        for nodes in terms:
            if not any(_open(n, unknowns, dims) for n in S.names_in(nodes)):
                continue
            for name in S.names_in(nodes):
                if not _open(name, unknowns, dims):
                    continue
                if term_dim.is_dimensionless and not _is_plain(rel) and isinstance(nodes, S.Name):
                    continue  # `I1 - I2 - I3 = 0` says nothing about what a bare I1 measures
                dims[name] = _peel(nodes, name, term_dim, lambda node: _node_dimension(node, dims, known))


def _open(name, unknowns, dims) -> bool:
    """Is this unknown still waiting for a real dimension?  A placeholder does not count."""
    return name in unknowns and (name not in dims or dims[name].is_dimensionless)


def _infer_proportional(rel, unknowns, dims, known):
    """`I3 * 4 ohm = I2 * 3 ohm`: each side is one product, so each calls for its own units.

    Both sides must measure the same thing, and each holds a single unknown times known factors,
    so the unknown of a side is whatever makes that product measure the other side.
    """
    for side, other in ((rel.lhs, rel.rhs), (rel.rhs, rel.lhs)):
        if not _is_product(side) or not _is_product(other):
            continue  # sums are measured by _infer_sum, not one factor at a time
        names = [n for n in S.names_in(side) if n in unknowns]
        if len(names) != 1 or names[0] in dims:
            continue
        if any(n not in dims and n not in known for n in S.names_in(other)):
            continue  # the other side is still undecided too
        name = names[0]
        rest = _factors_without(side, name)
        if rest is None:
            continue  # the unknown is not a plain factor (x^2, x + 1, ...): leave it
        known_rest = _node_dimension(rest, dims, known)
        dims[name] = _node_dimension(other, dims, known) / known_rest


def _is_product(node) -> bool:
    """Is this expression a plain product of factors (x * 2 ohm), with no sum in it?"""
    if isinstance(node, S.Binary):
        if node.op in ("+", "-", "/", "/.", "^"):
            return False
        return _is_product(node.left) and _is_product(node.right)
    if isinstance(node, S.Unary):
        return _is_product(node.operand)
    return not isinstance(node, S.Call)


def _factors_without(side, name):
    """The product of `side` with `name` removed, or None when it is not a plain factor."""
    if isinstance(side, S.Name):
        return S.Number(1.0) if side.name == name else side
    if isinstance(side, S.Binary) and side.op == "*":
        left_has = name in S.names_in(side.left)
        right_has = name in S.names_in(side.right)
        if left_has and right_has:
            return None
        if left_has:
            block = _factors_without(side.left, name)
            return None if block is None else S.Binary("*", block, side.right)
        block = _factors_without(side.right, name)
        return None if block is None else S.Binary("*", side.left, block)
    if isinstance(side, S.Unary) and side.op == "-":
        return _factors_without(side.operand, name)
    return None


def _spread_groups(groups, dims):
    """Give every member of a tied sum the dimension any one member has.

    `I1 - I2 - I3 = 0` alone is dimensionless, so its members start out as plain numbers; when a
    relation such as `I3 * 4 ohm = I2 * 3 ohm` shows the kind of quantity they really are, all of
    them take it.
    """
    for group in groups:
        found = [dims[name] for name in group if name in dims and not dims[name].is_dimensionless]
        if not found:
            continue
        for name in group:
            if name not in dims or dims[name].is_dimensionless:
                dims[name] = found[0]


def _known_term_dimension(terms, unknowns, dims, known):
    """The dimension of a sum's terms, read from whichever term has no unresolved unknown.

    A plain number such as the `0` in `I1 - I2 - I3 = 0` is dimensionless either way, so it says
    nothing about the kind of quantity the sum measures.
    """
    for term in terms:
        if any(n in unknowns and n not in dims for n in S.names_in(term)):
            continue
        shape = _node_dimension(term, dims, known)
        if not shape.is_dimensionless:
            return shape
    return None


def _sum_terms(node) -> List[object]:
    """The terms of a sum: `x^2 + y^2` gives [`x^2`, `y^2`]."""
    if isinstance(node, S.Binary) and node.op in ("+", "-"):
        return _sum_terms(node.left) + _sum_terms(node.right)
    return [node]


def _node_dimension(node, dims, known):
    """The dimension of an expression, treating names without a known dimension as plain numbers."""
    from .dimensions import Dim

    if isinstance(node, S.Name):
        if node.name in dims:
            return dims[node.name]
        if node.name in known:
            return known[node.name].dim
        return Dim.of()
    if isinstance(node, S.QuantityLit):
        return node.unit.dim
    if isinstance(node, S.Number):
        return Dim.of()
    if isinstance(node, S.Unary):
        return _node_dimension(node.operand, dims, known)
    if isinstance(node, S.Binary):
        left = _node_dimension(node.left, dims, known)
        right = _node_dimension(node.right, dims, known)
        if node.op in ("+", "-"):
            return left
        if node.op == "*":
            return left * right
        if node.op in ("/", "/."):
            return left / right
        if node.op == "^" and isinstance(node.right, S.Number):
            return left ** node.right.value
        return Dim.of()
    if isinstance(node, S.Call) and node.args:
        inner = _node_dimension(node.args[0], dims, known)
        if node.func == "sqrt":
            return inner ** (Fraction(1, 2))
        if node.func in ("sin", "cos", "tan", "asin", "acos", "atan", "ln", "log", "log2", "exp"):
            return Dim.of()
        return inner
    return Dim.of()


def _resolved(node, unknowns, dims, known) -> bool:
    """Does every name in `node` have a real dimension (a plain placeholder does not count)?"""
    for name in S.names_in(node):
        if name in known:
            continue
        if name not in dims or dims[name].is_dimensionless:
            return False
    return True


def _side_dimension(node, unknowns, dims, known):
    """The dimension a side of a relation has once everything in it is known; None if not.

    A name that is only a dimensionless placeholder counts as not known: `I1 - I2 - I3 = 0` does
    not make the currents plain numbers, it only says nothing about what they measure.
    """
    if not _resolved(node, unknowns, dims, known):
        return None
    return _node_dimension(node, dims, known)


def _dimension_for(rel, name, dims, known):
    """The dimension `name` needs so the relation balances, or None when it cannot be told."""
    def dim_of(node):
        return _node_dimension(node, dims, known)

    on_left = name in S.names_in(rel.lhs)
    on_right = name in S.names_in(rel.rhs)
    if on_left and not on_right:
        return _peel(rel.lhs, name, _measure(rel.rhs, dims, known, dim_of(rel.rhs)), dim_of)
    if on_right and not on_left:
        return _peel(rel.rhs, name, _measure(rel.lhs, dims, known, dim_of(rel.lhs)), dim_of)
    return None  # both sides hold the unknown: the sum rules decide instead


def _measure(side, dims, known, fallback):
    """The dimension `side` has, or `fallback` when it still holds an undecided unknown."""
    if any(n not in dims and n not in known for n in S.names_in(side)):
        return fallback
    return _node_dimension(side, dims, known)


def _peel(side, name, other, dim_of):
    """The dimension `name` needs so that `side`, written with `name`, measures `other`.

    `x` alone needs `other`; `x / R` needs `other * R`; `x^2` needs the square root of `other`;
    inside a sum, the term holding `name` is measured by the sum's own dimension.
    """
    from .dimensions import Dim

    if isinstance(side, S.Name) and side.name == name:
        return other
    if isinstance(side, S.Binary):
        if side.op in ("+", "-"):
            block = side.left if name in S.names_in(side.left) else side.right
            return _peel(block, name, other, dim_of)
        if side.op == "*":
            block, rest = (side.left, side.right) if name in S.names_in(side.left) else (side.right, side.left)
            return _peel(block, name, other / dim_of(rest), dim_of)
        if side.op == "/":
            if name in S.names_in(side.left):
                return _peel(side.left, name, other * dim_of(side.right), dim_of)
            return _peel(side.right, name, dim_of(side.left) / other, dim_of)
        if side.op == "^" and isinstance(side.right, S.Number) and side.right.value:
            return _peel(side.left, name, other ** (1.0 / side.right.value), dim_of)
    if isinstance(side, S.Unary):
        return _peel(side.operand, name, other, dim_of)
    if isinstance(side, S.Call) and len(side.args) == 1:
        if side.func == "sqrt":
            return _peel(side.args[0], name, other ** 2, dim_of)
        return _peel(side.args[0], name, other, dim_of)
    return other if name in S.names_in(side) else Dim.of()


# ---- numeric solution ------------------------------------------------------------------------
def _residual_function(relations, unknowns, known, dims, evaluator, call_span):
    def residual(values: List[float]) -> List[float]:
        scope_values: Dict[str, object] = dict(known)
        for name, value in zip(unknowns, values):
            scope_values[name] = Quantity(value, dims[name])
        scope = Scope(scope_values)
        out: List[float] = []
        for eq, rel in relations:
            try:
                left = evaluator.eval(rel.lhs, scope)
                right = evaluator.eval(rel.rhs, scope)
            except ForgeError as err:
                raise SolveError(
                    f"{err.message} while solving {format_relation(rel)} in {eq.name}", call_span,
                    hint="Check the units of the equations and the known values.") from None
            if not isinstance(left, Quantity) or not isinstance(right, Quantity):
                raise SolveError("simultaneous solving needs scalar equation relations", call_span)
            if left.dim != right.dim:
                # A bare 0 on one side of `I1 - I2 - I3 = 0` is a statement about zero, not a
                # quantity of another kind: it balances whatever the other side measures.
                if isinstance(rel.rhs, S.Number) and rel.rhs.value == 0:
                    out.append(left.value)
                    continue
                if isinstance(rel.lhs, S.Number) and rel.lhs.value == 0:
                    out.append(-right.value)
                    continue
                raise UnitError(
                    f"the two sides of {format_relation(rel)} measure different things: "
                    f"{describe_full(left.dim)} vs {describe_full(right.dim)}", call_span,
                    hint="Declare each unknown's unit in the equation that defines it, e.g. 'I1 : A'.",
                    notes=[f"in equation {eq.name}"])
            out.append(left.value - right.value)
        return out

    return residual


def _initial_guess(name, equations, dim) -> float:
    from .constants import CONSTANTS

    for eq in equations:
        decl = eq.decls.get(name)
        if decl is not None and not decl.unit.dim.is_dimensionless:
            return Quantity(1.0, decl.unit.dim).value  # one coherent SI unit of the right kind
    constant = CONSTANTS.get(name)
    if constant is not None and constant.dim == dim:
        return constant.value
    return 1.0


def _newton(residual, unknowns, dims, guess, call_span) -> SystemSolution:
    """Damped Newton iteration on the residuals, scaled so very small and very large units work."""
    n = len(unknowns)
    values = list(guess)
    scales = [max(abs(v), 1e-6) for v in values]
    for _iteration in range(60):
        f = residual(values)
        if all(item == 0 or abs(item) <= 1e-12 * max(1.0, abs(item)) for item in f):
            break
        jacobian = [[0.0] * n for _ in range(n)]
        for j in range(n):
            step = 1e-7 * scales[j]
            bumped = list(values)
            bumped[j] += step
            column = residual(bumped)
            for i in range(n):
                jacobian[i][j] = (column[i] - f[i]) / step
        try:
            delta = _linear_solve(jacobian, [-item for item in f])
        except ForgeEvalError:
            raise SolveError(
                "this system cannot be solved: the equations are dependent or have no single solution",
                call_span, hint="Check that every equation adds new information.") from None
        size = max(abs(delta[j]) / scales[j] for j in range(n))
        damping = 1.0
        trial = [values[j] + damping * delta[j] for j in range(n)]
        while damping > 1e-6:
            trial_f = residual(trial)
            if sum(v * v for v in trial_f) <= sum(v * v for v in f):
                break
            damping /= 2
            trial = [values[j] + damping * delta[j] for j in range(n)]
        values = trial
        if size < 1e-14:
            break
    else:
        raise SolveError(
            f"no solution found after 60 iterations for {', '.join(unknowns)}", call_span,
            hint="Check the known values, or give the unknowns declared units in their equations.")
    result = SystemSolution(steps=[f"solved {n} unknowns simultaneously with Newton's method"])
    for name, value in zip(unknowns, values):
        result.values[name] = Quantity(value, dims[name])
    return result


def _linear_solve(matrix: List[List[float]], rhs: List[float]) -> List[float]:
    """Gaussian elimination with partial pivoting; raises for a singular system."""
    n = len(rhs)
    work = [list(row) + [rhs[i]] for i, row in enumerate(matrix)]
    for column in range(n):
        pivot = max(range(column, n), key=lambda row: abs(work[row][column]))
        if abs(work[pivot][column]) <= 1e-14:
            raise ForgeEvalError("singular system")
        work[column], work[pivot] = work[pivot], work[column]
        divisor = work[column][column]
        work[column] = [value / divisor for value in work[column]]
        for row in range(n):
            if row == column:
                continue
            factor = work[row][column]
            work[row] = [value - factor * pivot_value
                         for value, pivot_value in zip(work[row], work[column])]
    return [work[i][n] for i in range(n)]
