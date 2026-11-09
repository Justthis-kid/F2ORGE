# F²ORGE language reference

This reference describes the implemented language, not planned syntax. For a guided first project,
see the [F²ORGE tutorial](tutorial.md); for a categorized vocabulary of units, constants, operators,
and concepts, see the [language dictionary](dictionary.md).

File types: `.forge` programs and `.eq` equation files. A program is a list of statements, one per
line (or separated by `;`). `#` and `//` start a comment.

## Program structure and statements

Programs execute from top to bottom. Use one statement per line or separate statements with `;`.
Blank lines and `#` or `//` comments are ignored. Names are case-sensitive.

| Form | Meaning |
|---|---|
| `name = expression` | Assign or replace a variable. |
| `expression` | Evaluate and display the result; also stores it in `ans`. |
| `print expression, "text"` | Print one or more expressions and/or string literals. |
| `convert expression -> unit` | Convert and display a quantity in another compatible unit. |
| `eq Name { ... }` | Define a reusable equation. |
| `worksheet Name { ... }` | Define unit-checked inputs, calculated outputs, and optional graph sweeps for the IDE. |
| `solve Name for variable { given = value }` | Solve an equation for one unknown from known values. |
| `import Name` / `import ./path/File.eq` | Load an equation by library/project name or file path. |
| `export Name` | Write a defined equation to a `.eq` file. |

F²ORGE does not currently have general-purpose `if`, `for`, or `while` statements, functions defined
by the user, or string interpolation. The word `for` is part of `solve ... for ...`, not a loop.

## Native engineering worksheets

A worksheet is a first-class Forge declaration, not a series of steps in a UI wizard. The `.forge`
source is authoritative; the offline IDE renders the declared controls and recalculates them when
inputs change. Open `examples/flight-worksheet.forge` in the IDE and run it to see the worksheet.

```forge
worksheet Flight {
    description = "Newton's second law"
    input mass : kg = 150 kg "Vehicle mass"
    input acceleration : m/s^2 = 9.81 m/s^2 "Acceleration"
    output force = mass * acceleration
    graph force over acceleration from 0 m/s^2 to 20 m/s^2
}
```

Each `input` declares a unique name, required unit, default quantity, and optional quoted help text.
Defaults may use constants but not other worksheet inputs. Each `output` is a scalar expression using
worksheet inputs and earlier outputs; output names must be unique and cannot shadow input names.
Optional `description = "..."` metadata is shown above the controls. A `graph` declaration sweeps one
input across two finite, distinct endpoints with compatible units and plots the named output. The IDE
validates entered numeric magnitudes against the declared input units, updates outputs live, and
renders each declared graph. Worksheets run from the local IDE and do not change the behavior of
ordinary script execution or equation calls.

## Values and units

```
mass = 150 kg
velocity = 30 m/s
accel = 9.81 m/s²            # also written m/s^2
resistance = 4.7 kohm
```

* A **number immediately followed by a unit** is a quantity: `150 kg`, `9.81 m/s²`.
* Inside such a unit, `*` `/` `^` must touch their operands: `m/s^2`, `W/(m*K)`.
  With spaces they are ordinary operators: `10 m / 2 s` means (10 m) / (2 s).
* A bare number is dimensionless. `2 * x` multiplies; `2 x` is an error (it would be read as a unit).
* SI prefixes work on most units: `km`, `mm`, `MPa`, `kN`, `uF` (or `µF`). `forge units` lists everything.
* Angles: `deg` and `rad` are dimensionless, so `sin(30 deg)` works and `sin(30)` means 30 radians.
* Temperatures: `degC` and `degF` are *scales* (25 degC = 298.15 K). Subtracting two of them gives a
  difference in `K`; adding two absolute temperatures is an error; inside compound units
  (`W/(m*degC)`) they mean a temperature *difference*.
* Unit products, quotients, and exponents can be grouped with parentheses, for example `W/(m*K)`.
  Unit multiplication/division/exponent operators are written tightly (`kg*m/s^2`); expression
  operators are separated by spaces when the distinction might be unclear.

### What gets printed

Results are shown in the unit you wrote (`10 kN + 500 N` -> `10.5 kN`; `2 * 5 ft` -> `10 ft`).
Multiplying or dividing two quantities gives simplified SI, using a named unit when one fits:
`kg*m/s²` -> `N`, `N*m` -> `J`, `V/A` -> `Ω`. `forge --ascii` prints `m/s^2` instead of `m/s²`.

