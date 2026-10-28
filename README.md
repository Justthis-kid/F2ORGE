# F²ORGE (Formula Forge)

A unit-safe engineering programming language where reusable equations become solvers, documentation,
and portable graphs (interactive calculators are next). Everything is local files: no cloud, no
accounts, no database, and **no dependencies beyond Python's standard library**.

```
eq Force {
    F = m * a
}

solve Force for a {
    F = 100 N
    m = 50 kg
}
# a = 2 m/s²

10 kg + 5 m
# error: Unit mismatch
#  --> main.forge:12:1
#    | 10 kg + 5 m
#    | ^^^^^^^^^^^ cannot add mass (kg) and length (m)
```

## Instruction manual: install, launch, and use F²ORGE

F²ORGE requires Python 3.9 or newer. Open a terminal in the extracted project folder (the folder
containing `pyproject.toml`) and follow the instructions for your operating system. The interpreter
and graph exporter use only Python's standard library; the optional `.[dev]` install also installs
pytest for running the tests.

### 1. Install

**Windows (PowerShell):**

```powershell
cd path\to\f2orge
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

If PowerShell says script execution is disabled when activating, open Command Prompt and run:

```bat
cd path\to\f2orge
.venv\Scripts\activate.bat
python -m pip install -e .
```

**macOS / Linux:**

```bash
cd /path/to/f2orge
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

To run the tests too, install the development extra instead with `python -m pip install -e ".[dev]"`.
Activate the virtual environment again whenever you open a new terminal.

### 2. Launch F²ORGE

Run a program, start the interactive shell, or ask for help:

```text
forge run examples/force.forge
forge shell
forge --help
```

On Windows, backslashes in file paths work too (for example `forge run examples\force.forge`).
If your system already uses the `forge` command (for example, Foundry), use `f2forge` in its place
or launch F²ORGE as a Python module:

```text
f2forge run examples/force.forge
python -m f2orge run examples/force.forge
```

### 3. Use the interactive shell

Start it with `forge shell`, enter one expression or statement per line, then type `:quit` to exit.
For example:

```text
forge> 150 kg * 9.81 m/s^2
1471.5 N
forge> convert 10 ft -> m
3.048 m
forge> :help
forge> :quit
```

In the shell, `:help` lists commands including `:vars`, `:eqs`, `:doc NAME`, `:units`, and
`:constants`. Use `:explain on` to show the rearranged formula when solving.

### 4. Write and run a program

Create a text file named `main.forge` in your project folder using any text editor, then add:

```forge
eq Force {
    m : kg
    a : m/s^2
    F : N
    F = m * a
}

force = Force(m = 150 kg, a = 9.81 m/s^2)
force

solve Force for a {
    F = 100 N
    m = 50 kg
}

convert 10 ft -> m
```

Run it from the project folder:

```text
forge run main.forge
```

F²ORGE prints the calculated force, the solved acceleration, and the converted length. If a
calculation combines incompatible units, the command prints a source location and a helpful error.
Programs use `.forge` files; reusable equation definitions can also be saved as `.eq` files.

### 5. Import equations and create documentation

Import a standard equation by name, or a project equation by relative path:

```forge
import Force
solve Force for a {
    F = 100 N
    m = 50 kg
}
```

Run the program containing this snippet with `forge run main.forge`. To see available standard
equations, browse `src/f2orge/stdlib/`. Generate equation documentation or check an equation file:

```text
forge doc Lift
forge doc Lift -o Lift.md
forge check examples/formulas/Drag.eq
```

### 6. Export a graph

Graph a callable equation by sweeping one declared input. Give its range in that input's unit and
provide other required inputs with `--set`:

```text
forge graph Force --vary a --from 0 --to 20 --set "m=150 kg" -o force.svg
```

Open `force.svg` in a browser. Use `--samples 201` to choose the number of sample points,
`--output-name F` to choose an output, or repeat `--curve` to compare values of one additional input:

```text
forge graph Force --vary a --from 0 --to 20 --curve "m=50 kg" --curve "m=100 kg" -o comparison.svg
```

