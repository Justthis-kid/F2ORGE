"""Numerical math and graph data for the in-script functions.

`integrate`, `derivative`, `roots`, `fzero`, and `minimize` sample a caller-supplied function
of one variable; the evaluator connects them to its own function table.  `Samples` describes one
graph drawn by a `plot` statement — a single series such as a curve of y against x, a polar
curve, or a 2D heat map or 3D surface on a grid.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .errors import ForgeEvalError

Number = float


def secant(f: Callable[[float], float], a: float, b: float, iterations: int = 80) -> float:
    fa, fb = f(a), f(b)
    if not (math.isfinite(fa) and math.isfinite(fb)):
        raise ForgeEvalError("the function must have finite values inside the bracket")
    if fa == 0:
        return a
    if fb == 0:
        return b
    x0, x1 = a, b
    for _ in range(iterations):
        f0, f1 = f(x0), f(x1)
        if f1 == f0:
            break
        x0, x1 = x1, x1 - f1 * (x1 - x0) / (f1 - f0)
        if not math.isfinite(x1):
            break
        if abs(x1 - x0) <= 1e-14 * max(1.0, abs(x1)):
            break
    return x1


def bisect(f: Callable[[float], float], a: float, b: float, iterations: int = 200) -> float:
    fa, fb = f(a), f(b)
    if fa == 0:
        return a
    if fb == 0:
        return b
    if fa * fb > 0:
        raise ForgeEvalError("fzero() needs values with opposite signs at the two ends of the bracket",
                             hint="Pick a and b so f(a) and f(b) have different signs.")
    for _ in range(iterations):
        middle = (a + b) / 2
        fm = f(middle)
        if fm == 0 or abs(b - a) <= 1e-15 * max(1.0, abs(middle)):
            return middle
        if fa * fm < 0:
            b, fb = middle, fm
        else:
            a, fa = middle, fm
    return (a + b) / 2


def golden(f: Callable[[float], float], a: float, b: float, iterations: int = 300) -> Tuple[float, float]:
    """Minimum of a unimodal function on [a, b]."""
    golden_ratio = (math.sqrt(5.0) - 1.0) / 2.0
    c = b - golden_ratio * (b - a)
    d = a + golden_ratio * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(iterations):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - golden_ratio * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + golden_ratio * (b - a)
            fd = f(d)
        if abs(b - a) <= 1e-14 * max(1.0, abs(a), abs(b)):
            break
    x = (a + b) / 2
    return x, f(x)


def adaptive_simpson(f: Callable[[float], float], a: float, b: float, tolerance: float,
                     limit: int = 50) -> float:
    """Numerical integral by adaptive Simpson subdivision (f is smooth enough for it)."""
    if a == b:
        return 0.0

    def simpson(lo: float, hi: float, f_lo: float, f_mid: float, f_hi: float) -> float:
        return (hi - lo) / 6.0 * (f_lo + 4.0 * f_mid + f_hi)

    def recurse(lo: float, hi: float, f_lo: float, f_mid: float, f_hi: float,
                estimate: float, allowed: float, depth: int) -> float:
        middle = (lo + hi) / 2.0
        left_mid = (lo + middle) / 2.0
        right_mid = (middle + hi) / 2.0
        f_left_mid, f_right_mid = f(left_mid), f(right_mid)
        left = simpson(lo, middle, f_lo, f_left_mid, f_mid)
        right = simpson(middle, hi, f_mid, f_right_mid, f_hi)
        refined = left + right
        if depth <= 0 or abs(refined - estimate) <= 15.0 * allowed:
            return refined + (refined - estimate) / 15.0
        return (recurse(lo, middle, f_lo, f_left_mid, f_mid, left, allowed / 2.0, depth - 1) +
                recurse(middle, hi, f_mid, f_right_mid, f_hi, right, allowed / 2.0, depth - 1))

    middle = (a + b) / 2.0
    f_a, f_mid, f_b = f(a), f(middle), f(b)
    return recurse(a, b, f_a, f_mid, f_b, simpson(a, b, f_a, f_mid, f_b), tolerance, limit)


@dataclass
class Samples:
    """Data for one graph: either one series, or (for 3D) a grid of rows."""

    kind: str                      # "plot", "polar", "heatmap", "surface"
    title: str
    x_label: str
    y_label: str
    series: List[Tuple[str, List[Tuple[float, float]]]] = field(default_factory=list)
    z_label: str = ""
    grid: Optional[List[List[Optional[float]]]] = None
    xs: Optional[List[float]] = None
    ys: Optional[List[float]] = None
    grid_title: str = ""

    def as_plot_dict(self) -> Dict[str, object]:
        """The form the CLI, desktop IDE, and browser IDE already draw."""
        if self.kind in ("heatmap", "surface"):
            return {
                "kind": self.kind,
                "title": self.title,
                "xLabel": self.x_label,
                "yLabel": self.y_label,
                "zLabel": self.z_label,
                "xs": self.xs,
                "ys": self.ys,
                "grid": self.grid,
            }
        return {
            "kind": "plot",
            "title": self.title,
            "xLabel": self.x_label,
            "yLabel": self.y_label,
            "points": self.series[0][1],
            "series": [(label, points) for label, points in self.series],
        }


def nelder_mead(f: Callable[[List[float]], float], start: List[float],
                tolerance: float = 1e-10, iterations: int = 5000) -> Tuple[List[float], float]:
    """Minimise f over several variables with the Nelder-Mead simplex method.

    This is the algorithm behind MATLAB's fminsearch: no derivatives, a simplex of n+1 points that
    reflects, expands, contracts, and shrinks toward the best corner.
    """
    n = len(start)
    if n == 0:
        raise ForgeEvalError("minimise() needs at least one variable")
    step = [0.05 * (abs(value) if value else 1.0) for value in start]
    simplex = [list(start)]
    for i in range(n):
        point = list(start)
        point[i] += step[i]
        simplex.append(point)
    values = [f(point) for point in simplex]
    for _ in range(iterations):
        order = sorted(range(n + 1), key=lambda i: values[i])
        simplex = [simplex[i] for i in order]
        values = [values[i] for i in order]
        spread = max(abs(values[0] - values[-1]),
                     max(max(abs(a - b) for a, b in zip(simplex[0], point)) for point in simplex[1:]))
        if spread <= tolerance:
            break
        centroid = [sum(point[i] for point in simplex[:-1]) / n for i in range(n)]
        worst = simplex[-1]
        reflected = [centroid[i] + (centroid[i] - worst[i]) for i in range(n)]
        reflected_value = f(reflected)
        if reflected_value < values[0]:
            expanded = [centroid[i] + 2.0 * (centroid[i] - worst[i]) for i in range(n)]
            expanded_value = f(expanded)
            simplex[-1], values[-1] = (expanded, expanded_value) if expanded_value < reflected_value \
                else (reflected, reflected_value)
        elif reflected_value < values[-2]:
            simplex[-1], values[-1] = reflected, reflected_value
        else:
            contracted = [centroid[i] + 0.5 * (worst[i] - centroid[i]) for i in range(n)]
            contracted_value = f(contracted)
            if contracted_value < values[-1]:
                simplex[-1], values[-1] = contracted, contracted_value
            else:  # shrink everything toward the best corner
                best = simplex[0]
                simplex = [best] + [[best[i] + 0.5 * (point[i] - best[i]) for i in range(n)]
                                    for point in simplex[1:]]
                values = [values[0]] + [f(point) for point in simplex[1:]]
    best = min(range(n + 1), key=lambda i: values[i])
    return simplex[best], values[best]


def simplex_linear(objective: List[float], constraints: List[List[float]],
                   bounds: List[float], sense: str = "max") -> Tuple[List[float], float]:
    """Solve a linear program with the simplex method.

    `objective` is the coefficient of each variable, each row of `constraints` is a constraint
    `sum(a_i x_i) <= bounds[i]`, and every variable is non-negative.  `sense` is "max" or "min".
    Returns the values of the variables and the objective there.
    """
    n = len(objective)
    m = len(constraints)
    if any(len(row) != n for row in constraints):
        raise ForgeEvalError("each constraint needs one coefficient for every variable")
    if len(bounds) != m:
        raise ForgeEvalError("each constraint needs a bound")
    sign = -1.0 if sense == "max" else 1.0  # the simplex minimises, so flip a maximisation
    costs = [sign * c for c in objective]
    # Slack variables turn each inequality into an equation; the basis starts as the slacks.
    tableau = []
    for i in range(m):
        if bounds[i] < 0:
            raise ForgeEvalError("linear programming needs non-negative bounds",
                                 hint="Move a term to the other side so the right-hand side is positive.")
        tableau.append(constraints[i] + [1.0 if j == i else 0.0 for j in range(m)] + [bounds[i]])
    tableau.append(costs + [0.0] * m + [0.0])
    width = n + m
    basis = [n + i for i in range(m)]
    for _ in range(500):
        row = tableau[-1]
        entering = min(range(width), key=lambda j: row[j])
        if row[entering] >= -1e-12:
            break  # no improving direction remains
        ratios = [(tableau[i][width] / tableau[i][entering], i)
                  for i in range(m) if tableau[i][entering] > 1e-12]
        if not ratios:
            raise ForgeEvalError("this linear program is unbounded", hint="Check the constraints.")
        _, pivot_row = min(ratios)
        pivot = tableau[pivot_row][entering]
        tableau[pivot_row] = [value / pivot for value in tableau[pivot_row]]
        for i in range(m + 1):
            if i != pivot_row and abs(tableau[i][entering]) > 1e-15:
                factor = tableau[i][entering]
                tableau[i] = [value - factor * pv for value, pv in zip(tableau[i], tableau[pivot_row])]
        basis[pivot_row] = entering
    solution = [0.0] * n
    for row, variable in enumerate(basis):
        if variable < n:
            solution[variable] = tableau[row][width]
    return solution, sum(c * x for c, x in zip(objective, solution))
