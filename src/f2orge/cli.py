"""Command line (feature 34):  forge run main.forge  |  forge shell  |  forge doc Force  |  ..."""
from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__, units
from .calculator import render_calculator, run_terminal_calculator
from .docgen import document_all
from .errors import ForgeError
from .interpreter import Interpreter
from .plot import render_interactive_html, render_svg, save_graph
from .quantity import Quantity
from .repl import run_shell
from .units import Unit, units_by_kind


def _color(stream) -> bool:
    if os.environ.get("NO_COLOR") or not hasattr(stream, "isatty") or not stream.isatty():
        return False
    if os.name == "nt":
        os.system("")  # switches the Windows console to ANSI escape handling
    return True


def _setup_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _report(err: ForgeError) -> None:
    print(err.format(_color(sys.stderr)), file=sys.stderr)


def cmd_run(args) -> int:
    path = Path(args.file)
    if not path.is_file():
        print(f"error: cannot find {path}", file=sys.stderr)
        return 2
    interp = Interpreter(base_dir=path.resolve().parent, explain=args.explain)
    try:
        interp.run_file(path)
    except ForgeError as err:
        _report(err)
        return 1
    if interp.plots:
        _write_plots(interp.plots, path, args.plot_format)
    return 0


def _write_plots(plots, source: Path, output_format: str) -> None:
    """Write one graph file per plot statement next to the program."""
    from .plot import render_interactive_html, render_svg, save_graph

    for index, plot in enumerate(plots, start=1):
        title, x_label, y_label = plot["title"], plot["xLabel"], plot["yLabel"]
        series = [("", plot["points"])]
        suffix = f"-{index}" if len(plots) > 1 else ""
        output = source.with_name(f"{source.stem}-plot{suffix}.{output_format}")
        try:
            if output_format == "html":
                page = render_interactive_html(render_svg(title, x_label, y_label, series), title, [""])
                output.write_text(page, encoding="utf-8")
            else:
                save_graph(str(output), output_format, title, x_label, y_label, series)
        except ForgeError as err:
            _report(err)
            continue
        except OSError as err:
            print(f"error: cannot write plot: {err}", file=sys.stderr)
            continue
        print(f"Wrote {output}")


def cmd_shell(args) -> int:
    run_shell(Interpreter(base_dir=Path.cwd(), explain=args.explain), color=_color(sys.stdout))
    return 0


def cmd_check(args) -> int:
    """Parse files and validate every equation's dimensions without running statements."""
    from . import syntax as S
    from .errors import Source
    from .parser import parse
    failed = 0
    for name in args.files:
        path = Path(name)
        try:
            interp = Interpreter(base_dir=path.resolve().parent)
            if path.suffix == ".eq":
                count = len(interp.load_eq_file(path))
            else:
                source = Source(str(path), path.read_text(encoding="utf-8-sig"))
                stmts = parse(source)
                count = 0
                interp._dirs = [path.resolve().parent]
                for st in stmts:
                    if isinstance(st, (S.EqDef, S.Import)):
                        interp.execute(st, source)
                        count += isinstance(st, S.EqDef)
            print(f"ok: {name} ({count} equation{'s' if count != 1 else ''} checked)")
        except ForgeError as err:
            failed += 1
            _report(err)
        except OSError as err:
            failed += 1
            print(f"error: {err}", file=sys.stderr)
    return 1 if failed else 0


def cmd_doc(args) -> int:
    interp = Interpreter(base_dir=Path.cwd())
    try:
        target = args.target
        is_path = target.endswith(".eq") or "/" in target or "\\" in target
        path = interp.find_eq_file(target, is_path, None)
        names = interp.load_eq_file(path)
        text = document_all(interp.equations[n] for n in names)
    except ForgeError as err:
        _report(err)
        return 1
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        sys.stdout.write(text)
    return 0


