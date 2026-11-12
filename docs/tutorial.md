# Learn F²ORGE: a guided engineering tutorial

This short course builds from quantities to reusable formulas, solving, vectors, graphs, and
calculators. Work through each lesson in a `.forge` file or the IDE's script editor. To install and
launch the tools, start with the [README](../README.md). For exact syntax and limits, use the
[language reference](language.md); for terminology and the unit catalog, see the
[language dictionary](dictionary.md).

## Lesson 1 — Make quantities, not naked numbers

Create `first.forge`:

```forge
mass = 150 kg
acceleration = 9.81 m/s^2
force = mass * acceleration
force
```

Run `forge run first.forge`. The result is a force (about `1471.5 N`): F²ORGE tracks both the
number and its physical dimension. Try changing the last line to `mass + acceleration`. The program
will stop with a unit-mismatch error because mass and acceleration cannot be added.

**Think about it:** Why is `mass * acceleration` meaningful, while their sum is not?

## Lesson 2 — Convert a measurement

Add these lines:

```forge
convert 10 ft -> m
convert 60 mph -> m/s
```

Conversions preserve the represented physical quantity. A conversion fails if the source and
destination units have different dimensions. A temperature scale such as `degC` includes an offset,
so `convert 25 degC -> K` produces an absolute temperature rather than a temperature difference.

## Lesson 3 — Turn a formula into an equation

Define `Force` once, then call it with named arguments:

```forge
eq Force {
    description = "Newton's Second Law"
    m : kg "mass"
    a : m/s^2 "acceleration"
    F : N "force"
    F = m * a
}

force = Force(m = 150 kg, a = 9.81 m/s^2)
force
```

The declarations document units and let F²ORGE check input dimensions and the formula when the
equation is defined. The equation's output is `F`; its inputs are inferred as `m` and `a`. Named
arguments make a call unambiguous. Run `forge doc Force` to generate a readable formula reference.

## Lesson 4 — Ask the solver for a different unknown

Add a solve block:

```forge
solve Force for a {
    F = 100 N
    m = 50 kg
}
```

F²ORGE rearranges the relation and returns `a = 2 m/s²`. `--explain` (`forge run --explain
first.forge`) shows the rearranged expression. A solve block lists known values; the `for` target is
the one value to find. If the givens do not determine the target, the diagnostic identifies what is
missing.

To find several unknowns at once, name several equations and several unknowns:

```forge
eq Sum { x + y = s }
eq Diff { x - y = d }
solve Sum, Diff for x, y {
    s = 10 m
    d = 2 m
}
```

