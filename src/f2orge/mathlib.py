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