def cmd_graph(args) -> int:
    from . import syntax as S
    from .errors import ForgeError, Source
    from .parser import parse

    interp = Interpreter(base_dir=Path.cwd())
    target = args.target
    is_path = target.endswith(".eq") or "/" in target or "\\" in target
    try:
        path = interp.find_eq_file(target, is_path, None)
        names = interp.load_eq_file(path)
        if is_path:
            if len(names) != 1:
                raise ForgeError(
                    f"'{target}' defines {len(names)} equations; graph one equation by name",
                    title="Cannot graph",
                )
            eq_name = names[0]
        else:
            if target not in names:
                raise ForgeError(
                    f"'{path.name}' does not define an equation named '{target}'",
                    title="Cannot graph",
                )
            eq_name = target
        eq = interp.equations[eq_name]
        if not eq.callable:
            raise ForgeError(
                f"{eq.name} does not define callable outputs",
                title="Cannot graph",
                hint="Graphing requires an equation with an output formula.",
            )
        if args.vary not in eq.inputs:
            raise ForgeError(
                f"'{args.vary}' is not an input of {eq.name}",
                title="Cannot graph",
                hint=f"Inputs: {', '.join(eq.inputs)}",
            )
        declaration = eq.decls.get(args.vary)
        if declaration is None:
            raise ForgeError(
                f"the varying input '{args.vary}' needs a declared unit",
                title="Cannot graph",
                hint=f"Add a declaration such as '{args.vary} : m' to {eq.name}.",
            )
        if args.samples < 2 or args.samples > 5001:
            raise ForgeError(
                "the sample count must be between 2 and 5001",
                title="Invalid graph range",
            )
        if not math.isfinite(args.start) or not math.isfinite(args.stop):
            raise ForgeError("range endpoints must be finite numbers", title="Invalid graph range")
        if not math.isfinite(args.stop - args.start):
            raise ForgeError("range is too wide to graph", title="Invalid graph range")

        def parse_graph_input(raw):
            if "=" not in raw:
                raise ForgeError(
                    f"'{raw}' must have the form name=value",
                    title="Invalid graph input",
                    hint="For example: --set 'm=150 kg'",
                )
            input_name, expression = raw.split("=", 1)
            input_name = input_name.strip()
            source = Source("<graph input>", f"{input_name} = {expression.strip()}")
            statements = parse(source)
            if len(statements) != 1 or not isinstance(statements[0], S.Assign):
                raise ForgeError(f"invalid value for input '{input_name}'", title="Invalid graph input")
            statement = statements[0]
            if statement.name != input_name or not input_name:
                raise ForgeError(
                    f"'{raw}' is malformed",
                    title="Invalid graph input",
                )
            quantity = interp.evaluator.eval(statement.expr, interp.scope())
            return input_name, quantity, statement.expr.span

        fixed = {}
        for raw in args.values:
            input_name, quantity, span = parse_graph_input(raw)
            if input_name in fixed:
                raise ForgeError(
                    f"input '{input_name}' is specified more than once",
                    title="Invalid graph input",
                )
            if input_name == args.vary:
                raise ForgeError(
                    f"the varying input '{args.vary}' cannot also be fixed with --set",
                    title="Invalid graph input",
                )
            fixed[input_name] = (quantity, span)

        curve_values = []
        curve_name = None
        for raw in args.curves:
            input_name, quantity, span = parse_graph_input(raw)
            if input_name == args.vary:
                raise ForgeError(
                    f"the varying input '{args.vary}' cannot also be used for --curve",
                    title="Invalid graph input",
                )
            if input_name not in eq.inputs:
                raise ForgeError(
                    f"'{input_name}' is not an input of {eq.name}",
                    title="Invalid graph input",
                    hint=f"Inputs: {', '.join(eq.inputs)}",
                )
            if input_name in fixed:
                raise ForgeError(
                    f"input '{input_name}' cannot be both fixed with --set and varied with --curve",
                    title="Invalid graph input",
                )
            if curve_name is not None and input_name != curve_name:
                raise ForgeError(
                    "all --curve values must vary the same input",
                    title="Invalid graph input",
                    hint=f"Use repeated values for '{curve_name}', for example --curve '{curve_name}=50 kg'.",
                )
            curve_name = input_name
            curve_values.append((quantity, span))
        if len(curve_values) > 20:
            raise ForgeError(
                "a graph can contain at most 20 curves",
                title="Invalid graph input",
            )

        output_name = args.output_name or eq.primary
        if output_name not in eq.outputs:
            raise ForgeError(
                f"'{output_name}' is not an output of {eq.name}",
                title="Cannot graph",
                hint=f"Outputs: {', '.join(eq.outputs)}",
            )

        curves = curve_values or [(None, None)]
        all_points: List[Tuple[float, float]] = []
        named_series = []
        x_unit = declaration.unit
        y_unit = eq.decls[output_name].unit if output_name in eq.decls else None
        for curve_value, curve_span in curves:
            points: List[Tuple[float, float]] = []
            values = dict(fixed)
            curve_label = ""
            if curve_value is not None:
                values[curve_name] = (curve_value, curve_span)
                curve_label = f"{curve_name} = {curve_value}"
            for index in range(args.samples):
                magnitude = args.start + (args.stop - args.start) * index / (args.samples - 1)
                call_values = dict(values)
                call_values[args.vary] = (Quantity.from_unit(magnitude, x_unit), None)
                result = eq.call(interp.evaluator, call_values, None)[output_name]
                if y_unit is None:
                    y_unit = Unit.from_dim(result.dim)
                ordinate = result.magnitude(y_unit)
                if not math.isfinite(ordinate):
                    raise ForgeError("the equation produced a non-finite graph value", title="Math error")
                points.append((magnitude, ordinate))
            all_points.extend(points)
            named_series.append((curve_label, points))

        if not math.isfinite(max(y for _, y in all_points) - min(y for _, y in all_points)):
            raise ForgeError("output range is too wide to graph", title="Invalid graph range")

        x_symbol = x_unit.symbol()
        y_symbol = y_unit.symbol() if y_unit is not None else ""
        x_name = declaration.doc or args.vary
        output_decl = eq.decls.get(output_name)
        y_name = output_decl.doc if output_decl and output_decl.doc else output_name
        x_name = x_name[:1].upper() + x_name[1:]
        y_name = y_name[:1].upper() + y_name[1:]
        x_label = f"{x_name} ({x_symbol})" if x_symbol else x_name
        y_label = f"{y_name} ({y_symbol})" if y_symbol else y_name
        title = f"{eq.name}: {output_name} vs {args.vary}"
        if args.interactive and args.window:
            raise ForgeError("--interactive cannot be combined with --window", title="Invalid graph options")
        if args.interactive:
            svg = render_svg(title, x_label, y_label, named_series)
            page = render_interactive_html(
                svg, title,
                [label for label, _ in named_series],
            )
            output = Path(args.output) if args.output else Path(f"{eq.name}-{args.vary}.html")
            output.write_text(page, encoding="utf-8")
        elif args.window:
            svg = render_svg(title, x_label, y_label, named_series)
            page = render_interactive_html(svg, title, [label for label, _ in named_series])
            from .desktop_tools import show_html_window

            show_html_window(title, page)
            print("Opened plot window")
            return 0
        else:
            output = Path(args.output) if args.output else Path(f"{eq.name}-{args.vary}.{args.format or 'svg'}")
            output_format = args.format or output.suffix.lower().lstrip(".")
            if output_format not in ("svg", "png", "pdf"):
                raise ForgeError(
                    f"unsupported graph format '{output_format}'",
                    title="Invalid graph format",
                    hint="Choose SVG, PNG, or PDF.",
                )
            save_graph(str(output), output_format, title, x_label, y_label, named_series)
    except ForgeError as err:
        _report(err)
        return 1
    except OSError as err:
        print(f"error: cannot write graph: {err}", file=sys.stderr)
        return 1
    print(f"Wrote {output}")
    return 0


