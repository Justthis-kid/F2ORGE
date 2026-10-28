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

Standard library: `Force KineticEnergy Bernoulli DeltaV IdealGas Ohm Lift CircularOrbit`.
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

## Not in v0.1 (planned)

Interactive graphs, generated calculators and live updates, matrices and vectors,
domain objects (`rocket`, `motor`, `battery`), worksheets, a package marketplace. Simultaneous
equation systems are not solved yet; each `solve` handles one chain of single-unknown relations.
