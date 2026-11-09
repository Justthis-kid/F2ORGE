"""Statement execution: variables, equations, imports/exports, solve, convert, print."""
from __future__ import annotations

import difflib
import math
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from . import syntax as S
from .equation import Equation
from .errors import ForgeError, ForgeImportError, ForgeNameError, Source, UnitError
from .evaluator import Evaluator, Scope
from .linear_algebra import Value, Vector
from .parser import parse
from .printer import format_equation
from .quantity import Quantity
from .solver import solve
from .units import Unit

STDLIB_DIR = Path(__file__).resolve().parent / "stdlib"


def _display_path(path: Path) -> str:
    try:
        rel = os.path.relpath(path)
        return rel if len(rel) < len(str(path)) else str(path)
    except ValueError:  # different drive on Windows
        return str(path)


class Interpreter:
    """Holds the variables and equations of one session and runs programs against them."""

    def __init__(self, base_dir=None, out: Optional[Callable[[str], None]] = None, *,
                 explain: bool = False, echo: bool = False,
                 plotter: Optional[Callable[[str, str, str, List[Tuple[float, float]]], None]] = None):
        self.base_dir = Path(base_dir).resolve() if base_dir else Path.cwd()
        self.out = out or print
        self.explain = explain  # show the rearranged formula for every solve
        self.echo = echo        # print assignments too (the shell does)
        self.plotter = plotter  # receives (title, x label, y label, points) for plot statements
        self.plots: List[Dict[str, object]] = []  # every plot drawn in this session
        self.variables: Dict[str, Value] = {}
        self.equations: Dict[str, Equation] = {}
        self.worksheets: Dict[str, S.WorksheetDef] = {}
        self._worksheet_defaults: Dict[str, Dict[str, Quantity]] = {}
        self.evaluator = Evaluator(self.equations.get)
        self.evaluator.equation_names = lambda: list(self.equations)
        self.evaluator.import_hint = self._import_hint
        self._dirs: List[Path] = [self.base_dir]
        self._loaded: Dict[Path, List[str]] = {}
        self._loading: List[Path] = []

    # ---- running -----------------------------------------------------------------------------
    def run(self, text: str, name: str = "<input>") -> None:
        source = Source(name, text)
        for stmt in parse(source):
            self.execute(stmt, source)

    def run_file(self, path) -> None:
        path = Path(path).resolve()
        text = path.read_text(encoding="utf-8-sig")  # -sig: PowerShell's Out-File adds a BOM
        self.base_dir = path.parent
        self._dirs = [path.parent]
        self.run(text, _display_path(path))

    def scope(self) -> Scope:
        return Scope(self.variables)

    def execute(self, st, source: Source) -> None:
        if isinstance(st, S.Assign):
            value = self.evaluator.eval(st.expr, self.scope())
            self.variables[st.name] = value
            if self.echo:
                self.out(f"{st.name} = {value}")
        elif isinstance(st, S.ExprStmt):
            value = self.evaluator.eval(st.expr, self.scope())
            self.variables["ans"] = value
            self.out(str(value))
        elif isinstance(st, S.Print):
            parts: List[str] = []
            for item in st.items:
                parts.append(item.value if isinstance(item, S.StringLit)
                             else str(self.evaluator.eval(item, self.scope())))
            self.out(" ".join(parts))
        elif isinstance(st, S.Plot):
            self._plot(st)
        elif isinstance(st, S.Convert):
            value = self.evaluator.eval(st.expr, self.scope())
            if not isinstance(value, Quantity):
                raise ForgeError("convert expects a scalar quantity, not a matrix or vector",
                                 st.span, title="Invalid conversion")
            result = value.to(st.unit)
            self.variables["ans"] = result
            self.out(str(result))
        elif isinstance(st, S.EqDef):
            eq = Equation(st, source)
            eq.validate(self.evaluator)
            self.equations[eq.name] = eq
        elif isinstance(st, S.WorksheetDef):
            self._define_worksheet(st)
        elif isinstance(st, S.Solve):
            self._solve(st)
        elif isinstance(st, S.Import):
            self._import(st)
        elif isinstance(st, S.Export):
            self._export(st)
        else:  # pragma: no cover
            raise TypeError(st)

    def _plot(self, st: S.Plot) -> None:
        from .desktop import plot_series

        y_value = self.evaluator.eval(st.y, self.scope())
        if not isinstance(y_value, Vector):
            raise ForgeError("plot() needs a vector of values", st.span, title="Cannot plot",
                             hint="Build one with linspace(), range(), or a vector literal like <1, 2, 3>.")
        x_name = x_value = None
        if st.x is not None:
            x_value = self.evaluator.eval(st.x, self.scope())
            if not isinstance(x_value, Vector):
                raise ForgeError("the horizontal values of plot() must be a vector", st.span,
                                 title="Cannot plot")
            x_name = st.x.name if isinstance(st.x, S.Name) else "x"
        y_name = st.y.name if isinstance(st.y, S.Name) else "y"
        x_label, y_label, points = plot_series(x_name, x_value, y_name, y_value)
        title = f"{y_label} vs {x_label}"
        self.plots.append({"title": title, "xLabel": x_label, "yLabel": y_label, "points": points})
        if self.plotter is not None:
            self.plotter(title, x_label, y_label, points)
        else:
            self.out(f"Plot: {title} ({len(points)} points)")

    def _define_worksheet(self, definition: S.WorksheetDef) -> None:
        inputs = [item for item in definition.items if isinstance(item, S.WorksheetInput)]
        outputs = [item for item in definition.items if isinstance(item, S.WorksheetOutput)]
        graphs = [item for item in definition.items if isinstance(item, S.WorksheetGraph)]
        if not inputs:
            raise ForgeError("a worksheet must declare at least one input", definition.span,
                             title="Invalid worksheet")
        if not outputs:
            raise ForgeError("a worksheet must declare at least one output", definition.span,
                             title="Invalid worksheet")
        input_names = [item.name for item in inputs]
        output_names = [item.name for item in outputs]
        if len(set(input_names)) != len(input_names):
            raise ForgeError("input names must be unique", definition.span, title="Invalid worksheet")
        if len(set(output_names)) != len(output_names):
            raise ForgeError("output names must be unique", definition.span, title="Invalid worksheet")
        duplicate_names = set(input_names) & set(output_names)
        if duplicate_names:
            name = sorted(duplicate_names)[0]
            raise ForgeError(f"'{name}' cannot be both an input and an output",
                             definition.span, title="Invalid worksheet")
        for graph in graphs:
            if graph.variable not in input_names:
                raise ForgeError(f"graph sweep '{graph.variable}' is not a worksheet input",
                                 graph.span, title="Invalid worksheet")
            if graph.output not in output_names:
                raise ForgeError(f"graph output '{graph.output}' is not a worksheet output",
                                 graph.span, title="Invalid worksheet")

        defaults: Dict[str, Quantity] = {}
        constant_scope = Scope({}, constants=True)
        for item in inputs:
            default = self.evaluator.eval(item.default, constant_scope)
            if not isinstance(default, Quantity):
                raise ForgeError(f"default for input '{item.name}' must be a scalar quantity",
                                 item.span, title="Invalid worksheet input")
            if default.is_plain and not item.unit.dim.is_dimensionless:
                default = Quantity.from_unit(default.value, item.unit)
            if default.dim != item.unit.dim:
                raise UnitError(
                    f"default for input '{item.name}' expects {item.unit.symbol() or 'dimensionless'}",
                    item.span,
                    title="Worksheet unit mismatch",
                )
            defaults[item.name] = default.to(item.unit)

        previous_definition = self.worksheets.get(definition.name)
        previous_defaults = self._worksheet_defaults.get(definition.name)
        self.worksheets[definition.name] = definition
        self._worksheet_defaults[definition.name] = defaults
        try:
            self._evaluate_worksheet(definition, defaults, samples=2)
        except ForgeError:
            if previous_definition is None or previous_defaults is None:
                del self.worksheets[definition.name]
                del self._worksheet_defaults[definition.name]
            else:
                self.worksheets[definition.name] = previous_definition
                self._worksheet_defaults[definition.name] = previous_defaults
            raise

    def worksheet_schema(self, name: str) -> Dict[str, object]:
        definition = self.worksheets.get(name)
        if definition is None:
            raise ForgeNameError(f"There is no worksheet named '{name}'",
                                 title="Unknown worksheet")
        metadata = {item.key: item.value for item in definition.items if isinstance(item, S.Meta)}
        defaults = self._worksheet_defaults[name]
        inputs = [
            {
                "name": item.name,
                "unit": item.unit.symbol(),
                "default": defaults[item.name].magnitude(item.unit),
                "description": item.doc or "",
            }
            for item in definition.items if isinstance(item, S.WorksheetInput)
        ]
        outputs = [
            {"name": item.name}
            for item in definition.items if isinstance(item, S.WorksheetOutput)
        ]
        graphs = [
            {"output": item.output, "variable": item.variable}
            for item in definition.items if isinstance(item, S.WorksheetGraph)
        ]
        return {
            "name": definition.name,
            "description": metadata.get("description", ""),
            "inputs": inputs,
            "outputs": outputs,
            "graphs": graphs,
        }

    def evaluate_worksheet(self, name: str, values: Optional[Dict[str, object]] = None) -> Dict[str, object]:
        definition = self.worksheets.get(name)
        if definition is None:
            raise ForgeNameError(f"There is no worksheet named '{name}'",
                                 title="Unknown worksheet")
        supplied = values or {}
        if not isinstance(supplied, dict):
            raise ForgeError("worksheet values must be an object", title="Invalid worksheet input")
        defaults = self._worksheet_defaults[name]
        input_items = [item for item in definition.items if isinstance(item, S.WorksheetInput)]
        known = {item.name for item in input_items}
        unexpected = set(supplied) - known
        if unexpected:
            raise ForgeError(f"unknown worksheet input '{sorted(unexpected)[0]}'",
                             title="Invalid worksheet input")
        inputs = dict(defaults)
        for item in input_items:
            if item.name not in supplied:
                continue
            raw_value = supplied[item.name]
            if isinstance(raw_value, bool):
                raise ForgeError(f"value for '{item.name}' must be a finite number",
                                 item.span, title="Invalid worksheet input")
            try:
                magnitude = float(raw_value)
            except (TypeError, ValueError):
                raise ForgeError(f"value for '{item.name}' must be a finite number",
                                 item.span, title="Invalid worksheet input") from None
            if not math.isfinite(magnitude):
                raise ForgeError(f"value for '{item.name}' must be a finite number",
                                 item.span, title="Invalid worksheet input")
            inputs[item.name] = Quantity.from_unit(magnitude, item.unit)
        return self._evaluate_worksheet(definition, inputs, samples=51)

    def _evaluate_worksheet(self, definition: S.WorksheetDef,
                            inputs: Dict[str, Quantity], samples: int) -> Dict[str, object]:
        values: Dict[str, Value] = dict(inputs)
        scope = Scope(values, constants=True)
        output_values: Dict[str, Quantity] = {}
        for item in definition.items:
            if not isinstance(item, S.WorksheetOutput):
                continue
            value = self.evaluator.eval(item.expr, scope)
            if not isinstance(value, Quantity):
                raise ForgeError(f"output '{item.name}' must be a scalar quantity",
                                 item.span, title="Invalid worksheet output")
            values[item.name] = value
            output_values[item.name] = value
        rendered_outputs = [
            {"name": item.name, "value": str(output_values[item.name])}
            for item in definition.items if isinstance(item, S.WorksheetOutput)
        ]
        rendered_graphs = []
        for graph in (item for item in definition.items if isinstance(item, S.WorksheetGraph)):
            input_item = next(item for item in definition.items
                              if isinstance(item, S.WorksheetInput) and item.name == graph.variable)
            start_value = self.evaluator.eval(graph.start, scope)
            stop_value = self.evaluator.eval(graph.stop, scope)
            if not isinstance(start_value, Quantity) or not isinstance(stop_value, Quantity):
                raise ForgeError("graph range endpoints must be scalar quantities",
                                 graph.span, title="Invalid worksheet graph")
            if start_value.dim != input_item.unit.dim or stop_value.dim != input_item.unit.dim:
                raise UnitError(
                    f"graph range for '{graph.variable}' must use {input_item.unit.symbol() or 'dimensionless'}",
                    graph.span,
                    title="Worksheet unit mismatch",
                )
            start = start_value.magnitude(input_item.unit)
            stop = stop_value.magnitude(input_item.unit)
            if not math.isfinite(start) or not math.isfinite(stop) or start == stop:
                raise ForgeError("graph range must have distinct finite endpoints",
                                 graph.span, title="Invalid worksheet graph")
            points: List[Tuple[float, float]] = []
            output_unit = None
            for index in range(samples):
                magnitude = start + (stop - start) * index / (samples - 1)
                sample_inputs = dict(inputs)
                sample_inputs[graph.variable] = Quantity.from_unit(magnitude, input_item.unit)
                sample_values: Dict[str, Value] = dict(sample_inputs)
                sample_scope = Scope(sample_values, constants=True)
                sample_output: Optional[Quantity] = None
                for item in definition.items:
                    if isinstance(item, S.WorksheetOutput):
                        sample_result = self.evaluator.eval(item.expr, sample_scope)
                        if not isinstance(sample_result, Quantity):
                            raise ForgeError(f"output '{item.name}' must be a scalar quantity",
                                             item.span, title="Invalid worksheet output")
                        sample_values[item.name] = sample_result
                        if item.name == graph.output:
                            sample_output = sample_result
                if sample_output is None:
                    raise ForgeError(f"graph output '{graph.output}' was not calculated",
                                     graph.span, title="Invalid worksheet graph")
                if output_unit is None:
                    output_unit = sample_output.unit or Unit.from_dim(sample_output.dim)
                if output_unit is not None:
                    if sample_output.dim != output_unit.dim:
                        raise UnitError(f"graph output '{graph.output}' changes dimensions",
                                        graph.span, title="Worksheet unit mismatch")
                    y_value = sample_output.magnitude(output_unit)
                else:
                    y_value = sample_output.value
                if not math.isfinite(y_value):
                    raise ForgeError("graph produced a non-finite value",
                                     graph.span, title="Invalid worksheet graph")
                points.append((magnitude, y_value))
            rendered_graphs.append({
                "output": graph.output,
                "variable": graph.variable,
                "xLabel": f"{graph.variable} ({input_item.unit.symbol()})"
                          if input_item.unit.symbol() else graph.variable,
                "yLabel": f"{graph.output} ({output_unit.symbol()})"
                          if output_unit is not None and output_unit.symbol() else graph.output,
                "points": points,
            })
        return {"name": definition.name, "inputs": {
            name: value.magnitude(next(item.unit for item in definition.items
                                       if isinstance(item, S.WorksheetInput) and item.name == name))
            for name, value in inputs.items()
        }, "outputs": rendered_outputs, "graphs": rendered_graphs}

    def _import_hint(self, name: str) -> Optional[str]:
        for d in self.search_dirs():
            if (d / f"{name}.eq").is_file():
                return f"There is an equation file for it. Add this line first:  import {name}"
        return None

    # ---- solve -------------------------------------------------------------------------------
    def get_equation(self, name: str, span) -> Equation:
        eq = self.equations.get(name)
        if eq is None:
            close = difflib.get_close_matches(name, list(self.equations), n=2, cutoff=0.5)
            hint = ("Did you mean " + " or ".join(f"'{c}'" for c in close) + "? ") if close else ""
            hint += f"Define it with 'eq {name} {{ ... }}' or bring it in with 'import {name}'."
            raise ForgeNameError(f"There is no equation named '{name}'", span, hint=hint, title="Unknown equation")
        return eq

    def _solve(self, st: S.Solve) -> None:
        eq = self.get_equation(st.eq, st.eq_span)
        givens: Dict[str, Tuple[Quantity, Optional[object]]] = {}
        for name, expr, name_span in st.givens:
            givens[name] = (self.evaluator.eval(expr, self.scope()), getattr(expr, "span", None) or name_span)
        sol = solve(eq, st.target, givens, self.evaluator, call_span=st.span, target_span=st.target_span)
        self.variables["ans"] = sol.value
        self.out(f"{st.target} = {sol.value}")
        if self.explain:
            for step in sol.steps:
                self.out(f"  rearranged: {step}")
        for note in sol.notes:
            self.out(f"  note: {note}")

    # ---- imports and exports -----------------------------------------------------------------
    def search_dirs(self) -> List[Path]:
        dirs = [self._dirs[-1], self._dirs[-1] / "formulas", self._dirs[-1] / "eq",
                self.base_dir, self.base_dir / "formulas", self.base_dir / "eq"]
        dirs += [Path(p) for p in os.environ.get("FORGE_PATH", "").split(os.pathsep) if p]
        dirs.append(STDLIB_DIR)
        seen: List[Path] = []
        for d in dirs:
            if d not in seen:
                seen.append(d)
        return seen

    def find_eq_file(self, target: str, is_path: bool, span) -> Path:
        if is_path:
            p = Path(target).expanduser()
            if not p.is_absolute():
                p = self._dirs[-1] / p
            if p.suffix == "":
                p = p.with_suffix(".eq")
            if p.is_file():
                return p
            raise ForgeImportError(f"Cannot find the file '{target}'", span, hint=f"Looked for {p}")
        for d in self.search_dirs():
            cand = d / f"{target}.eq"
            if cand.is_file():
                return cand
        available = sorted({f.stem for d in self.search_dirs() if d.is_dir() for f in d.glob("*.eq")})
        close = difflib.get_close_matches(target, available, n=2, cutoff=0.5)
        hint = ("Did you mean " + " or ".join(f"'{c}'" for c in close) + "? ") if close else ""
        hint += "Available: " + (", ".join(available) if available else "none")
        raise ForgeImportError(f"Cannot find an equation file named '{target}.eq'", span, hint=hint)

    def load_eq_file(self, path: Path, span=None) -> List[str]:
        """Parse an .eq file and register its equations.  Returns the equation names it defines."""
        path = path.resolve()
        if path in self._loaded:
            return self._loaded[path]
        if path in self._loading:
            raise ForgeImportError(f"{path.name} imports itself through a cycle", span)
        source = Source(_display_path(path), path.read_text(encoding="utf-8-sig"))
        stmts = parse(source)
        names: List[str] = []
        self._loading.append(path)
        self._dirs.append(path.parent)
        try:
            for st in stmts:
                if isinstance(st, S.EqDef):
                    self.execute(st, source)
                    names.append(st.name)
                elif isinstance(st, S.Import):
                    self.execute(st, source)
                else:
                    raise ForgeImportError("An .eq file can only contain 'eq' definitions and imports",
                                           st.span, hint="Move other statements into a .forge program.")
        finally:
            self._loading.pop()
            self._dirs.pop()
        self._loaded[path] = names
        return names

    def _import(self, st: S.Import) -> None:
        path = self.find_eq_file(st.target, st.is_path, st.span)
        names = self.load_eq_file(path, st.span)
        if not st.is_path and st.target not in names:
            raise ForgeImportError(
                f"{path.name} does not define an equation named '{st.target}'", st.span,
                hint=f"It defines: {', '.join(names) or 'nothing'}")

    def _export(self, st: S.Export) -> None:
        eq = self.get_equation(st.name, st.span)
        path = self.base_dir / f"{eq.name}.eq"
        path.write_text(format_equation(eq), encoding="utf-8")
        self.out(f"Exported {eq.name} -> {_display_path(path)}")
