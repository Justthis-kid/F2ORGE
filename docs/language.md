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
| `solve A, B for x, y { ... }` | Solve several equations for several unknowns at once. |
| `import Name` / `import ./path/File.eq` | Load an equation by library/project name or file path. |
| `export Name` | Write a defined equation to a `.eq` file. |

F²ORGE has general-purpose `if`/`elseif`/`else`, `for`, and `while` statements and user-defined
functions (`def`, also spelled `fn`). String interpolation is not supported; text is a value used
inside statements, such as `print` or `x = "hi"`.

## Control flow and functions

Blocks use braces and may span several lines. Conditions use `and`, `or`, `not` and the comparisons
`< <= > >= == !=`; a number is true when it is nonzero, and comparing quantities of different kinds
is a unit error.

```
for k in 1..5 {
    print k, "squared is", k^2
}

n = 0
while n < 3 {
    n = n + 1
    if n == 2 {
        continue
    }
}

if speed > 20 m/s {
    print "fast"
} elseif speed > 10 m/s {
    print "cruising"
} else {
    print "slow"
}
```

`for` walks a range (`1..10`, `1..10..2` for a step, or the MATLAB-style `for k = 1..10`), a vector,
the rows of a matrix, or the characters of text. `break` leaves the loop and `continue` starts the
next pass. Loops stop with an error after a million passes so a runaway loop cannot hang a session.

Functions are declared with `def` (or `fn`) and return a value with `return`:

```
def area(r) {
    return pi * r^2
}

area(2 m)                 # 12.56637061 m²

def gain(v, ref = 1 m/s) {
    return 20 * log(v / ref)
}
```

Parameters are positional; only the last may have a default. A function sees its own parameters
first and the session's variables second, and calling it does not change those variables. Functions
may call themselves (up to a recursion limit) and can be passed to `integrate`, `derivative`,
`fzero`, `minimize`, and `surface`.

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
* Angles: `deg` and `rad` are their own dimension, so `sin(30 deg)` works and `sin(30)` means 30 radians;
  `rad/s` is an angular velocity while `1/s` is a frequency.
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
`log` is base 10. `sqrt(16 m^2)` is `4 m`, and the square root of a negative quantity is imaginary
(`sqrt(-1)` is `i`). Trig functions take an angle or a plain number of radians; logs need a plain
number.

