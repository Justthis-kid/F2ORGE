"""Numerical integration of ordinary differential equations.

`solveODE(f, y0, t0, t1)` walks a derivative function forward in time with an adaptive
Runge-Kutta-Fehlberg (4,5) step and returns the solution as vectors, so it plots like any other
time series:

    accel = -9.81 m/s^2
    def v(t, y) { return accel }                      # y is the value, t the time
    v0 = 20 m/s
    result = solveODE(v, v0, 0 s, 4 s)
    plot(result[0], result[1])                        # time against velocity

The solver adapts its step to keep the local error near a tolerance, so smooth and stiff-ish
problems both finish quickly.  Only one evolving quantity is supported; a system of equations can
be written as a vector-valued derivative and solved with `solveODE_system`.
"""
from __future__ import annotations

from typing import Callable, List, Sequence, Tuple

from .errors import ForgeEvalError


# Dormand-Prince (RK45) Butcher tableau, the method behind MATLAB's ode45.
_C = (0.0, 1 / 5, 3 / 10, 4 / 5, 8 / 9, 1.0)
_A = (
    (),
    (1 / 5,),
    (3 / 40, 9 / 40),
    (44 / 45, -56 / 15, 32 / 9),
    (19372 / 6561, -25360 / 2187, 64448 / 6561, -212 / 729),
    (9017 / 3168, -355 / 33, 46732 / 5247, 49 / 176, -5103 / 18656),
)
_B5 = (35 / 384, 0.0, 500 / 1113, 125 / 192, -2187 / 6784, 11 / 84)
_B4 = (5179 / 57600, 0.0, 7571 / 16695, 393 / 640, -92097 / 339200, 187 / 2100, 1 / 40)


def integrate(f: Callable[[float, float], float], y0: float, t0: float, t1: float,
              tolerance: float = 1e-7, max_steps: int = 20000) -> Tuple[List[float], List[float]]:
    """Integrate dy/dt = f(t, y) from t0 to t1, adapting the step (Dormand-Prince 5)."""
    if t1 == t0:
        return [t0], [y0]
    direction = 1.0 if t1 > t0 else -1.0
    times: List[float] = [t0]
    values: List[float] = [y0]
    t, y = t0, y0
    span = abs(t1 - t0)
    h = direction * span / 200.0  # about 200 points for a plot, refined where the error is large
    scale = max(span / 2000.0, 1e-12)  # never step below this: it keeps the list finite
    for _ in range(max_steps):
        if direction * (t - t1) >= -1e-15 * max(1.0, abs(t1)):
            break
        # Stop inside the requested span, and keep producing samples for a readable plot: the
        # step never grows past a two-hundredth of the span, however easy the solution is.
        h = direction * min(abs(h), abs(t1 - t), span / 200.0)
        k = _stages(f, t, y, h)
        y5 = y + h * sum(b * ki for b, ki in zip(_B5, k))
        y4 = y + h * (sum(b * ki for b, ki in zip(_B4, k[:6])) + _B4[6] * k[5])
        size = max(abs(y), abs(y5), 1.0)
        error = abs(y5 - y4) / size
        if error <= tolerance or abs(h) <= scale:
            t += h
            y = y5
            times.append(t)
            values.append(y)
        # Grow when the step was easy, shrink when it was not; never jump wildly.
        if error == 0:
            factor = 5.0
        else:
            factor = max(0.2, min(5.0, 0.9 * (tolerance / error) ** 0.2))
        h *= factor
        if abs(h) < scale:
            h = direction * scale
    else:
        raise ForgeEvalError(
            f"the differential equation needed more than {max_steps} steps",
            hint="Raise the end time in smaller pieces, or check that the derivative is finite.")
    return times, values


def _stages(f: Callable[[float, float], float], t: float, y: float, h: float) -> List[float]:
    k: List[float] = []
    for stage, row in enumerate(_A):
        yi = y + h * sum(a * kj for a, kj in zip(row, k))
        ti = t + _C[stage] * h
        value = f(ti, yi)
        if value != value or abs(value) == float("inf"):
            raise ForgeEvalError("the derivative is not finite at this point of the solution",
                                 hint="Check the equation and the starting value.")
        k.append(value)
    k.append(f(t + h, y + h * sum(b * ki for b, ki in zip(_B5, k))))
    return k

# ---- steady-state fields (the pdepe-shaped problem) -------------------------------------------
def solve_poisson(laplacian_sources: Sequence[Sequence[float]], cells: int,
                  sweeps: int = 4000, tolerance: float = 1e-9) -> List[List[float]]:
    """Relax a field to steady state on a `cells` x `cells` grid with fixed edges.

    `laplacian_sources` is a source term per interior cell (0 for Laplace's equation, which is heat
    flow, electrostatics, and seepage alike).  Each sweep sets every interior cell to the average of
    its four neighbours less its source, which is Gauss-Seidel on the five-point stencil.  The
    boundary rows and columns are taken from `laplacian_sources` and never change, so they are the
    boundary conditions.
    """
    n = cells
    grid = [list(row) for row in laplacian_sources]
    if len(grid) != n or any(len(row) != n for row in grid):
        raise ForgeEvalError(f"solvePDE() needs a {n} by {n} grid of values")
    for _ in range(sweeps):
        change = 0.0
        for i in range(1, n - 1):
            row, above, below = grid[i], grid[i - 1], grid[i + 1]
            for j in range(1, n - 1):
                value = 0.25 * (row[j - 1] + row[j + 1] + above[j] + below[j])
                change = max(change, abs(value - row[j]))
                row[j] = value
        if change <= tolerance:
            break
    return grid
