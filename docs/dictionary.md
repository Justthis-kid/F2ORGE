# F²ORGE language dictionary

This glossary collects the names and terms used by the implemented language. It is not a promise of
support for unlisted or planned syntax. For examples in sequence, read the
[tutorial](tutorial.md); for complete expression and equation rules, see the
[language reference](language.md).

## Language terms

| Term | Meaning |
|---|---|
| **Assignment** | `name = expression` binds or replaces a variable in the current interpreter workspace. |
| **Dimension** | The physical kind of a quantity, represented by powers of SI base dimensions. |
| **Dimensionless** | A pure number, or a ratio whose physical dimensions cancel. Angles are dimensionless here. |
| **Equation** | A named formula group declared with `eq`; its inputs and outputs are inferred from relations. |
| **Engineering worksheet** | A native `worksheet` block defining unit-checked inputs, calculated outputs, metadata, and optional graph sweeps for live IDE interaction. |
| **Equation input** | A variable used by an equation but not defined by one of its relations. |
| **Equation output** | A name defined on the left side of a simple equation relation. |
| **Implicit relation** | A relation with a non-name left side, useful in `solve` blocks but not callable as an ordinary output formula. |
| **Quantity** | A numeric magnitude paired with a dimension and display unit. |
| **SI magnitude** | The value after converting a quantity to coherent SI units; conversions and calculations operate on this representation. |
| **Unit declaration** | `name : unit` inside an equation; documents a variable and enables equation/call dimensional checks. |
| **Unit literal** | A number followed by a unit, such as `9.81 m/s^2`. |
| **Affine temperature** | An absolute scale with an offset, such as `degC` or `degF`; it is not interchangeable with a temperature difference. |
| **Sweep** | Repeated evaluation of an equation over a range of one declared input for graphing. |
| **Calculator input** | A declared equation input field; calculators require a unit declaration to validate values. |
| **Workspace** | The variables and equations held by a running CLI or IDE interpreter session. |
| **Chart Studio** | The IDE's local table editor and chart panel for creating 2D and 3D visualizations from CSV-style data. |
| **Table chart** | A line, scatter/point, bar, or 3D plot whose series are selected from table columns. |
| **Surface grid** | A complete rectangular set of X/Y coordinate pairs with exactly one Z value per pair. |

## Statements and keywords

| Word / form | Use |
|---|---|
| `eq` | Begin an equation definition: `eq Force { ... }`. |
| `worksheet` | Begin an IDE-backed engineering worksheet: `worksheet Flight { ... }`. |
| `input` | Declare a worksheet input with a unit and default, such as `input mass : kg = 150 kg`. |
| `output` | Calculate a named worksheet result, such as `output force = mass * acceleration`. |
| `graph` | Sweep a worksheet input and graph an output: `graph force over acceleration from 0 m/s^2 to 20 m/s^2`. |
| `over`, `from`, `to` | Specify the input being swept and the two range endpoints of a worksheet graph. |
| `solve` | Start a solve request: `solve Force for a { F = 100 N; m = 50 kg }`. |
| `for` | Name the unknown in a `solve` statement. It does not introduce a loop. |
| `import` | Load an equation by library name or `.eq` path. |
| `export` | Write a named equation to a `.eq` file. |
| `convert` | Convert a quantity: `convert 10 ft -> m`. |
| `print` | Write values and quoted strings to program output. |
| `description` | Conventional equation metadata key consumed by equation documentation generation. |
| `ans` | Workspace value set when a bare expression or `convert` statement is evaluated. |

General conditional and looping statements are not part of the current language.

## Operators and punctuation

| Symbol | Meaning |
|---|---|
| `=` | Assignment, or equality/relation inside an equation and solve block. |
| `+`, `-` | Addition and subtraction; quantities must have compatible dimensions. |
| `*` | Scalar multiplication; vector dot product; matrix, matrix-vector, or vector-matrix product. |
| `/` | Scalar division, or vector/matrix scaling by a scalar quantity. |
| `^` | Exponentiation; right-associative. |
| `(...)` | Group an expression or call a built-in/equation with named arguments. |
| `<...>` | Vector literal, for example `<1, 2, 3>`. |
| `[[...], [...]]` | Matrix literal; rows must have equal lengths. Newlines may separate rows. |
| `:` | Unit declaration in an equation, as in `m : kg`. |
| `->` | Conversion destination, as in `convert 10 ft -> m`. |
| `.` | Select a named equation output, such as `Force(...).F`. |
| `,` | Separate call arguments, print items, vector/matrix values, or solve givens. |
| `;` | Separate statements on one line or givens inside a solve block. |
| `#`, `//` | Begin a line comment. |

Unicode operator alternatives include `×`, `·`, `÷`, `−`, and `→`; superscript exponents such as
`m²` are accepted. To avoid ambiguity between a quantity and a multiplication expression, write
unit compounds tightly (`kg*m/s^2`) and expression operators with spaces (`10 m / 2 s`).

## Built-in functions

| Function | Meaning and constraints |
|---|---|
| `sin(x)`, `cos(x)`, `tan(x)` | Trigonometric functions. Input must be dimensionless; `deg` and `rad` are available angle scales. |
| `asin(x)`, `acos(x)`, `atan(x)` | Inverse trigonometric functions; return a dimensionless radian value. `asin` and `acos` require inputs in `[-1, 1]`. |
| `atan2(y, x)` | Two-input angle; both values must have matching dimensions. |
| `exp(x)` | Exponential function; input must be dimensionless. |
| `ln(x)` | Natural logarithm; input must be positive and dimensionless. |
| `log(x)` | Base-10 logarithm; input must be positive and dimensionless. |
| `sqrt(x)` | Square root of a nonnegative quantity. |
| `abs(x)` | Absolute magnitude of a scalar quantity. |
| `min(a, b, ...)`, `max(a, b, ...)` | Select among two or more compatible scalar quantities. |
| `transpose(A)` | Transpose matrix `A`. |
| `inverse(A)` | Invert a square, dimensionless matrix; singular matrices are rejected. |