| Function | Inputs and result |
|---|---|
| `sin(x)`, `cos(x)`, `tan(x)` | Trigonometric functions; `x` is an angle (`deg`, `rad`, `rev`) or a plain number of radians. |
| `asin(x)`, `acos(x)`, `atan(x)` | Inverse trigonometric functions; the result is an angle, shown in radians. |
| `atan2(y, x)` | Two-argument angle; both values must have matching units, and the result is an angle. |
| `exp(x)`, `ln(x)`, `log(x)`, `log2(x)`, `log(x, base)` | Exponential, natural, base-10, base-2, and general logs; the argument must be a plain number. |
| `sqrt(x)`, `cbrt(x)` | Roots; unit exponents are halved or thirds and must remain representable. |
| `abs(x)`, `sign(x)`, `floor(x)`, `ceil(x)`, `round(x, digits)` | Magnitude and rounding of a plain number. |
| `compare_mag(a, b)` | Compare two quantities by size alone: `-1`, `0`, or `1`. Ignores the kind of quantity. |
| `less_mag`, `less_equal_mag`, `greater_mag`, `greater_equal_mag` | Magnitude-only ordering, as booleans. |
| `min(a, b, ...)`, `max(a, b, ...)`, `clamp(x, low, high)` | Select or bound compatible scalar quantities. |
| `cross(a, b)` | Cross product of two length-3 vectors: torque, magnetic force, angular momentum. |
| `transpose(A)`, `inverse(A)`, `det(A)` | Matrix operations; `inverse` needs a square matrix whose units factor into row and column dimensions. |
| `solve_system(A, b)` | Solve `A x = b` for a square matrix of coefficients and a vector of right-hand sides. |
| `sum(v)`, `mean(v)`, `median(v)`, `std(v)`, `pstd(v)`, `var(v)`, `pvar(v)` | Summary statistics; `std`/`var` are the sample forms and `pstd`/`pvar` the population forms. |
| `percentile(v, p)` | The p-th percentile; `p` is a fraction (0 to 1) or a percentage (0 to 100). |
| `linreg(x, y)` | Least-squares fit: returns `<slope, intercept, R²>`. |
| `cumsum(v)`, `diff(v)`, `normalize(v)` | Running total, successive differences, and a vector scaled to sum to 1. |
| `count(v)`, `size(v)`, `sort(v, "asc"\|"desc")`, `select(v, indices)` | Length, shape, ordering, and positional selection. |
| `reshape(v, rows, columns)`, `concat(a, b)`, `linspace(a, b, n)`, `logspace(a, b, n)`, `range(a, b, step)` | Build and reshape vectors. |
| `integrate(f, a, b)`, `derivative(f, x)` | Definite integral and numeric derivative of a function or a bare expression such as `x^2`. |
| `diff(x^2)` | Symbolic derivative, returned as text: `diff(x * sin(x))` is `sin(x) + x * cos(x)`. |
| `trapz(y)`, `trapz(x, y)` | Trapezoidal integral of sampled data, with the units of x times y. |
| `limit(x^2, 2)`, `limit(sin(x)/x, 0)` | The value an expression approaches; 0/0 shapes are resolved with l'Hôpital's rule. |
| `solveODE(f, y0, t0, t1)` | Integrate `dy/dt = f(t, y)` and return `<times, values>`; adaptive Dormand-Prince 5. |
| `solvePDE(grid)` | Relax a square grid of boundary values to steady state; plots as a heatmap. |
| `fft(v)`, `ifft(v)`, `fftfreq(n, dt)` | Discrete Fourier transform, its inverse, and the frequency of each bin. |
| `spectrum(v, dt, window)` | Window and transform in one step: returns `<frequencies, bins>`. |
| `lowpass(v, cutoff, dt)`, `highpass(v, cutoff, dt)`, `bandpass(v, low, high, dt)` | FIR filters built from windowed-sinc Hamming kernels. |
| `window(v, kind)`, `convolve(v, taps)` | Taper a signal (`hann`, `hamming`, `blackman`) or apply your own kernel. |
| `bode(f, cutoff)`, `resonance(f, damping, cutoff)` | Gain and phase of a first- or second-order low-pass, for a Bode plot. |
| `fminsearch(cost, start)` | Minimise a cost over several variables from a starting vector (Nelder-Mead). |
| `linprog(cost, A, b, "max"\|"min")` | Optimise a linear objective under `A x <= b`, with non-negative x. |
| `fzero(f, a, b)`, `minimize(f, a, b)` | A root inside a bracket, and a one-variable minimum (returns `<x, f(x)>`). |
| `fminsearch(f, x0)` | Minimum of a function of several variables, starting from `x0`. |
| `linprog(cost, A, b, sense)` | Linear program with `A x <= b` and `x >= 0`; `sense` is `"max"` (default) or `"min"`. |
| `fminsearch(cost, start)` | Minimise a cost over several variables from a starting vector (Nelder-Mead). |
| `linprog(cost, A, b, "max"\|"min")` | Optimise a linear objective under `A x <= b`, with non-negative x. |
| `roots(<c, b, a>)` | Real roots of `c + b x + a x² + ...`, from the constant term upward. |
| `surface(f, xs, ys)` | Sample `f(x, y)` over a grid into a matrix for `plot(..., kind = "surface")`. |
| `db(x)`, `undb(level)`, `dbm(power)` | Decibel ratios, the inverse of `db`, and a power level in dBm above 1 mW. |
| `pH(concentration)`, `fromPH(level)` | `-log10` of a concentration, and the concentration for a pH. |
| `real(z)`, `imag(z)`, `conj(z)`, `arg(z)`, `mag(z)` | Parts, conjugate, phase, and magnitude of a complex quantity. |
| `format(...)`, `text(x)`, `upper(t)`, `lower(t)`, `char(code)`, `ascii(t)` | Build and inspect text. |

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