The swept input needs a unit declaration in its equation. Multiple curves must vary the same
additional input; up to 20 curves are supported. Axis labels use equation documentation when present.
The SVG is self-contained and does not require a plotting package or desktop GUI.

### 7. VS Code and tests

For syntax highlighting, follow [the VS Code extension instructions](vscode-forge/README.md). To run
the test suite after installing the development extra:

```text
python -m pytest -q
```

The same F²ORGE commands are available in the VS Code terminal on Windows, macOS, and Linux.

### Quick command reference

```text
forge run FILE.forge [--explain]     Run a program
forge shell                          Start the interactive shell
forge check FILE...                  Parse and unit-check equation files
forge doc EQUATION [-o FILE.md]      Generate equation documentation
forge graph EQUATION ...             Export an equation graph as SVG
forge units [FILTER]                 List built-in units
forge --version                      Print the installed version
```

## What is implemented (v1 core)

| # | Feature | Status |
|---|---|---|
| 1, 2 | Variables, built-in units (length, mass, time, force, energy, power, pressure, temperature, electrical, ...) | done |
| 3 | `convert 10 ft -> m` | done |
| 4 | Dimensional analysis: `kg*m/s²` is shown as `N` | done |
| 5 | Unit safety checking, with expected / found in the message | done |
| 6, 7 | `+ - * / ^`, `sin cos tan ln log sqrt` (plus a few more) | done |
| 8, 11, 12, 13 | `eq` blocks, auto-detected inputs and outputs, calls, metadata | done |
| 9, 10, 39, 40 | `import`, `export`, `.eq` files, project imports | done |
| 14 | Documentation generation (`forge doc`) | done |
| 15 | Equation packages: a small standard library (`Force`, `Bernoulli`, `DeltaV`, ...) | started |
| 16, 17, 18 | `solve ... for`, automatic rearrangement, missing-information errors | done |
| 32, 33 | Constants library and engineering packs (`pi e g G R muEarth speedOfLight ...`) | done |
| 34, 35 | `forge run`, `forge shell` | done |
| 36 | VS Code syntax highlighting | done |
| 37 | Located, explanatory errors | done |
| 38 | Local-first | done |
| 19-31 | SVG equation graphs, variable sweeps and multiple curves (initial implementation); auto-generated calculators, live updates, matrices and vectors | in progress |
| 41-45 | Domain objects, worksheets, marketplace, browser IDE, plot windows | later |

The full language is described in [docs/language.md](docs/language.md).

## How it works

```
source text -> lexer -> parser -> AST -> evaluator <- Quantity (value + dimension + display unit)
                                    |-> Equation (inputs/outputs, dependency order, dimension check)
                                    |-> solver (rearrange -> chain -> numeric)
                                    |-> interpreter (imports, exports, solve, convert)
```

* **Dimensions** are exponent vectors over the seven SI base quantities, held as exact fractions.
  Conversion, unit checking and naming (`N`, `J`, `Pa`) are all that one mechanism.
* **Quantities** store SI values and remember how they were written, so `150 kg` prints in kg while
  `kg*m/s²` prints as N.
* **Rearrangement** peels an expression tree away from the unknown, inverting one operation at a time,
  then evaluates the result with unit-checked arithmetic, so answers carry correct units by construction.
* Errors carry source spans, so the caret lands on the offending expression.

Source layout: `src/f2orge/` (`units.py` registry, `dimensions.py`, `quantity.py`, `lexer.py`,
`parser.py`, `evaluator.py`, `equation.py`, `solver.py`, `interpreter.py`, `docgen.py`, `repl.py`,
`cli.py`, `stdlib/*.eq`), `tests/`, `examples/`, `vscode-forge/`.

## Known limits

* The solver handles one equation at a time; simultaneous systems are not supported yet.
* Numeric solving needs the unknown's unit to be declared.
* `rad` and `deg` are dimensionless, so angular velocity in rad/s is the same dimension as 1/s.
* Currencies, logarithmic units (dB) and `rpm` are not defined.
* Graph export currently plots one callable equation output against one declared input and writes
  SVG. Multiple curves vary a single additional input (up to 20 curves); interactive plots,
  calculators, matrices and vectors are not implemented yet.