This returns `x = 6 m` and `y = 4 m`. See the
[language reference](language.md#simultaneous-systems) for how units are inferred and how the loops
of a circuit are written.

## Lesson 5 — Build vectors and matrices

```forge
position = <1 m, 2 m, 3 m>
direction = <4, 5, 6>
dot = direction * <1, 0, 0>

A = [
  [1, 2]
  [3, 4]
]
transposed = transpose(A)
inverse_A = inverse(A)
identity = A * inverse_A
identity
```

Vectors and matrices contain scalar quantities. Addition and subtraction require matching shape and
compatible units. Multiplying two vectors computes a dot product; multiplying matrices (or a matrix
and vector) follows the usual dimension rules. `transpose` changes rows and columns. `inverse`
currently accepts only square, dimensionless matrices; singular matrices cannot be inverted. The
interpreter reports incompatible shapes or units instead of silently truncating data.

## Lesson 5b — Calculus: slopes, areas, and limits

F²ORGE can differentiate symbolically, integrate sampled data, and take a limit:

```forge
distance = <0 m, 2 m, 4 m, 6 m>
force = <2 N, 4 N, 6 N, 8 N>
trapz(distance, force)       # 30 J, the work done
trapz(force)                 # 15 N, spaced one unit apart

diff(x^3 + 2*x)              # 3 * x^2 + 2
limit(sin(x) / x, 0)         # 1
derivative(x^2, 3)           # 6, a numeric derivative at x = 3
integrate(x^2, 0 m, 2 m)     # 2.666666667 m³
```

`trapz(x, y)` is the trapezoidal area under a curve, so its units are the units of x times the
units of y: distance times force gives joules. `diff()` returns the derivative as text when you give
it an expression, but still returns neighbouring differences when you give it a vector. `limit()`
handles the 0/0 shapes a calculus class meets, and says plainly when a limit does not exist.

## Lesson 6 — Plot an equation sweep

The graph command evaluates a callable equation repeatedly across a range:

```text
forge graph Force --vary a --from 0 --to 20 --set "m=150 kg" -o force.svg
```

The swept input needs a unit declaration; range endpoints are magnitudes in that input's unit.
Open the static, self-contained SVG in a browser. For zoom, pan, reset, and curve visibility toggles,
export offline interactive HTML:

```text
forge graph Force --vary a --from 0 --to 20 --curve "m=50 kg" --curve "m=100 kg" --interactive
```

Repeated `--curve` values compare cases while sweeping the same other input (here, mass). Try
`--samples 201` for finer sampling. For vector data created by a script, use
`forge plot first.forge direction` after assigning at least two vector values.

A script can also draw its own graph. Save this as `power.forge` and run it with
`forge run power.forge`; the graph is written next to the program as `power-plot.svg`:

```text
speed = linspace(0 m/s, 30 m/s, 61)
power = 0.5 * 1200 kg/m^3 * 2.1 m^2 * 0.3 * speed^3
plot(speed, power)
```

`plot(y)` uses the sample index for the horizontal axis. The desktop IDE opens each plot in its own
window after a run, and the browser IDE shows the last plot in its interactive plot dialog.

## Lesson 7 — Build table charts

Start the browser IDE with `forge browser`, open the **Charts** tab, and edit its CSV table or import
a local `.csv` file. Column headers may declare units:

```csv
time [s],distance [m],height [m]
0,0,1
1,3,2
2,8,4
```

Render a 2D line or scatter chart with `time` as X and one or both distance columns as value
series. For a bar chart, use category labels without a unit in the first column and select a numeric
value column. Units must be compatible across multiple value series.

For a **3D surface**, use a complete rectangular X/Y grid with one Z value for each pair. The example
above is a diagonal path, not a surface grid; a surface needs rows such as `(0,0,z)`, `(0,1,z)`,
`(1,0,z)`, and `(1,1,z)`. Drag the preview to rotate and scroll to zoom. Export 2D charts as SVG,
PNG, or standalone HTML; export 3D charts as standalone HTML. Print / PDF opens the browser print
dialog.

## Lesson 8 — Generate a calculator

Every calculator input needs a unit declaration. Export the `Force` equation as an offline HTML
calculator:

```text
forge calc Force -o force.html
```

Open `force.html` locally. Change a field and observe the outputs recalculate immediately. The
calculator accepts compatible units such as `0.15 t` for an input declared in kilograms; try an
incompatible unit to see field-level validation. The page makes no server or network request.
`forge calc Force --terminal` provides the same equation as an assignment-driven terminal tool.

## Lesson 9 — Reuse a formula from a file

Place an equation definition in `formulas/Force.eq`, then import it from a program:

```forge
import ./formulas/Force.eq
force = Force(m = 150 kg, a = g)
force
```

Project imports use paths relative to the importing file. Library equations can be imported by
name, for example `import Force`. Use `export Force` in a program to write an equation to a `.eq`
file. Equation files contain equation definitions and imports, not arbitrary top-level calculations.

## Lesson 10 — Create a native engineering worksheet

Open `examples/flight-worksheet.forge` in the offline IDE and run it. The worksheet is declared in
Forge source, not assembled through a sequence of UI steps:

```forge
worksheet Flight {
    description = "Explore how mass and acceleration affect force."
    input mass : kg = 150 kg "Vehicle mass"
    input acceleration : m/s^2 = 9.81 m/s^2 "Acceleration"
    output force = mass * acceleration
    graph force over acceleration from 0 m/s^2 to 20 m/s^2
}
```

Select **Worksheets** to see fields generated from the `input` declarations. Change a value and the
unit-aware output and graph update automatically. The `output` declaration names the calculated
quantity; `graph` sweeps acceleration across the specified range. Edit the Forge source to change
the worksheet definition, then run it again to refresh the IDE view.

## Review questions

1. What unit should acceleration use in `F = m * a` if mass is in kilograms and force in newtons?
2. Which two declarations are needed to validate a Force calculator's inputs?
3. Why does adding `10 kg` to `5 m` fail, while multiplying those quantities is valid?
4. What input is swept in the graph command above, and what do the `--curve` settings compare?
5. What restriction applies to `inverse(matrix)`?
6. What must a table contain before it can be rendered as a 3D surface?
7. Which worksheet declarations define a live input, a calculated result, and a graph sweep?

**Suggested answers:** `m/s²`; mass (`kg`) and acceleration (`m/s²`); addition needs like dimensions
but multiplication combines dimensions; acceleration is swept while two fixed masses are compared;
the matrix must be square and dimensionless; one Z value for every pair in a rectangular X/Y grid;
`input`, `output`, and `graph`.