User-defined equation calls use the equation's name and named inputs, not positional arguments:
`Force(m = 2 kg, a = 3 m/s^2)`.

## Built-in constants

| Name | Meaning | Dimension |
|---|---|---|
| `pi` | Circle constant π | Dimensionless |
| `e` | Euler's number | Dimensionless |
| `g` | Standard gravity | Acceleration |
| `G` | Newtonian gravitational constant | `N·m²/kg²` |
| `R` | Molar gas constant | `J/(mol·K)` |
| `speedOfLight` | Speed of light in vacuum | Speed |
| `kB` | Boltzmann constant | `J/K` |
| `NA` | Avogadro constant | `1/mol` |
| `sigmaSB` | Stefan–Boltzmann constant | `W/(m²·K⁴)` |
| `muEarth` | Earth gravitational parameter | `m³/s²` |
| `rEarth` | Earth equatorial radius | Length |
| `rhoSL` | ISA sea-level density | `kg/m³` |
| `pSL` | ISA sea-level pressure | Pressure |
| `TSL` | ISA sea-level temperature | Temperature |

The Mathematics pack is `pi`, `e`; Physics is `g`, `G`, `R`, `speedOfLight`, `kB`, `NA`, `sigmaSB`;
the Aerospace pack is `muEarth`, `rEarth`, `rhoSL`, `pSL`, `TSL`. Names are case-sensitive. A
top-level variable can shadow a constant; inside an equation, declare a same-named variable (for
example `R : ohm`) to make it an input.

## Built-in unit catalog

The following are base names, aliases, and prefixes recognized by the current unit registry. Units
may be combined into compounds such as `N*m`, `kg/m^3`, and `W/(m*K)`. Run `forge units` for the
authoritative list in an installed version and `forge units FILTER` to narrow it.

| Kind | Unit names and aliases |
|---|---|
| Length | `m`, `in` (`inch`), `ft` (`foot`, `feet`), `yd`, `mi`, `nmi` |
| Mass | `g`, `kg` (prefix + gram), `lb` (`lbm`, `lbs`), `oz`, `slug`, `t` (`tonne`) |
| Time | `s` (`sec`), `min`, `h` (`hr`), `day` |
| Frequency | `Hz` |
| Force | `N`, `lbf`, `kgf`, `dyn` |
| Energy | `J`, `cal`, `BTU` (`Btu`), `Wh`, `eV`, `ftlbf` |
| Power | `W`, `hp` |
| Pressure | `Pa`, `bar`, `atm`, `psi`, `ksi`, `torr`, `mmHg`, `inHg` |
| Temperature | `K`, `degC` (`°C`, `celsius`), `degF` (`°F`), `degR` |
| Electrical | `A`, `V`, `ohm` (`Ω`, `Ohm`), `F`, `H`, `C`, `S`, `Wb`, `T` |
| Amount | `mol` |
| Volume | `L` (`l`), `gal`, `qt` |
| Speed | `mph`, `kph`, `kn` (`knot`) |
| Angle | `rad`, `deg` (`°`) |

Prefixes supported for prefixable units are `T` (tera), `G` (giga), `M` (mega), `k` (kilo),
`c` (centi), `m` (milli), `u` or `µ` (micro), `n` (nano), `p` (pico), and `f` (femto). The exact
unit name is checked before interpreting a prefix, so `min` is minute, not milli-inch. Prefix
support is unit-specific; `forge units` reports available names.

## Common dimensions

| Dimension | SI relationship | Named unit example |
|---|---|---|
| Length | `m` | `km` |
| Mass | `kg` | `g` |
| Time | `s` | `min` |
| Area | `m²` | `cm²` |
| Volume | `m³` | `L` |
| Speed | `m/s` | `mph` |
| Acceleration | `m/s²` | — |
| Force | `kg·m/s²` | `N` |
| Energy / work | `N·m` | `J` |
| Power | `J/s` | `W` |
| Pressure | `N/m²` | `Pa` |
| Temperature | `K` | `degC`, `degF` |
| Electric current | `A` | `mA` |
| Voltage | `W/A` | `V` |
| Resistance | `V/A` | `ohm` |
| Frequency | `1/s` | `Hz` |

Names such as `force`, `energy`, or `acceleration` are explanatory labels in diagnostics and
documentation; units still derive from their dimensions.

## CLI vocabulary

| Command | Purpose |
|---|---|
| `forge run FILE.forge` | Run a source file. `--explain` displays solver rearrangements. |
| `forge shell` | Start the interactive language shell. |
| `forge check FILE...` | Validate equation files/program equation definitions without executing ordinary statements. |
| `forge doc EQUATION` | Generate documentation from equation metadata and declarations. |
| `forge units [FILTER]` | List built-in units. |
| `forge graph EQUATION ...` | Sweep an equation input and export a graph. `--interactive` writes standalone HTML. |
| `forge calc EQUATION ...` | Create an offline HTML calculator; `--terminal` opens a terminal calculator. |
| `forge plot FILE.forge Y [--x X]` | Plot vector variables created by a script. |
| `forge transpile FILE --target TARGET` | Generate supported scalar code for Python, C++, MicroPython, or TI-84 BASIC. |
