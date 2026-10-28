"""Interactive shell (feature 35): `forge shell`."""
from __future__ import annotations

from typing import Callable, List

from .constants import CONSTANTS, PACKS
from .docgen import document
from .errors import ForgeError
from .interpreter import Interpreter
from .lexer import KEYWORDS
from .units import units_by_kind

BANNER = """F²ORGE shell. Type an expression, an assignment, or an eq block. :help for commands."""

HELP = """\
  :help              this text
  :vars              list variables
  :eqs               list equations and their inputs / outputs
  :doc NAME          show generated documentation for an equation
  :units [text]      list units (optionally only those matching text)
  :constants         list built-in constants
  :explain on|off    show the rearranged formula for each solve
  :load FILE         run a .forge file in this session
  :quit              leave (Ctrl-D also works)

  Examples:   convert 10 ft -> m        solve Force for a { F = 100 N, m = 50 kg }
              eq Force { F = m * a }    Force(m = 2 kg, a = 3 m/s^2)
              ans                       the last result"""


def is_complete(lines: List[str]) -> bool:
    """False while a bracket is open or the last line ends in an operator (keep reading)."""
    depth = 0
    in_string = False
    last = ""
    for line in lines:
        i = 0
        while i < len(line):
            ch = line[i]
            if in_string:
                if ch == "\\":
                    i += 1
                elif ch == '"':
                    in_string = False
            elif ch == '"':
                in_string = True
            elif ch == "#" or line.startswith("//", i):
                break
            elif ch in "({":
                depth += 1
            elif ch in ")}":
                depth -= 1
            if not in_string and not ch.isspace():
                last = ch
            i += 1
    if in_string or depth > 0:
        return False
    if last == "":  # blank input is complete (note: "" in "=+-" would be True in Python)
        return True
    return last not in "=+-*/^,(" and not (lines and lines[-1].rstrip().endswith("->"))


def _command(interp: Interpreter, text: str, out: Callable[[str], None]) -> bool:
    """Handle a ':command'.  Returns False to quit."""
    parts = text[1:].split()
    cmd, rest = (parts[0].lower() if parts else ""), parts[1:]
    if cmd in ("q", "quit", "exit"):
        return False
    if cmd in ("h", "help", "?"):
        out(HELP)
    elif cmd == "vars":
        for name, value in interp.variables.items():
            out(f"{name} = {value}")
        if not interp.variables:
            out("(no variables yet)")
    elif cmd == "eqs":
        for eq in interp.equations.values():
            io = f"{', '.join(eq.inputs)} -> {', '.join(eq.outputs)}" if eq.callable else f"variables: {', '.join(eq.variables)}"
            out(f"{eq.name}: {io}")
        if not interp.equations:
            out("(no equations yet; try: import Force)")
    elif cmd == "doc" and rest:
        eq = interp.equations.get(rest[0])
        out(document(eq) if eq else f"No equation named '{rest[0]}'. Use :eqs to list them.")
    elif cmd == "units":
        needle = rest[0].lower() if rest else ""
        for kind, defs in sorted(units_by_kind().items()):
            names = [u.name for u in defs if needle in u.name.lower() or needle in kind]
            if names:
                out(f"{kind}: {' '.join(names)}")
        out("(SI prefixes such as k, m, u, M, G also work on most units: km, mm, MPa)")
    elif cmd == "constants":
        for pack, names in PACKS.items():
            out(f"{pack}: " + ", ".join(f"{n} = {CONSTANTS[n]}" for n in names))
    elif cmd == "explain" and rest:
        interp.explain = rest[0].lower() in ("on", "true", "1", "yes")
        out(f"explain is {'on' if interp.explain else 'off'}")
    elif cmd == "load" and rest:
        interp.run_file(" ".join(rest))
    else:
        out("Unknown command. :help lists them.")
    return True


def run_shell(interp: Interpreter, input_fn: Callable[[str], str] = input,
              out: Callable[[str], None] = print, color: bool = False, banner: bool = True) -> None:
    interp.echo = True
    interp.out = out
    if banner:
        out(BANNER)
    buf: List[str] = []
    while True:
        try:
            line = input_fn("forge> " if not buf else "  ... ")
        except EOFError:
            break
        except KeyboardInterrupt:
            buf = []
            out("")
            continue
        if not buf and line.strip().startswith(":"):
            try:
                if not _command(interp, line.strip(), out):
                    break
            except ForgeError as err:
                out(err.format(color))
            except OSError as err:
                out(f"error: {err}")
            continue
        buf.append(line)
        if not is_complete(buf):
            continue
        text = "\n".join(buf)
        buf = []
        if not text.strip():
            continue
        try:
            interp.run(text, "<shell>")
        except ForgeError as err:
            out(err.format(color))
        except (OSError, RecursionError) as err:
            out(f"error: {err}")