Inside parentheses and brackets a newline is insignificant, so calls, vectors, and matrices may span
several lines; a vector or matrix may also begin on the line after its `=`:

```
A = [
  [1, 2]
  [3, 4]
]
force = Force(
  m = 150 kg,
  a = 9.81 m/s^2
)
v = <1, 2, 3>
w = v + <3, 2, 1>        # a '<' after an operator starts a vector
isFast = w > <0, 0, 0>   # compare values with <, <=, >, >=, ==, !=
```

A statement ends at the end of its line unless it is incomplete: a line ending in an operator, or a
block header such as `for k in 1..3`, continues on the next line.

Vectors support addition/subtraction, scalar multiplication/division, and dot products. Matrices
support addition/subtraction, scalar multiplication/division, matrix multiplication, matrix-vector
products, transpose (`M.T` or `transpose(M)`), inverse, and determinant. Element operations preserve
unit checking. Matrices and vectors are program values, not equation outputs or solver relations.

### Indexing and slicing

Indices are **zero-based**. `v[i]` is one element, `M[i]` one row, and `M[i, j]` one cell. A `:`
selects everything along an axis and `j:j+n` a run of n values:

```
v = <10, 20, 30>
v[1]              # 20
v[0:2]            # <10, 20>
M = [[1, 2], [3, 4]]
M[:, 0]           # [[1], [3]]   every row, first column
M[0:2, 0]         # [[1], [3]]   two rows counted from row 0, first column
```

### Complex numbers

Use `i` for the imaginary unit. Complex quantities keep their units, which is what AC impedance
work needs:

```
Z = 3 ohm + 4i ohm
abs(Z)            # 5 Ω
arg(Z)            # 0.927295218 rad
conj(Z)           # 3 Ω - 4i Ω
Z * 2 A           # 6 V + 8i V
sqrt(-1)          # i
```

`real`, `imag`, `conj`, `arg`, and `mag` take a complex quantity apart. Complex numbers cannot be
ordered with `<` or `>`; compare magnitudes with `abs()` instead.

### Logarithmic and angular units

The unit catalog includes `dB` and `dBm` (logarithmic levels), `rpm`/`rps` (angular velocity),
`rad`/`deg`/`rev` (angles), and six currencies (`USD EUR GBP JPY CAD AUD`), each with a dimension of
its own and no exchange rates. Because angles are a dimension, `rad/s` is an angular velocity while
`1/s` is a frequency:

```
db(100)                    # 20 dB
dbm(1 W)                   # 30 dBm
convert 3000 rpm -> rad/s  # 314.1592654 rad/s
```

Built-in constants: `pi e g G R` (physics), `speedOfLight kB NA sigmaSB`, and the aerospace pack
`muEarth rEarth rhoSL pSL TSL`. Your own variables may shadow them.

### Comparing quantities

`< <= > >=` compare two quantities of the same kind and refuse anything else, which is what catches
`3 < 2 m`. When you knowingly want to compare *sizes* — a threshold on a graph, a scale limit — say
so with a magnitude comparison:

```forge
compare_mag(3, 2 m)           # 1, because 3 is the larger number
compare_mag(2 km, 1500 m)     # 1: 2000 vs 1500, so units are converted first
less_mag(3, 2 m)              # false
greater_equal_mag(5 s, 3 kg)  # true
```

`compare_mag` gives `-1`, `0`, or `1`, so it also sorts. The four boolean forms are `less_mag`,
`less_equal_mag`, `greater_mag`, and `greater_equal_mag`. Complex values compare by magnitude; text
and vectors are refused with an explanation. In the Blueprint, a Compare node set to `mag<=`,
`mag<`, `mag>`, or `mag>=` generates the same calls.

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

### Simultaneous systems

Name several equations and several unknowns to solve them together:

