"""Statement execution: variables, equations, imports/exports, solve, convert, print."""
from __future__ import annotations

import difflib
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from . import syntax as S
from .equation import Equation
from .errors import ForgeError, ForgeImportError, ForgeNameError, Source
from .evaluator import Evaluator, Scope
from .parser import parse
from .printer import format_equation
from .quantity import Quantity
from .solver import solve

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
                 explain: bool = False, echo: bool = False):
        self.base_dir = Path(base_dir).resolve() if base_dir else Path.cwd()
        self.out = out or print
        self.explain = explain  # show the rearranged formula for every solve
        self.echo = echo        # print assignments too (the shell does)
        self.variables: Dict[str, Quantity] = {}
        self.equations: Dict[str, Equation] = {}
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
        elif isinstance(st, S.Convert):
            result = self.evaluator.eval(st.expr, self.scope()).to(st.unit)
            self.variables["ans"] = result
            self.out(str(result))
        elif isinstance(st, S.EqDef):
            eq = Equation(st, source)
            eq.validate(self.evaluator)
            self.equations[eq.name] = eq
        elif isinstance(st, S.Solve):
            self._solve(st)
        elif isinstance(st, S.Import):
            self._import(st)
        elif isinstance(st, S.Export):
            self._export(st)
        else:  # pragma: no cover
            raise TypeError(st)

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