def cmd_plot(args) -> int:
    from .desktop import DesktopSession
    from .plot import render_interactive_html, render_svg

    path = Path(args.file)
    if not path.is_file():
        print(f"error: cannot find {path}", file=sys.stderr)
        return 2
    session = DesktopSession(base_dir=path.resolve().parent)
    try:
        source = path.read_text(encoding="utf-8-sig")
    except OSError as err:
        print(f"error: cannot read {path}: {err}", file=sys.stderr)
        return 2
    output, success = session.execute(source, path)
    if not success:
        print(output, file=sys.stderr)
        return 1
    command = f"plot({args.x}, {args.y})" if args.x else f"plot({args.y})"
    try:
        x_label, y_label, points = session.plot_data(command)
        title = f"{y_label} vs {x_label}"
        svg = render_svg(title, x_label, y_label, [("", points)])
        page = render_interactive_html(svg, title, [""])
        if args.output:
            Path(args.output).write_text(page, encoding="utf-8")
            print(f"Wrote {args.output}")
        else:
            from .desktop_tools import show_html_window

            show_html_window(title, page)
            print("Opened plot window")
    except ForgeError as err:
        _report(err)
        return 1
    except OSError as err:
        print(f"error: cannot create plot: {err}", file=sys.stderr)
        return 1
    return 0