```
eq Sum { x + y = s }
eq Diff { x - y = d }
solve Sum, Diff for x, y {
    s = 10 m
    d = 2 m
}
# x = 6 m
# y = 4 m
```

One equation for each unknown. Units are inferred from the relations, so `x + y = s` with `s` in
metres makes both lengths, `x^2 + y^2 = r2` with `r2` in m² makes them lengths, and a product such
as `I3 * 4 ohm = I2 * 3 ohm` makes both currents. A sum whose size is unknown
(`I1 - I2 - I3` against a plain `0`) ties its names to one dimension, which another relation then
settles. Declaring a unit on an unknown (`I1 : A`) overrides the inference and is the clearest way to
write a circuit; an equation that mixes units and a bare `0` is rejected when it is defined, so write
`I1 = I2 + I3` rather than `I1 - I2 - I3 = 0`.

```
eq KCL { I1 : A
    I2 : A
    I3 : A
    I1 = I2 + I3 }
eq Loop { V : V
    I1 : A
    I3 : A
    R1 : ohm
    R3 : ohm
    V = I1 * R1 + I3 * R3 }
eq Mesh { R2 : ohm
    I2 : A
    I3 : A
    R3 : ohm
    I3 * R3 = I2 * R2 }
solve KCL, Loop, Mesh for I1, I2, I3 {
    V = 6 V
    R1 = 2 ohm
    R2 = 3 ohm
    R3 = 4 ohm
}
# I1 = 1.615384615 A
# I2 = 0.9230769231 A
# I3 = 0.6923076923 A
```

Linear and non-linear systems use the same solver: a damped Newton iteration started from one
coherent unit of each unknown's dimension. `--explain` reports which method ran. The solver refuses
the cases that have no single answer: too few equations for the unknowns, a dependent system
(`x + y = s` together with `2*x + 2*y = 2*s`), or an unknown that is also given a value.

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

### Reading and writing data tables

A program can read a CSV file and analyse it without leaving the language. `readtable()` returns a
table: a vector whose first value is the headers and whose following values are the columns.
`csvwrite()` writes that same shape back.

```
t = readtable("measurements.csv")
t[0]                      # <time, distance>     the headers
t[1]                      # <0 s, 1 s, 2 s>     a column, with its units
distance = t[2]
mean(distance)            # 3.666666667 m
linreg(t[1], distance)    # <4 m/s, -0.3333333333 m, 0.9795918367>

csvwrite("reports/summary.csv", t)   # folders are created as needed
```

* Paths are relative to the program being run, and the folder is created when writing.
* A header may declare a unit in brackets, `time [s]`. Every cell in that column is read as that
  quantity, so the column is unit-checked like any other vector. A header without brackets gives
  plain numbers.
* A column holding any non-numeric cell becomes a vector of text.
* Rows must all have the same number of values, and a column cannot mix numbers and text; both are
  reported with the file and the reason.
* `forge browser`'s **Charts** tab reads the same `name [unit]` headers, so a file produced by
  `csvwrite()` opens there directly.

## Solving and optimising

`fzero(f, a, b)` finds a root inside a bracket (the two ends must have opposite signs), and
`minimize(f, a, b)` finds a one-variable minimum. Both accept a function or a bare expression:

```forge
fzero(sin(x), 3, 4)              # 3.141592654
def f(x) { return x^2 - 4 }
fzero(f, 1 m, 3 m)               # 2 m
minimize(x^2 + 1, -5, 5)         # <1.053671203e-08, 1>, the minimum near 0
```

`fminsearch(f, x0)` searches several variables at once and keeps their units, so a fit can be written
with the measurements it fits:

```forge
def error(d, v) { return (d / 1 m - 5)^2 + (v / 1 m/s - 2)^2 }
fminsearch(error, <0 m, 0 m/s>)  # <5 m, 2 m/s>
```

`linprog(cost, A, b)` maximises `cost x` subject to `A x <= b` and `x >= 0`; pass `"min"` as a fourth
argument to minimise instead. The bounds may also ride in the last column of `A`:

```forge
linprog(<3, 2>, [[1, 1], [2, 1]], <4, 6>)        # <<2, 2>, 10>: x + y <= 4, 2x + y <= 6
linprog(<3, 2>, [[1, 1, 4], [2, 1, 6]])          # the same problem, bounds in the matrix
linprog(<2, 1>, [[1, 1]], <3>, "min")            # <<0, 0>, 0>
```

## Domain objects

Three engineering objects are built in. Each bundles named quantities with the formulas that apply
to them, and everything it returns is a quantity, so unit safety holds throughout.

```forge
r = Rocket(dryMass = 1200 kg, propellantMass = 2800 kg, isp = 311 s)
r.wetMass                 # 4000 kg
r.deltaV                  # 3671.958309 m/s, Tsiolkovsky's equation
r.burnTime(50 kN)         # how long the propellant lasts at that thrust
r.gravityLoss(60 s, 9.81 m/s^2)

m = Motor(torque = 2.5 N*m, speed = 3000 rpm)
m.power                   # 785.4 W
m.torqueAt(1500 rpm)      # the torque at another speed, same power

b = Battery(capacity = 5 Ah, voltage = 11.1 V)
b.energy                  # 199800 J
b.runtime(10 A)
b.range(0.15 kWh/km)
```

Properties read like values and formulas with parameters are called: `r.deltaV` is a number,
`r.burnTime(50 kN)` is a call. Arguments and defaults are unit-checked when the object is built.

### Custom objects

Declare your own type with `object`. A typed line is a **property** with a unit and optional default;
a typed line with parentheses is a **formula** that states its result unit.

```forge
object Car {
    description = "A simple electric car"
    mass : kg = 1500 kg "kerb mass"
    v : m/s = 20 m/s
    energy() : J = 0.5 * mass * v^2 "kinetic energy"
    distance(seconds : s) : m = v * seconds "how far it travels"
}

c = Car()                 # uses the defaults
c.mass                    # 1500 kg
c.energy                  # 300000 J
c.distance(3 s)           # 60 m
d = Car(mass = 900 kg)    # a 900 kg car; v keeps its default
d.energy                  # 180000 J
```

* A property without `= default` must be given when the object is built; leaving it out says which
  property is missing.
* A property's default may use constants (`pi`, `g`) but not other properties.
* Formulas see every property and every other formula, so `range` can use `energy`. A name that is
  neither a property, a parameter, nor a formula is refused when the object is *declared*, not at run
  time.
* Declaring a result unit (`energy() : J`) checks the formula: a formula that produces momentum where
  it promised a length is reported as a unit mismatch.
* Parameter units (`seconds : s`) are documentation; they make the intended units clear, and the
  result-unit check enforces the real contract.
* Quoted text after a property or formula documents it, and `description = "..."` documents the type.

Custom objects behave like the built-in ones: they appear in the IDE's **Objects** list with their
properties and defaults, and `Car(...)` works anywhere an expression does.

## Signals

A signal is a vector of samples. `fft()` turns it into a spectrum, `fftfreq()` says which frequency
each bin holds, and a filter works on the samples directly. Transforms accept any length: a power of
two uses the fast radix-2 path, anything else a direct sum.

```forge
t = linspace(0 s, 1 s, 64)
y = sin(2 * pi * 8 Hz * t)
s = fft(y)
f = fftfreq(64, 1 s / 64)
mag(s[8])        # the 8 Hz line; a full-scale tone of 64 samples is about 32
f[8]             # 8 Hz
```

Window first when a tone does not fall on an exact bin, or when you want one step:

```forge
[s2, f2] = spectrum(y, 1 s / 64, "hann")
```

Filters are finite-impulse-response kernels, so they are stable and easy to reason about. The
time step sets the sample rate, and the Nyquist frequency is half of it:

```forge
clean = lowpass(y, 20 Hz, 1 s / 64)              # keep only what is below 20 Hz
edges = highpass(y, 20 Hz, 1 s / 64)
band = bandpass(y, 10 Hz, 30 Hz, 1 s / 64)
convolve(y, <0.5, 0.5>)                         # your own two-tap average
```

