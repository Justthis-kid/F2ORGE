# F²ORGE (Formula Forge)

A unit-safe engineering programming language where reusable equations and native engineering
worksheets become live calculations, solvers, documentation, portable graphs, and standalone offline
calculators. Everything is local files: no cloud, no accounts, no database, and **no dependencies
beyond Python's standard library**.

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

## Learn and reference

- [Guided tutorial](docs/tutorial.md) — a sequence of lessons, examples, and review questions.
- [`examples/tour.forge`](examples/tour.forge) — one runnable script that exercises most of the
  language, from units and matrices through calculus, signals, domain objects, and plots.
- [Language reference](docs/language.md) — syntax and behavior for scripts, units, equations, solving,
  vectors, matrices, graphing, and calculators.
- [Language dictionary](docs/dictionary.md) — built-in vocabulary, functions, constants, unit names,
  prefixes, dimensions, and CLI commands.

## Instruction manual: install, launch, and use F²ORGE

F²ORGE requires Python 3.9 or newer. Open a terminal in the extracted project folder (the folder
containing `pyproject.toml`) and follow the instructions for your operating system. The interpreter
and graph exporter use only Python's standard library; the optional `.[dev]` install also installs
pytest for running the tests.

### 1. Install

First, change into the project root: the directory that contains `pyproject.toml`, `src`, and
`tools`. If you extracted a ZIP and the first folder does not contain those files, enter the nested
project folder. For example, if the files are in `Downloads/f2orge/F2ORGE`, use
`cd ~/Downloads/f2orge/F2ORGE` on macOS/Linux or
`cd "$HOME\Downloads\f2orge\F2ORGE"` in PowerShell. Replace `F2ORGE` with the actual extracted
folder name if it differs.

**Windows (PowerShell):**