def cmd_calc(args) -> int:
    interp = Interpreter(base_dir=Path.cwd())
    target = args.target
    is_path = target.endswith(".eq") or "/" in target or "\\" in target
    try:
        path = interp.find_eq_file(target, is_path, None)
        names = interp.load_eq_file(path)
        if is_path:
            if len(names) != 1:
                raise ForgeError(
                    f"'{target}' defines {len(names)} equations; generate a calculator by equation name",
                    title="Calculator unavailable",
                )
            eq_name = names[0]
        else:
            if target not in names:
                raise ForgeError(
                    f"'{path.name}' does not define an equation named '{target}'",
                    title="Calculator unavailable",
                )
            eq_name = target
        if args.terminal and (args.desktop or args.executable):
            raise ForgeError(
                "--terminal cannot be combined with --desktop or --executable",
                title="Invalid calculator options",
            )
        if args.terminal:
            if args.output:
                raise ForgeError("--terminal cannot be combined with --output",
                                 title="Invalid calculator options")
            eq = interp.equations[eq_name]
            if not eq.callable:
                raise ForgeError(f"{eq.name} does not define callable outputs",
                                 title="Calculator unavailable")
            run_terminal_calculator(interp, eq_name)
            return 0
        if args.desktop and args.output:
            raise ForgeError("--desktop cannot be combined with --output",
                             title="Invalid calculator options")
        page = render_calculator(interp, eq_name)
        if args.desktop and args.executable:
            raise ForgeError("--desktop cannot be combined with --executable",
                             title="Invalid calculator options")
        if args.desktop:
            from .desktop_tools import show_html_window

            show_html_window(f"{eq_name} — F²ORGE Calculator", page)
            return 0
        if args.executable:
            from .desktop_tools import build_calculator_executable

            output = Path(args.output) if args.output else Path(f"{eq_name}-calculator.exe")
            build_calculator_executable(page, output, eq_name)
        else:
            output = Path(args.output) if args.output else Path(f"{eq_name}-calculator.html")
            output.write_text(page, encoding="utf-8")
    except ForgeError as err:
        _report(err)
        return 1
    except OSError as err:
        print(f"error: cannot write calculator: {err}", file=sys.stderr)
        return 1
    print(f"Wrote {output}")
    return 0


def cmd_trace(args) -> int:
    """Run a program statement by statement, showing each line and what it changed."""
    from .debug import trace_of

    path = Path(args.file)
    if not path.is_file():
        print(f"error: cannot find {path}", file=sys.stderr)
        return 2
    try:
        frames = trace_of(path.read_text(encoding="utf-8-sig"), str(path), base_dir=path.parent)
    except ForgeError as err:
        _report(err)
        return 1
    for frame in frames:
        if args.kind and frame.kind != args.kind:
            continue
        print(f"{frame.line:>4}  {frame.kind:<11} {frame.source.strip()}")
    print(f"{len(frames)} statements ran")
    return 0