Frequency response is returned as gain and phase, ready to plot:

```forge
frequencies = logspace(1, 4, 60)
[gain, phase] = bode(frequencies, 100 Hz)        # 0.707 and -45 deg at the cutoff
[peak, up] = resonance(frequencies, 0.1, 100 Hz) # Q = 5 at resonance
plot(frequencies, gain)
```

### Assigning several results

A function that returns a vector can be unpacked into several names with `[a, b] = ...`, which is
shorter than indexing twice:

```forge
[gain, phase] = bode(frequencies, 100 Hz)
[s, f] = spectrum(y, 1 s / 64)
```

The number of names must match the number of parts.

## Differential equations

`solveODE(f, y0, t0, t1)` integrates `dy/dt = f(t, y)` from `t0` to `t1`, starting at `y0`, and
returns two vectors: the times and the values. Its adaptive Dormand-Prince step keeps the error near
1e-7 and produces about 200 samples, so the result plots directly.

```forge
def accel(t, v) { return -9.81 m/s^2 }
fall = solveODE(accel, 20 m/s, 0 s, 4 s)
n = count(fall[1])
fall[1][n - 1]        # -19.24 m/s, the velocity after four seconds
fall[0][n - 1]        # 4 s
plot(fall[0], fall[1])   # a velocity-versus-time graph
```

The derivative is a function of time first and the value second, `f(t, y)`. A bare expression works
too, using `t` and `y`: `solveODE(-9.81 m/s^2, 20 m/s, 0 s, 4 s)`. Units flow through: the value
carries `y0`'s unit, and the derivative must measure that unit per second, so a derivative in newtons
is reported as a unit mismatch rather than silently accepted.

Decay and growth need a rate constant, which is an inverse unit:

```forge
def dv(t, v) { return -0.5 1/s * v }
r = solveODE(dv, 10 m/s, 0 s, 2 s)     # 10 e^-t, about 3.6788 m/s at t = 2 s
```

### Steady-state fields

`solvePDE(grid)` relaxes a square grid to steady state: every interior cell settles at the average
of its four neighbours, while the edge values are held fixed as boundary conditions. That is
Laplace's equation, which describes a heated plate, an electric potential in a conductor, and steady
seepage alike.

```forge
grid = [[100 degC, 100 degC, 100 degC, 100 degC, 100 degC],
        [0 degC, 0 degC, 0 degC, 0 degC, 0 degC],
        [0 degC, 0 degC, 0 degC, 0 degC, 0 degC],
        [0 degC, 0 degC, 0 degC, 0 degC, 0 degC],
        [0 degC, 0 degC, 0 degC, 0 degC, 0 degC]]
steady = solvePDE(grid)
steady[2][2]                                # 25 °C, halfway into the plate
plot(steady, kind = "heatmap")
```

The grid must be square and at least 3 cells across. The result keeps the grid's units, and it plots
directly as a heatmap. A larger grid is more accurate but slower; pass a cell count as a second
argument to override the grid's own size.

## Optimisation

`fminsearch(cost, start)` minimises a cost over several variables, starting from a vector. The cost
must be a plain number (divide by a reference to remove units), and the answer comes back in the
units of the starting vector:

```forge
def cost(x, y) { return (x - 3)^2 + (y + 1)^2 }
fminsearch(cost, <0, 0>)          # <3, -1>

# With physical variables: find the distance and speed that best fit a model.
def error(d, v) { return (d / 1 m - 5)^2 + (v / 1 m/s - 2)^2 }
fminsearch(error, <0 m, 0 m/s>)   # <5 m, 2 m/s>
```

`linprog(cost, A, b)` solves a linear program: maximise `cost · x` subject to `A x <= b` with every
variable non-negative. `A` may be given without its right-hand side, as rows `[a1, a2, b]`. Pass
`"min"` as a fourth argument to minimise instead:

