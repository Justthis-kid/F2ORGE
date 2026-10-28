"""F²ORGE (Formula Forge): a unit-safe programming language where reusable equations become
solvers, documentation and (soon) calculators and graphs."""

__version__ = "0.1.0"

from .errors import ForgeError  # noqa: E402
from .interpreter import Interpreter  # noqa: E402
from .quantity import Quantity  # noqa: E402

__all__ = ["ForgeError", "Interpreter", "Quantity", "__version__"]