def cmd_profile(args) -> int:
    """Run a program and report the time each source line took."""
    from .debug import profile

    path = Path(args.file)
    if not path.is_file():
        print(f"error: cannot find {path}", file=sys.stderr)
        return 2
    result = profile(path.read_text(encoding="utf-8-sig"), str(path), base_dir=path.parent,
                     runs=args.runs)
    print(result.report())
    if result.error is not None:
        _report(result.error)
        return 1
    return 0


def cmd_ide(_args) -> int:
    from .web_ide import serve_desktop_ide

    try:
        serve_desktop_ide()
    except ForgeError as err:
        _report(err)
        return 1
    return 0


def cmd_transpile(args) -> int:
    from .transpile import transpile

    path = Path(args.file)
    try:
        generated = transpile(path.read_text(encoding="utf-8-sig"), args.target, str(path))
        if args.output and Path(args.output).suffix.lower() == ".8xp":
            from .ti84 import write_8xp

            write_8xp(args.output, generated, path.stem)
            print(f"Wrote {args.output} (tokenized TI-84 program)")
        elif args.output:
            Path(args.output).write_text(generated, encoding="utf-8")
            print(f"Wrote {args.output}")
        else:
            sys.stdout.write(generated)
    except ForgeError as err:
        _report(err)
        return 1
    except OSError as err:
        print(f"error: cannot transpile {path}: {err}", file=sys.stderr)
        return 1
    return 0


def cmd_browser(args) -> int:
    from .web_ide import serve_browser_ide

    try:
        serve_browser_ide(port=args.port, open_browser=not args.no_open)
    except OSError as err:
        print(f"error: cannot start browser IDE: {err}", file=sys.stderr)
        return 1
    return 0