## Operators and functions

`+ - * / ^` and parentheses. `^` is right-associative and binds tighter than unary minus
(`-2^2` is -4, `2^3^2` is 512). Unicode `× · ÷ − →` and superscripts (`x²`) are accepted.

Functions: `sin cos tan asin acos atan atan2 exp ln log sqrt abs min max`.
`log` is base 10. `sqrt(16 m^2)` is `4 m`. Trig and log arguments must be dimensionless.
`inverse` and `transpose` operate on matrices.

| Function | Inputs and result |
|---|---|
| `sin(x)`, `cos(x)`, `tan(x)` | Trigonometric functions; `x` is dimensionless (use `deg` or `rad` for angles). |
| `asin(x)`, `acos(x)`, `atan(x)` | Inverse trigonometric functions; input and result are dimensionless angles in radians. |
| `atan2(y, x)` | Two-argument angle function; arguments must be dimensionless. |
| `exp(x)`, `ln(x)`, `log(x)` | Exponential, natural log, base-10 log; argument must be dimensionless. |
| `sqrt(x)` | Square root; unit exponents are halved and must remain representable. |
| `abs(x)` | Absolute magnitude of a scalar quantity. |
| `min(a, b, ...)`, `max(a, b, ...)` | Select the smallest/largest compatible scalar quantity; at least two arguments. |
| `transpose(A)`, `inverse(A)` | Matrix operations; inverse requires a square, dimensionless matrix. |

### Vectors and matrices

Vectors use angle brackets; matrices are rows of bracketed values:

```
v = <1, 2, 3>
A = [
  [1, 2]
  [3, 4]
]
transpose(A)
inverse(A)
A * v
```

Vectors support addition/subtraction, scalar multiplication/division, and dot products. Matrices
support addition/subtraction, scalar multiplication/division, matrix multiplication, matrix-vector
products, transpose, and inverse. Element operations preserve unit checking. Inverse currently
requires a square, dimensionless matrix. Matrices and vectors are program values, not equation
outputs or solver relations.

Built-in constants: `pi e g G R` (physics), `speedOfLight kB NA sigmaSB`, and the aerospace pack
`muEarth rEarth rhoSL pSL TSL`. Your own variables may shadow them.

## Conversion

```
convert 10 ft -> m          # 3.048 m
convert 60 mph -> m/s
convert 25 degC -> K
```

## Equations

```
eq Force {
    description = "Newton's Second Law"     # metadata: any  key = "text"
    m : kg "mass"                           # optional declaration: unit (+ doc string)
    a : m/s^2
    F : N
    F = m * a                               # a relation
}
```

* **Outputs** are names defined by `name = ...`; **inputs** are every other variable. Nothing is
  declared by hand. Relations may appear in any order and may build on each other.
* **Declarations are optional.** With them, arguments are unit-checked at the call
  (`a of Force expects acceleration (m/s²), but this is mass (kg)`), outputs print in the declared
  unit, and the formulas are dimension-checked when the equation is *defined*.
* A relation whose left side is not a single name (`p1 + 0.5*rho*v1^2 = p2 + ...`) is an implicit
  relation: use it with `solve`, not as a call.
* A built-in constant name used inside an equation is the constant, unless you declare it:
  `R : ohm` makes R a resistance input, as in `Ohm.eq`.
* Equations are pure: they never see your top-level variables, only their inputs and the constants.
* Equations can call other equations.
* Metadata uses `key = "text"` inside an equation; `description` is conventional and is used by
  generated equation documentation. A declaration's optional quoted text documents that variable.

### Calling

```
force = Force(
    m = 150 kg,
    a = 9.81 m/s²
)
Force(m = 2 kg, a = 3 m/s²).F        # .name picks an output when there are several
```

Arguments are always named. The call returns the equation's main output (the one nothing else uses).

### Solving

```
solve Force for a {
    F = 100 N
    m = 50 kg
}
# a = 2 m/s²
```

1. The solver rearranges symbolically when the unknown appears once (`a = F / m`), through
   `+ - * / ^ sqrt ln exp log sin cos tan asin acos atan`. Use `forge run --explain` to see the result.