```powershell
cd "$HOME\Downloads\f2orge\F2ORGE"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

If PowerShell says script execution is disabled when activating, open Command Prompt and run:

```bat
cd "%USERPROFILE%\Downloads\f2orge\F2ORGE"
.venv\Scripts\activate.bat
python -m pip install -e .
```

**macOS / Linux:**

```bash
cd ~/Downloads/f2orge/F2ORGE
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools
python -m pip install -e .
```

Upgrading pip is important on macOS installations that bundle an older pip: editable installs from
`pyproject.toml` require a modern build frontend. To run the tests too, use
`python -m pip install -e ".[dev]"` after upgrading pip and setuptools. Activate the virtual
environment again whenever you open a new terminal.

### 2. Launch F²ORGE

Run a program, start the interactive shell, or ask for help:

```text
forge run examples/force.forge
forge shell
forge ide
forge browser
forge transpile examples/force.forge --target python -o force.py
forge transpile examples/force.forge --target cpp -o force.cpp
forge transpile examples/force.forge --target micropython -o force-mpy.py
forge transpile examples/force.forge --target ti-basic -o force.8xp
forge transpile examples/force.forge --target ti-basic -o force.ti.txt
forge --help
```

`forge ide` opens the offline desktop IDE in an embedded webview, reusing the browser IDE UI and its
MATLAB-style workspace, script editor, command window, and complete Blueprint canvas. Install the
desktop webview dependency with `pip install "f2orge[desktop]"`; Windows needs the Microsoft
WebView2 runtime. The Blueprint tab uses a graph-paper grid: add
Input, Constant, Function, Call, Compare, arithmetic, Output, two-output, and Script nodes. A
**Call** node names a function or equation and takes one pin per argument, so `area(r)` uses one and
`cross(a, b)` two; a **Compare** node applies `<`, `<=`, `>`, `>=`, `==`, or `!=`; and a **two-output**
node unpacks a function that returns several parts, generating `[time, velocity] = solveODE(...)`.
Drag node headers to reposition; drag a node’s lower-right corner to resize it. Select a node and
choose **Delete Node** (or press Delete) to remove it. Connect output pins to input pins. A Script
node accepts arbitrary F²ORGE statements, so equations, imports, solves, conversions, prints,
assignments, and expressions can all be authored in the Blueprint canvas. Script nodes run before
generated Output nodes.
Input nodes reference workspace variables; an Input and Output sharing a name prompts for
confirmation and orders dependent outputs automatically. Save and reopen `.fgraph` files.
**Dark: On/Off** switches between light and a softer, lower-contrast dark palette. Pan the graph
with the middle mouse button and scroll with the wheel. In the command window, use `plot(y)` or
`plot(x, y)` for vectors. The desktop window runs the bundled local IDE server on loopback and
requires no internet access. On Windows, backslashes in file paths work too (for example
`forge run examples\force.forge`).

Use the **Convert to** selector in the IDE to generate and download Python, C++, MicroPython, or
TI-84 BASIC from the current script. The same conversion is available from the CLI with
`forge transpile FILE.forge --target python|cpp|micropython|ti-basic [-o OUTPUT]`. Conversion
currently supports scalar assignments, arithmetic, scientific functions, constants, `print`, and
`convert`. Unit literals and physical constants become SI numeric values; generated code does not
retain F²ORGE's dimensional checks. Equation definitions, solves, imports, and vectors/matrices are
rejected with a source-located explanation rather than silently altered. MicroPython output uses
only `math` and built-ins, including a portable base-10 logarithm expression, and targets the
standard MicroPython language subset. TI-84 BASIC output is readable source for the TI-84/Plus/Plus CE
calculator BASIC language; it maps F²ORGE names to the calculator's 27 scalar variables and adds a
non-running variable map. Write the output to a `.8xp` name to get a tokenized calculator program
instead of text:

```text
forge transpile program.forge --target ti-basic -o program.8xp
```

The `.8xp` file carries the TI variable header, the tokenized program and its checksum, so TI Connect
(or another link tool) can send it straight to a TI-83/84 Plus or Plus CE. The browser IDE's
**Download** button does the same for TI-84 BASIC. `atan2` and more than 27 distinct scalar variables
are not supported by the TI-BASIC target.

### Build a standalone Windows app

On Windows, install the desktop and build extras, then run:

```powershell
cd "$HOME\Downloads\f2orge\F2ORGE"
python -m pip install -e ".[desktop,build]"
python tools/build_windows.py
```

Run both commands from the project root (the folder containing `pyproject.toml` and
`tools\build_windows.py`); the build writes the updated executable to `dist\F2ORGE.exe`.
The generated `dist/F2ORGE.exe` is a windowed, one-file desktop app with the F²ORGE cube icon.
It uses the installed Microsoft WebView2 runtime. Build it on Windows; the generated executable
does not require a separate Python installation.
If your system already uses the `forge` command (for example, Foundry), use `f2forge` in its place
or launch F²ORGE as a Python module:

```text
f2forge run examples/force.forge
python -m f2orge run examples/force.forge
```

`forge browser` starts a browser-based engineering workspace at `http://127.0.0.1:8765` and opens
it automatically. It is served only from your own computer; no cloud service or external assets are
used. The browser workspace includes a script editor, persistent command window, variable/equation
list, Blueprint canvas, table-based Chart Studio, native engineering worksheets, and a softer dark
theme. Declare worksheets directly in `.forge` source with `worksheet`, `input`, `output`, and
optional `graph` declarations; running the source creates live unit-aware controls in the
**Worksheets** tab. See [the language reference](docs/language.md#native-engineering-worksheets) and
[`examples/flight-worksheet.forge`](examples/flight-worksheet.forge). In the **Charts** tab,
edit a table as CSV or import a local CSV file, then create 2D line, scatter/point, or bar charts and
interactive 3D scatter, line, or surface plots. Column headers may declare units, such as `time [s]`;
the IDE checks numeric data and unit compatibility. 2D charts export to SVG, PNG, or offline
interactive HTML, while 3D charts export to offline interactive HTML. Use Print / PDF to open the
browser's print dialog. Blueprint nodes can be repositioned, resized, and
deleted; Script nodes support any F²ORGE statement, while name-shared Input/Output nodes prompt for
confirmation. Use **Open** and **Save file** to load and download
`.forge`/`.eq` programs, or **Open graph** and **Save graph** for `.fgraph` diagrams. Use
`forge browser --port 0` to choose an available local port automatically, or `--no-open` to start
the server without opening a browser. Both IDEs use warm off-white surfaces, restrained orange
highlights, and a deep charcoal dark mode. Stop it with Ctrl+C in the terminal.

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
The SVG is self-contained and does not require a plotting package or desktop GUI. Add `--interactive`
to export an offline HTML graph with zoom, pan, reset, and per-curve toggles:

```text
forge graph Force --vary a --from 0 --to 20 --curve "m=50 kg" --curve "m=100 kg" --interactive
```

Choose PNG or PDF via `--format` or the output extension. These raster/document formats require
Pillow (`pip install "f2orge[plots]"`). Add `--window` to open an interactive plot in a native
desktop window. For MATLAB-style plotting of vectors produced by a script, use
`forge plot FILE.forge Y --x X`; omit `--x` for sample indices. Add `-o graph.html` to export the
interactive plot instead of opening a window. Native windows need the desktop extra and a supported
system WebView.

Programs can also draw their own graphs with a `plot` statement, which works in `forge run`, the
shell, the desktop IDE, and the browser IDE:

```text
speed = linspace(0 m/s, 30 m/s, 61)
power = 0.5 * 1200 kg/m^3 * 2.1 m^2 * 0.3 * speed^3
plot(speed, power)
```

`plot(y)` uses the sample index for the horizontal axis; `plot(x, y)` needs two vectors of the same
length with matching units. `forge run` writes one graph per plot statement next to the program
(`program-plot.svg`, or `-plot-2`, ... for more), and `--plot-format png|pdf|html` chooses the
format. The desktop IDE opens each plot in its own window after the run, and the browser IDE opens
the last plot in the interactive plot dialog.

### 7. Generate an offline calculator

Turn a callable equation into a self-contained HTML app:

```text
forge calc Force -o force-calculator.html
```

Open the file in a browser. Enter each value in its declared unit, or include a compatible unit
(`0.15 t` is accepted for a mass input declared in kg); the output updates as you type. Incompatible
units are reported next to the fields. All calculations run locally in the page.

For an interactive terminal version, run `forge calc Force --terminal` and enter assignments such
as `m = 150 kg`. Outputs recalculate whenever you change an input; use `:help`, `:values`, or `:quit`.
Use `forge calc Force --desktop` for a native desktop calculator window, or
`forge calc Force --executable -o Force-calculator.exe` to build a standalone Windows app. These
options require the desktop extra; executable generation also requires the build extra.

### 8. VS Code and tests

For syntax highlighting, follow [the VS Code extension instructions](vscode-forge/README.md). To run
the test suite after installing the development extra:

```text
python -m pytest -q
```

The same F²ORGE commands are available in the VS Code terminal on Windows, macOS, and Linux.

### Quick command reference

```text
forge run FILE.forge [--explain]     Run a program; plot statements write graph files
forge shell                          Start the interactive shell
forge ide                            Launch the offline desktop editor
forge check FILE...                  Parse and unit-check equation files
forge doc EQUATION [-o FILE.md]      Generate equation documentation
forge calc EQUATION [-o FILE.html]   Export an offline calculator; --desktop opens a window
forge graph EQUATION ...             Export SVG, PNG, or PDF; --window opens an interactive plot
forge plot FILE.forge Y [--x X]      Plot script vectors interactively or export HTML
forge transpile FILE --target TARGET  Generate Python, C++, MicroPython, or TI-84 BASIC
                                      (-o program.8xp writes a tokenized TI-84 program)
forge units [FILTER]                 List built-in units
forge --version                      Print the installed version
```

## Feature scope

The v1 goal is a useful, unit-safe language for writing, reusing, and solving engineering equations.
Graphing, interactive apps, and broader engineering data types are follow-on features; they should
not block a dependable language and solver.

### Core language (v1)

| Capability | Status |
|---|---|
| Variables, arithmetic (`+ - * / ^`), scientific functions, and built-in constants | Implemented |
| Built-in units, conversions, dimensional analysis, and unit-safety errors | Implemented |
| First-class equations with inferred inputs/outputs, named calls, metadata, imports, and exports | Implemented |
| Native worksheets with unit-declared inputs, calculated outputs, descriptions, and graph sweeps | Implemented |
| Equation documentation and reusable standard-library formulas | Documentation implemented; formula library growing |
| Solve for a variable, rearrange equations, and report missing information | Implemented |
| Simultaneous systems: `solve A, B for x, y` with inferred units and a Newton solver | Implemented |
| Control flow (`if`/`elseif`/`else`, `for`, `while`, `break`, `continue`) and user functions (`def`, `fn`) | Implemented |
| Script-level data files: `readtable()` and `csvwrite()` with unit-aware columns | Implemented |
| Calculus: symbolic `diff()`, numeric `integrate`/`derivative`, `trapz()`, and `limit()` | Implemented |
| Signal processing: `fft`, filtering, windows, and Bode/resonance data | Implemented |
| Tracing and profiling: `forge trace`, `forge profile` | Implemented |
| Blueprint nodes for calls, comparisons (including `mag<`), and unpacking several results | Implemented |
| Domain objects: built-in `Rocket`, `Motor`, `Battery`, and custom `object` declarations | Implemented |
| Differential equations: `solveODE()` (adaptive RK45, plottable time series) and `solvePDE()` (steady-state fields) | Implemented |
| Optimisation: `fminsearch()` over several variables and `linprog()` for linear programs | Implemented |
| CLI execution, interactive shell, local files, and explanatory source locations | Implemented |
| VS Code syntax highlighting | Available |
| Vectors and matrices: arithmetic, products, transpose, inverse | Implemented; inverse is unit-aware for matrices whose units factor into rows and columns |

### Companion tools (useful, but not required for the language core)

| Capability | Status |
|---|---|
| Static SVG and interactive HTML graphing, sweeps, multiple curves | Initial implementation |
| Offline HTML and terminal calculators, live recalculation, and unit validation | Initial implementation |
| Python, C++, MicroPython, and TI-84 BASIC generation for scalar scripts | Initial implementation; generated code uses SI numbers and omits unit checks |
| PNG/PDF graph export and MATLAB-style interactive plot windows | Implemented |
| Generated native calculator forms and standalone desktop calculator apps | Implemented |
| Offline browser/desktop IDE with live worksheet controls and SVG graph previews | Implemented |

### Advanced and long-term features

| Capability | Status |
|---|---|
| Engineering domain objects (`rocket`, `motor`, `battery`) | Future work |
| Standalone Windows executable build and additional IDE refinements | In progress |
| Equation marketplace | Later; not recommended for v1 |

The [language reference](docs/language.md), [dictionary](docs/dictionary.md), and
[tutorial](docs/tutorial.md) describe the implemented language and companion tools. Worksheets are
first-class Forge source declarations, not a staged UI wizard: define `worksheet`, `input`, `output`,
and optional `graph` statements in a `.forge` file, then run it to populate the IDE's **Worksheets**
tab with live, unit-aware controls. See
[`examples/flight-worksheet.forge`](examples/flight-worksheet.forge) for a complete example.
Engineering domain objects such as `rocket`, `motor`, and `battery` remain future work.

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

* Numeric solving of a single equation needs the unknown's unit to be declared (for systems, units
  are inferred from the relations unless an equation declares them).
* `rad` and `deg` are their own dimension, so `rad/s` is an angular velocity while `1/s` is a
  frequency; trig functions accept an angle or a plain number of radians.
* Currencies have a dimension of their own and no exchange rates; `dB` and `rpm` are defined as
  their own kinds of unit.
* `inverse()` needs a square matrix whose elements factor into row and column dimensions.
* Graph export is an optional companion tool: it plots one callable equation output against one
  declared input; multiple curves vary a single additional input (up to 20 curves). Pillow is
  needed only for PNG/PDF exports; native plot and calculator windows need the desktop extra.
  Standalone calculator executables are currently Windows-only and require the build extra.