def cmd_units(args) -> int:
    needle = (args.filter or "").lower()
    for kind, defs in sorted(units_by_kind().items()):
        names = [u.name for u in defs if needle in u.name.lower() or needle in kind]
        if names:
            print(f"{kind:12s} {' '.join(names)}")
    print("\nSI prefixes (k, M, G, m, u, n, ...) work on most units: km, mm, MPa, kN, uF.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="forge", description="F²ORGE: a unit-safe language for engineering equations.")
    p.add_argument("--version", action="version", version=f"F²ORGE {__version__}")
    p.add_argument("--ascii", action="store_true", help="print m/s^2 instead of m/s² (for limited terminals)")
    sub = p.add_subparsers(dest="command")

    r = sub.add_parser("run", help="run a .forge program")
    r.add_argument("file")
    r.add_argument("--explain", action="store_true", help="show how each solve was rearranged")
    r.add_argument("--plot-format", choices=("svg", "png", "pdf", "html"), default="svg",
                   help="format for graphs drawn by plot statements (default: svg)")
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("shell", help="interactive shell")
    s.add_argument("--explain", action="store_true")
    s.set_defaults(func=cmd_shell)

    c = sub.add_parser("check", help="parse files and check the units of every equation")
    c.add_argument("files", nargs="+")
    c.set_defaults(func=cmd_check)

    d = sub.add_parser("doc", help="generate Markdown documentation for an equation or .eq file")
    d.add_argument("target", help="an equation name (Force), or a path to an .eq file")
    d.add_argument("-o", "--output", help="write to this file instead of the terminal")
    d.set_defaults(func=cmd_doc)

    g = sub.add_parser("graph", help="sample an equation and export an SVG graph")
    g.add_argument("target", help="an equation name (Force), or a single-equation .eq file")
    g.add_argument("--vary", required=True, help="input variable to sweep")
    g.add_argument("--from", dest="start", type=float, required=True, help="starting value in the declared input unit")
    g.add_argument("--to", dest="stop", type=float, required=True, help="ending value in the declared input unit")
    g.add_argument("--set", dest="values", action="append", default=[], metavar="NAME=VALUE",
                   help="fixed equation input, e.g. --set 'm=150 kg' (repeat as needed)")
    g.add_argument("--curve", dest="curves", action="append", default=[], metavar="NAME=VALUE",
                   help="vary another input for multiple curves, e.g. --curve 'm=50 kg' (repeat)")
    g.add_argument("--samples", type=int, default=101, help="number of samples (2-5001; default: 101)")
    g.add_argument("--output-name", help="output variable to plot (defaults to the primary output)")
    g.add_argument("--interactive", action="store_true", help="write a standalone interactive HTML graph")
    g.add_argument("--window", action="store_true", help="open an interactive native plot window")
    g.add_argument("--format", choices=("svg", "png", "pdf"),
                   help="static export format (inferred from -o when omitted)")
    g.add_argument("-o", "--output", help="output filename (defaults to Equation-variable.svg or .html)")
    g.set_defaults(func=cmd_graph)

    plot = sub.add_parser("plot", help="open an interactive plot of vectors from a F²ORGE program")
    plot.add_argument("file", help="F²ORGE source file that creates vector variables")
    plot.add_argument("y", help="vector to plot on the vertical axis")
    plot.add_argument("--x", help="vector to use for the horizontal axis (defaults to sample index)")
    plot.add_argument("-o", "--output", help="write a standalone interactive HTML plot instead")
    plot.set_defaults(func=cmd_plot)

    c = sub.add_parser("calc", help="generate a standalone offline HTML calculator")
    c.add_argument("target", help="an equation name (Force), or a single-equation .eq file")
    c.add_argument("-o", "--output", help="HTML filename (defaults to Equation-calculator.html)")
    c.add_argument("--terminal", action="store_true",
                   help="run an interactive terminal calculator instead of writing HTML")
    c.add_argument("--desktop", action="store_true", help="open a native desktop calculator window")
    c.add_argument("--executable", action="store_true",
                   help="build a standalone one-file Windows calculator app (requires PyInstaller)")
    c.set_defaults(func=cmd_calc)

    ide = sub.add_parser("ide", help="launch the offline desktop IDE",
                         description="Launch the offline IDE in an embedded webview.")
    ide.set_defaults(func=cmd_ide)

    tr = sub.add_parser("trace", help="show every statement a program runs")
    tr.add_argument("file")
    tr.add_argument("--kind", help="only show one kind of statement, such as 'assignment'")
    tr.set_defaults(func=cmd_trace)

    pr = sub.add_parser("profile", help="report the time each source line takes")
    pr.add_argument("file")
    pr.add_argument("--runs", type=int, default=1, help="repeat the program this many times")
    pr.set_defaults(func=cmd_profile)

    transpile = sub.add_parser(
                           "transpile", help="convert a F²ORGE program to Python, C++, MicroPython, or TI-84 BASIC"
    )
    transpile.add_argument("file", help="F²ORGE source file")
    transpile.add_argument(
                           "--target", required=True,
                           choices=(
                               "python",
                               "micropython",
                               "micro-py",
                               "micro_py",
                               "cpp",
                               "c++",
                               "ti-basic",
                               "ti84",
                               "ti-84",
                               "ti84-basic",
                               "ti-84-basic",
                           ),
                           help="target language")
    transpile.add_argument("-o", "--output",
                           help="write generated code to a file; a .8xp name writes a tokenized "
                                "TI-84 program instead of readable BASIC")
    transpile.set_defaults(func=cmd_transpile)

    browser = sub.add_parser(
        "browser", aliases=["web"], help="launch the local browser IDE",
        description="Launch the browser IDE on loopback. No cloud service or external assets are used.",
    )
    browser.add_argument("--port", type=int, default=8765, help="local port (default: 8765)")
    browser.add_argument("--no-open", action="store_true", help="do not open a browser automatically")
    browser.set_defaults(func=cmd_browser)

    u = sub.add_parser("units", help="list the built-in units")
    u.add_argument("filter", nargs="?")
    u.set_defaults(func=cmd_units)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    _setup_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    units.set_ascii(args.ascii)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