2. With several relations it chains them: any relation with one unknown yields it, until the target is known.
3. If the unknown appears twice (`t + t^2 = 6`) it solves numerically, which needs the unknown's unit
   declared (`t : dimensionless`). Positive solutions are preferred; other roots are reported.
4. If information is missing it says exactly what: `cannot find F from F = m * a: m, a are unknown`.
5. Numeric solving is not a general simultaneous-system solver. Equations requiring several
   independent unknowns at once will report what information is missing.

## Files

```
import Force                    # Force.eq from the project, ./formulas, ./eq, $FORGE_PATH, or the standard library
import ./formulas/Force.eq      # an explicit path (relative to the importing file)
export Force                    # writes Force.eq next to the program
```

Standard library:
`Force KineticEnergy Work Power Momentum Density PressureFromForce HydrostaticPressure SpringForce
Bernoulli DeltaV IdealGas Ohm ElectricalPower CapacitorEnergy Lift CircularOrbit`.
An `.eq` file may contain only `eq` definitions and `import`s.
Imports search relative to the importing file and the project, configured equation paths, and the
bundled standard library. File paths in `import` are relative to the importing file.

## Graph export

`forge graph` samples a callable equation output over a declared input range and writes a standalone
SVG (no plotting package or desktop GUI required):

```powershell
forge graph Force --vary a --from 0 --to 20 --set "m=150 kg" -o force.svg
forge graph Force --vary a --from 0 --to 20 --curve "m=50 kg" --curve "m=100 kg"
```

The varying input must have a unit declaration. `--from` and `--to` are magnitudes in that unit.
Provide every other input with `--set NAME=VALUE`; `--samples` controls the point count (default
101), and `--output-name` selects a non-primary output. Repeat `--curve NAME=VALUE` to graph multiple
curves while varying one other input; every curve option must name the same input. The SVG uses the
declared or inferred SI output unit, variable documentation as axis labels when available, and a
legend for multiple curves. It can be opened in a browser on any supported platform.

A program can also draw its own graphs with a `plot` statement:

```text
speed = linspace(0 m/s, 30 m/s, 61)
power = 0.5 * 1200 kg/m^3 * 2.1 m^2 * 0.3 * speed^3
plot(speed, power)
plot(power)
```

`plot(y)` uses the sample index for the horizontal axis; `plot(x, y)` needs two vectors of the same
length whose elements share a dimension. `forge run` writes `program-plot.svg` next to the program
(`-plot-2`, `-plot-3`, ... for further plots) and accepts `--plot-format svg|png|pdf|html`. The
shell prints a one-line summary, the desktop IDE opens a window per plot after the run, and the
browser IDE opens the last plot in its interactive plot dialog.

The offline IDE's **Charts** tab plots editable table data or imported CSV files. Use the first CSV
row for column names and optionally append units in brackets, such as `time [s],distance [m]`.
Choose a 2D line, scatter/points, or bar chart; bar charts use the first selected column as
categories, while line and scatter charts require a numeric horizontal column. Select up to 10
numeric value series. Series must have compatible dimensions and are converted to the first
selected series' unit for display. Cells must be finite numbers for numeric axes; category cells
may be text. The table editor can add rows and columns.

The same table workflow supports interactive **3D scatter**, **3D line**, and **3D surface** plots.
Choose separate X, Y, and Z columns for scatter/line. A surface requires a complete rectangular
grid with exactly one Z value for each X/Y pair. Drag to rotate and scroll to zoom; the reset
control restores the initial camera. All table-based plots run locally without a chart service or
external JavaScript library. 2D charts export to SVG, PNG, and standalone interactive HTML; use
**Print / PDF** to print or save a chart as a PDF in the browser. 3D charts export as standalone
interactive HTML, and can also be printed from the browser.

Add `--interactive` to create a self-contained HTML graph instead. It works offline and supports
wheel/trackpad zoom, drag-to-pan, reset, and toggling individual curves:

```powershell
forge graph Force --vary a --from 0 --to 20 --curve "m=50 kg" --curve "m=100 kg" --interactive
```

## Calculator export

Generate a standalone HTML calculator from a callable equation:

```powershell
forge calc Force -o force-calculator.html
```

