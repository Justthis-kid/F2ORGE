# F²ORGE language reference (v0.1)

File types: `.forge` programs and `.eq` equation files. A program is a list of statements, one per
line (or separated by `;`). `#` and `//` start a comment.

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
`plot(y)` or `plot(x, y)` on vector variables to open a native plot window. `:clear` resets the
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
arbitrary F²ORGE statements, including equation definitions, imports, solves, conversions, loops,
prints, assignments, and expressions. Script nodes run before Output nodes, so graph Inputs can
consume variables created by script blocks. Connect typed nodes for visual expression building.
When an Input and Output use the same variable name, the IDE asks you to confirm sharing; the graph
compiler orders the producing Output before Outputs that consume it. A circular shared-variable
dependency is rejected. Graph files use version 2 to preserve node dimensions and remain compatible
with version 1 files. Use **Open**/**Save file** for `.forge` or `.eq` programs and
**Open graph**/**Save graph** for `.fgraph` diagrams. `--no-open`
prevents automatic browser launch; `--port 0` requests an available local port. Stop the server
with Ctrl+C.

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