```forge
linprog(<3, 2>, [[1, 1], [2, 1]], <4, 6>)   # <<2, 2>, 10>
linprog(<3, 2>, [[1, 1, 4], [2, 1, 6]])     # the same, in the augmented form
linprog(<1, 2>, [[1, 1]], <3>, "min")       # <<0, 0>, 0>
```

The result is a vector holding the variable values and then the objective's value there. A program
that is unbounded, or whose bounds are negative, is reported rather than answered wrongly.

For a steady field over a surface — heat conduction, electrostatics, seepage — `solvePDE(grid)`
relaxes a square matrix to its steady state. The edge values are the boundary conditions and the
result keeps their units:

```forge
plate = [[100 C, 100 C, 100 C, 100 C, 100 C],
         [0 C, 0 C, 0 C, 0 C, 0 C],
         [0 C, 0 C, 0 C, 0 C, 0 C],
         [0 C, 0 C, 0 C, 0 C, 0 C],
         [0 C, 0 C, 0 C, 0 C, 0 C]]
steady = solvePDE(plate)
steady[2][2]                     # 25 C, the midpoint of a plate with one warm edge
plot(steady, kind = "heatmap")
```

These are F²ORGE's own names, not MATLAB's: `solveODE` replaces `ode45` and `solvePDE` stands in
for `pdepe`. MATLAB's `solveODE` solves equations symbolically, so this language uses a different word
to avoid suggesting a symbolic engine.

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

## Tracing and profiling

`forge trace FILE.forge` runs a program statement by statement and prints each one as it executes,
with its line and its kind, so a script's real path through its branches and loops is visible:

```text
   1  assignment  total = 0
   2  for         for k in 1..4 {
   3  assignment  total = total + k
   5  if          if total > 5 {
   6  print       print "big"
  10  expression  total
7 statements ran
```

Show only one kind of statement with `--kind`, for example `--kind print`.

`forge profile FILE.forge` reports where the time goes, one row per source line, busiest first.
Each line's count is how many times it actually ran, so a hot loop is obvious. Use `--runs 10` to
repeat a short program enough for the times to mean something:

```text
        ms     calls  line
      0.04         4     3  total = total + k
      0.01         1     1  total = 0
      0.45  total
```

The same facilities are available from Python, which is how the IDEs drive them:
`DebugSession` steps, holds breakpoints, and exposes the current line and variables;
`trace_of()` returns the frames a program ran; and `profile()` returns per-line times and call
counts plus a report.

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

Run `forge ide` to open the offline desktop IDE. It tries an embedded webview first, then the
Tkinter editor, then the browser IDE, so it opens something even when an optional package is
missing; `--ui webview|tk|browser` picks one deliberately. The webview shares the browser IDE
interface and Blueprint implementation and needs `pip install "f2orge[desktop]"`; Windows also
requires the Microsoft WebView2 runtime. The Tkinter editor is Python's built-in GUI and needs no
other package. Open or save
`.forge` and `.eq` files, then
press **Run** or **F5** to execute it. The workspace shows variables and equations; the command
window runs expressions and assignments in the same session, with Up/Down command history. Use
`plot(y)` or `plot(x, y)` on vector variables to open a native plot window, and a `plot` statement
in a script opens its graph after the run. `:clear` resets the
workspace. The IDE serves its bundled UI on loopback and runs locally without an internet connection.
The **Blueprint** tab provides a graph-paper canvas with Input, Constant,
Function, Call, Compare, arithmetic, Script, Output, and two-output nodes. Connect output pins to input pins, then select **Run Graph**
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
cloud service or remote assets. It includes a script editor, command window, workspace list (with a
live **Objects** group for domain types), **Trace** and **Profile** buttons that report what the
current script runs and where its time goes (the same reports `forge trace` and `forge profile`
print), and a Blueprint canvas with draggable, connectable, deletable, resizable nodes. A **Script** node accepts
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

One `solve` handles one equation, or one system of equations: `solve A, B for x, y` names several
equations and several unknowns and solves them together. Matrix values remain program values, not
equation outputs or solver relations.