Open the generated file in a browser; it runs locally without a server or internet connection.
Changing an input recalculates the outputs immediately. Enter a number in the declared input unit,
or append a compatible unit such as `0.15 t`; incompatible units and invalid values are reported
in the page. Every input needs a unit declaration so the calculator can validate values. Outputs
use their declared unit or the inferred SI unit.

For an interactive terminal calculator using the same evaluator, run
`forge calc Force --terminal`. Enter assignments such as `m = 150 kg`; outputs recalculate when
inputs change. Use `:help` for a reminder, `:values` to inspect current values, or `:quit` to exit.

## Offline desktop IDE

Run `forge ide` to open the offline desktop IDE, embedded in a native webview and sharing the
browser IDE interface and Blueprint implementation. Install its optional dependency with
`pip install "f2orge[desktop]"`; Windows also requires the Microsoft WebView2 runtime. Open or save
`.forge` and `.eq` files, then
press **Run** or **F5** to execute it. The workspace shows variables and equations; the command
window runs expressions and assignments in the same session, with Up/Down command history. Use
`plot(y)` or `plot(x, y)` on vector variables to open a native plot window, and a `plot` statement
in a script opens its graph after the run. `:clear` resets the
workspace. The IDE serves its bundled UI on loopback and runs locally without an internet connection.
The **Blueprint** tab provides a graph-paper canvas with Input, Constant,
Function, arithmetic, Script, and Output nodes. Connect output pins to input pins, then select **Run Graph**
to compile the visual flow into F²ORGE statements and execute it in the shared workspace. Input
nodes refer to variables already present in the workspace; Constant nodes accept F²ORGE
expressions. Drag node headers to reposition and the lower-right corner to resize; double-click a
node to edit it. Script nodes edit arbitrary F²ORGE statements. Matching Input and Output names
show a confirmation before they share a variable, and dependent outputs are ordered automatically.
Select a node and use **Delete Node** or press Delete. Save and reopen browser-compatible `.fgraph`
files. **Dark: On/Off** switches between light and a softer,
lower-contrast dark palette. Middle-drag to pan the graph canvas; use the mouse wheel to scroll.
Syntax highlighting and code completion are not included yet.

## Browser IDE

Run `forge browser` to open the local browser-based IDE at `http://127.0.0.1:8765`; `forge web`
is an alias. The application is served on loopback by the local F²ORGE process and does not use a
cloud service or remote assets. It includes a script editor, command window, workspace list, and a
Blueprint canvas with draggable, connectable, deletable, resizable nodes. A **Script** node accepts
arbitrary supported F²ORGE statements, including equation definitions, imports, solves, conversions,
prints, assignments, and expressions. Script nodes run before Output nodes, so graph Inputs can
consume variables created by script blocks. Connect typed nodes for visual expression building.
When an Input and Output use the same variable name, the IDE asks you to confirm sharing; the graph
compiler orders the producing Output before Outputs that consume it. A circular shared-variable
dependency is rejected. Graph files use version 2 to preserve node dimensions and remain compatible
with version 1 files. Use **Open**/**Save file** for `.forge` or `.eq` programs and
**Open graph**/**Save graph** for `.fgraph` diagrams. `--no-open`
prevents automatic browser launch; `--port 0` requests an available local port. Stop the server
with Ctrl+C.

The **Charts** tab is for data-driven charts rather than Blueprint diagrams. Paste or edit CSV
data, import a local `.csv` file, select columns and chart type, then render. Units in column headers
are validated and appear on axes. Export 2D charts as SVG, PNG, or offline HTML; 3D charts as
offline HTML. Print / PDF uses the browser's print dialog.

## Scope beyond the language core

The language core does not depend on interactive graphs, generated calculators or live updates,
domain objects (`rocket`, `motor`, `battery`), or interactive worksheets.
Static SVG and interactive HTML graph export and standalone offline calculator export are optional
companion tools. `forge graph` can also export PNG/PDF (install `f2orge[plots]`) or open an
interactive native window (install `f2orge[desktop]`). `forge plot FILE.forge Y --x X` plots vectors
from a script, with optional HTML export. Calculators support offline HTML, terminal, native-window,
and standalone Windows executable output; the desktop extras are required for native windows, and
the build extra is additionally required for an executable. The native and loopback browser IDEs are
initial implementations; an equation marketplace is not recommended for v1.

Simultaneous equation systems are not solved yet; each `solve` handles one chain of single-unknown
relations.
