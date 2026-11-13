"""Recursive-descent parser.

Expression precedence, lowest to highest:

    or   <   and   <   not   <   comparisons   <   + -   <   * /   <   unary -   <   ^ (right-assoc)

A number immediately followed by a unit name is a quantity literal:  9.81 m/s^2.  Inside such
a unit the operators must touch their operands (m/s^2, not m / s^2) so that
`10 m / 2 s` still means (10 m) / (2 s).  Declarations and `convert` targets run to the end of
the line, so they may be written with spaces.

Blocks (`eq`, `worksheet`, `if`, `while`, `for`, `def`) use braces.  Inside parentheses and
brackets a newline is insignificant.
"""
from __future__ import annotations

from fractions import Fraction
from typing import List, Optional, Tuple

from . import syntax as S
from .errors import ForgeNameError, ForgeSyntaxError, Source, Span
from .lexer import KEYWORDS, Token, tokenize
from .units import Unit, UnknownUnit, lookup_unit, suggest_units

Atom = Tuple[str, Fraction, Span]


def is_literal(node) -> bool:
    """A value written out in full: `[1, 2]` after such a value is a new list, not an index."""
    return isinstance(node, (S.Number, S.QuantityLit, S.StringLit, S.VectorLiteral,
                             S.MatrixLiteral, S.ListLiteral))


class Parser:
    def __init__(self, source: Source):
        self.source = source
        self.toks = tokenize(source)
        self.i = 0
        self.depth = 0  # >0 inside ( ) or < >: newlines are then ignored
        self.last_end = 0
        self._count = None  # the n of a counted selection M[:, j:j+n]
        self.vector_depth = 0  # >0 inside <...>: its '>' closes a vector instead of comparing

    # ---- token access ----------------------------------------------------------------------
    def _index(self, k: int = 0) -> int:
        i, count, last = self.i, 0, len(self.toks) - 1
        while True:
            if count == k:
                return min(i, last)
            i += 1
            if i > last:
                return last
            if self.depth > 0 and self.toks[i].kind == "nl":
                continue
            count += 1

    def peek(self, k: int = 0) -> Token:
        return self.toks[self._index(k)]

    def peek_raw(self, k: int = 0) -> Token:
        """Look ahead token by token, so a lookahead can see where a line ends."""
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def next(self) -> Token:
        idx = self._index(0)
        tok = self.toks[idx]
        if tok.kind != "eof":
            self.i = idx + 1
            self.last_end = tok.end
        return tok

    def is_op(self, text: str, k: int = 0) -> bool:
        t = self.peek(k)
        return t.kind == "op" and t.text == text

    def skip_nl(self) -> None:
        while self.toks[self.i].kind == "nl":
            self.i += 1

    def skip_separators(self, extra: str = ";") -> None:
        while True:
            t = self.toks[self.i]
            if t.kind == "nl" or (t.kind == "op" and t.text in extra):
                self.i += 1
            else:
                return

    def span_from(self, start: int) -> Span:
        return Span(self.source, start, max(self.last_end, start))

    @staticmethod
    def describe(tok: Token) -> str:
        if tok.kind == "nl":
            return "the end of the line"
        if tok.kind == "eof":
            return "the end of the file"
        return f"'{tok.text}'"

    def fail(self, message: str, where, hint: Optional[str] = None):
        """Report a syntax error at a token, a node's span, or the end of the last token read."""
        if isinstance(where, Span):
            span = where
        elif hasattr(where, "span") and isinstance(where.span, Span):
            span = where.span
        elif hasattr(where, "start"):
            span = Span(self.source, where.start, max(where.end, where.start + 1))
        else:
            span = Span(self.source, self.last_end, max(self.last_end + 1, self.last_end))
        raise ForgeSyntaxError(message, span, hint=hint)

    def expect_op(self, text: str, message: Optional[str] = None, hint: Optional[str] = None) -> Token:
        t = self.peek()
        if t.kind == "op" and t.text == text:
            return self.next()
        self.fail(message or f"Expected '{text}' but found {self.describe(t)}", t, hint)

    def expect_ident(self, what: str) -> Token:
        t = self.peek()
        if t.kind != "ident" or t.text in KEYWORDS:
            self.fail(f"Expected {what} but found {self.describe(t)}", t)
        return self.next()

    # ---- program and statements ------------------------------------------------------------
    def parse_program(self) -> List[object]:
        stmts: List[object] = []
        self.skip_separators()
        while self.peek().kind != "eof":
            stmts.append(self.statement())
            t = self.peek()
            if t.kind not in ("nl", "eof") and not (t.kind == "op" and t.text == ";"):
                self.fail(f"Unexpected {self.describe(t)}; a statement should end here", t,
                          "Put each statement on its own line, or separate them with ';'.")
            self.skip_separators()
        return stmts

    def statement(self):
        t = self.peek()
        if t.kind == "ident":
            kw = t.text
            if kw == "eq":
                return self.eq_def()
            if kw == "worksheet":
                return self.worksheet_def()
            if kw == "object":
                return self.object_def()
            if kw == "import":
                return self.import_stmt()
            if kw == "export":
                return self.export_stmt()
            if kw == "solve":
                return self.solve_stmt()
            if kw == "convert":
                return self.convert_stmt()
            if kw == "print":
                return self.print_stmt()
            if kw == "plot":
                return self.plot_stmt()
            if kw in ("if", "for", "while", "def", "fn"):
                return self.block_statement()
            if kw in ("return", "break", "continue"):
                return self.flow_statement()
            if kw in ("elseif", "else"):
                self.fail(f"'{kw}' must follow an if block on its own line", t,
                          "Write 'elseif condition {' or 'else {' directly after the previous block.")
            if self.is_op("=", 1):
                return self.assign()
        if t.kind == "op" and t.text == "[":
            names = self.names_until_bracket()
            if names is not None:
                return names
        expr = self.expression()
        return S.ExprStmt(expr, expr.span)

    def range_expression(self):
        """Loop values: 1..10, a value with a step (1..10..2), or a comma list (0, 2, 10)."""
        start = self.expression()
        if self.is_op(".."):
            self.next()
            self.skip_nl()
            stop = self.expression()
            step = None
            if self.is_op(".."):
                self.next()
                self.skip_nl()
                step = self.expression()
            return S.Range(start, stop, step, self._join(start, step or stop))
        if self.is_op(","):
            items = [start]
            while self.is_op(","):
                self.next()
                self.skip_nl()
                if self.is_op("{"):
                    break
                items.append(self.expression())
            return S.VectorLiteral(tuple(items), self._join(items[0], items[-1]))
        return start

    def block_statement(self):
        t = self.peek()
        if t.text == "if":
            return self.if_stmt()
        if t.text == "for":
            return self.for_stmt()
        if t.text == "while":
            return self.while_stmt()
        return self.def_stmt()

    def flow_statement(self):
        t = self.next()
        if t.text == "return":
            nxt = self.peek()
            if nxt.kind in ("nl", "eof") or (nxt.kind == "op" and nxt.text in ";}"):
                self.fail("Expected a value to return", nxt, "Write: return expression")
            return S.Return(self.expression(), self.span_from(t.start))
        if t.text == "break":
            return S.Break(self.span_from(t.start))
        return S.Continue(self.span_from(t.start))

    def block(self, opener: Token, what: str) -> Tuple[object, ...]:
        """Parse '{ statements }' for a control-flow block."""
        while self.peek().kind == "nl":
            self.next()
        self.expect_op("{", f"Expected '{{' to start the {what} body",
                       f"Write: {what} {{ ... }}")
        body = self.statements_until_brace(opener, what)
        self.expect_op("}")
        return tuple(body)

    def statements_until_brace(self, opener: Token, what: str) -> List[object]:
        body: List[object] = []
        while True:
            self.skip_separators()
            if self.is_op("}"):
                return body
            if self.peek().kind == "eof":
                self.fail(f"This {what} is missing its closing '}}'", opener)
            body.append(self.statement())
            if self.is_op("}"):
                continue
            t = self.peek()
            if not (t.kind == "nl" or (t.kind == "op" and t.text in (";", "}"))):
                self.fail(f"Unexpected {self.describe(t)}; a statement should end here", t,
                          "Put each statement on its own line, or separate them with ';'.")

    def if_stmt(self):
        kw = self.next()
        self.depth += 1  # a condition may wrap onto the next line before its '{'
        try:
            return self._if_branches(kw)
        finally:
            self.depth -= 1

    def _if_branches(self, kw):
        branches: List[Tuple[object, Tuple[object, ...]]] = []
        condition = self.expression()
        branches.append((condition, self.block(kw, "if")))
        while True:
            self.skip_nl()
            t = self.peek()
            if t.kind == "ident" and t.text == "elseif":
                self.next()
                condition = self.expression()
                branches.append((condition, self.block(t, "elseif")))
                continue
            if t.kind == "ident" and t.text == "else":
                self.next()
                branches.append((None, self.block(t, "else")))
            break
        return S.If(tuple(branches), self.span_from(kw.start))

    def while_stmt(self):
        kw = self.next()
        self.depth += 1
        try:
            condition = self.expression()
        finally:
            self.depth -= 1
        return S.While(condition, self.block(kw, "while"), self.span_from(kw.start))

    def for_stmt(self):
        kw = self.next()
        name = self.expect_ident("a loop variable name")
        t = self.peek()
        if t.kind == "ident" and t.text == "in":
            self.next()
            iterable = self.range_expression()
        elif self.is_op("="):  # MATLAB-style counter: for k = 1..10
            self.next()
            iterable = self.range_expression()
        else:
            self.fail("Expected 'in' and the values to loop over", t,
                      f"Write: for {name.text} in 1..10 {{ ... }} or for {name.text} = 1..10 {{ ... }}")
        body = self.block(kw, "for")
        return S.For(name.text, iterable, body, self.span_from(kw.start),
                     Span(self.source, name.start, name.end))

    def def_stmt(self):
        kw = self.next()
        name = self.expect_ident("a function name")
        self.expect_op("(", f"Expected '(' after the function name '{name.text}'",
                       f"Write: def {name.text}(x) {{ ... }}")
        self.depth += 1
        params: List[str] = []
        default = None
        while not self.is_op(")"):
            p = self.expect_ident("a parameter name")
            if p.text in params:
                self.fail(f"parameter '{p.text}' is listed twice", p)
            params.append(p.text)
            if self.is_op(":"):  # what the parameter measures: def area(r : m) { ... }
                self.next()
                self.parse_unit_atoms(tight=False)
            if self.is_op("="):
                self.next()
                default = self.expression()
                if not self.is_op(")"):
                    self.fail("only the last parameter can have a default value", self.peek())
                break
            if not self.is_op(","):
                break
            self.next()
        self.expect_op(")", "Expected ',' or ')' in this parameter list")
        self.depth -= 1
        body = self.block(kw, "function")
        return S.Def(name.text, tuple(params), default, body, self.span_from(kw.start),
                     Span(self.source, name.start, name.end))

    def names_until_bracket(self):
        """`[a, b] = call(...)`: bind the parts of one returned value to several names.

        Returns None (leaving the parser where it started) when the brackets hold values rather
        than a list of names, so `<1, 2>` and `v[0]` keep their usual meaning.
        """
        start = self.i
        try:
            self.expect_op("[")
            self.depth += 1
            names: List[Token] = []
            while True:
                names.append(self.expect_ident("a variable name"))
                if self.is_op(","):
                    self.next()
                    continue
                break
            self.expect_op("]", "Expected ']' to close the list of names",
                           "Write: [a, b] = call(...)")
            self.depth -= 1
            self.expect_op("=", "Expected '=' after the list of names")
        except ForgeSyntaxError:
            self.i = start
            self.depth = 0
            return None
        self.skip_nl()
        self.header = True
        try:
            expr = self.expression()
        finally:
            self.header = False
        return S.MultiAssign(tuple(name.text for name in names), expr, self.span_from(names[0].start))

    def assign(self):
        name = self.next()
        self.next()  # '='
        self.skip_nl()
        expr = self.expression()
        if isinstance(expr, S.StringLit):
            self.fail("Text cannot be assigned to a variable", expr,
                      'Text is used in print and equation metadata, not stored: write print "hi".')
        return S.Assign(name.text, expr, self.span_from(name.start))

    def import_stmt(self):
        kw = self.next()
        t = self.peek()
        if t.kind != "path":
            self.fail("Expected an equation name or a file path after 'import'", kw,
                      "For example: import Force   or   import ./formulas/Force.eq")
        self.next()
        raw = t.text
        is_path = "/" in raw or "\\" in raw or raw.endswith(".eq") or raw.startswith(".")
        if not is_path and not raw.replace("_", "a").isalnum():
            self.fail(f"'{raw}' is not a valid equation name", t, "Use a name like Force, or a path like ./Force.eq")
        return S.Import(raw, is_path, self.span_from(kw.start))

    def export_stmt(self):
        kw = self.next()
        name = self.expect_ident("the name of the equation to export")
        return S.Export(name.text, self.span_from(kw.start))

    def print_stmt(self):
        kw = self.next()
        items: List[object] = []
        while True:
            t = self.peek()
            if t.kind == "str":
                self.next()
                items.append(S.StringLit(t.value, Span(self.source, t.start, t.end)))
            else:
                items.append(self.expression())
            if self.is_op(","):
                self.next()
                continue
            break
        return S.Print(tuple(items), self.span_from(kw.start))

    def plot_stmt(self):
        kw = self.next()
        self.expect_op("(", "Expected '(' after 'plot'", "Write: plot(y) or plot(x, y)")
        self.depth += 1
        args: List[object] = []
        polar = False
        kind = "plot"
        while not self.is_op(")"):
            option = None
            t = self.peek()
            if t.kind == "ident" and t.text in ("polar", "kind") and self.is_op("=", 1):
                self.next()
                self.next()
                option = t.text
            value = self.expression()
            if option == "polar":
                polar = self.bool_option(value, "polar")
            elif option == "kind":
                kind = self.kind_option(value)
            else:
                args.append(value)
            if self.is_op(","):
                self.next()
                continue
            break
        self.expect_op(")", "Expected ')' to close this plot")
        self.depth -= 1
        if not args:
            self.fail("plot() needs a vector to draw", kw, "Write: plot(y) or plot(x, y)")
        if len(args) == 1:
            return S.Plot((args[0],), None, polar, kind, self.span_from(kw.start))
        if kind in ("heatmap", "surface") and len(args) == 3:
            coordinates = S.VectorLiteral((args[0], args[1]))
            return S.Plot((args[2],), coordinates, polar, kind, self.span_from(kw.start))
        return S.Plot(tuple(args[1:]), args[0], polar, kind, self.span_from(kw.start))

    def bool_option(self, value, name: str) -> bool:
        if isinstance(value, S.Name) and value.name in ("true", "false"):
            return value.name == "true"
        self.fail(f"{name} = must be true or false", value)

    def kind_option(self, value) -> str:
        if isinstance(value, S.StringLit) and value.value in ("plot", "line", "heatmap", "surface"):
            return "plot" if value.value == "line" else value.value
        self.fail('kind = must be "plot", "heatmap", or "surface"', value)

    def convert_stmt(self):
        kw = self.next()
        expr = self.expression()
        self.expect_op("->", "Expected '->' and a target unit", "For example: convert 10 ft -> m")
        atoms = self.parse_unit_atoms(tight=False)
        return S.Convert(expr, self.make_unit(atoms), self.span_from(kw.start))

    def solve_stmt(self):
        kw = self.next()
        eq = self.expect_ident("the name of the equation to solve")
        equations = [(eq.text, Span(self.source, eq.start, eq.end))]
        while self.is_op(","):  # solve Ohm, Power for I, R { ... }
            self.next()
            more = self.expect_ident("another equation name")
            equations.append((more.text, Span(self.source, more.start, more.end)))
        t = self.peek()
        if not (t.kind == "ident" and t.text == "for"):
            self.fail("Expected 'for' and the variable to solve for", t,
                      f"Write: solve {eq.text} for x {{ ... }}")
        self.next()
        target = self.expect_ident("the variable to solve for")
        unknowns = [(target.text, Span(self.source, target.start, target.end))]
        while self.is_op(","):
            self.next()
            more = self.expect_ident("another unknown")
            unknowns.append((more.text, Span(self.source, more.start, more.end)))
        self.skip_nl()
        self.expect_op("{", "Expected '{' to start the list of known values",
                       f"Write: solve {eq.text} for {target.text} {{ name = value }}")
        givens: List[Tuple[str, object, Optional[Span]]] = []
        while True:
            self.skip_separators(";,")
            if self.is_op("}"):
                break
            if self.peek().kind == "eof":
                self.fail("This solve block is missing its closing '}'", kw)
            name = self.expect_ident("a variable name")
            self.expect_op("=", f"Expected '=' after '{name.text}'")
            self.skip_nl()
            expr = self.expression()
            givens.append((name.text, expr, Span(self.source, name.start, name.end)))
            t = self.peek()
            if not (t.kind == "nl" or (t.kind == "op" and t.text in ";,}")):
                self.fail(f"Unexpected {self.describe(t)} in the list of known values", t)
        self.expect_op("}")
        span = self.span_from(kw.start)
        if len(equations) > 1 or len(unknowns) > 1:
            return S.SolveSystem(tuple(name for name, _ in equations),
                                 tuple(name for name, _ in unknowns), tuple(givens), span,
                                 tuple(item for _, item in equations),
                                 tuple(item for _, item in unknowns))
        return S.Solve(eq.text, target.text, tuple(givens), span,
                       equations[0][1], unknowns[0][1])

    # ---- equation definitions --------------------------------------------------------------
    def eq_def(self):
        kw = self.next()
        t = self.peek()
        if t.kind != "ident" or t.text in KEYWORDS:
            self.fail("Expected a name for the equation", kw, "For example: eq Force { F = m * a }")
        name = self.next()
        self.skip_nl()
        self.expect_op("{", "Expected '{' to start the equation body")
        items: List[object] = []
        while True:
            self.skip_separators()
            if self.is_op("}"):
                break
            if self.peek().kind == "eof":
                self.fail(f"The equation '{name.text}' is missing its closing '}}'", kw)
            items.append(self.eq_item())
            t = self.peek()
            if not (t.kind == "nl" or (t.kind == "op" and t.text in ";}")):
                self.fail(f"Unexpected {self.describe(t)}; this line of the equation should end here", t)
        self.expect_op("}")
        return S.EqDef(name.text, tuple(items), self.span_from(kw.start), Span(self.source, name.start, name.end))

    def eq_item(self):
        t = self.peek()
        if t.kind == "ident" and self.is_op(":", 1):
            return self.decl()
        if t.kind == "ident" and self.is_op("=", 1):
            j = self._index(0) + 2
            while self.toks[j].kind == "nl":
                j += 1
            if self.toks[j].kind == "str":  # metadata: description = "..."
                self.next()
                self.next()
                self.skip_nl()
                s = self.next()
                return S.Meta(t.text, s.value, self.span_from(t.start))
        start = t.start
        lhs = self.expression()
        self.expect_op("=", "Expected '=' in this equation",
                       "Each line of an equation looks like:  F = m * a")
        self.skip_nl()
        rhs = self.expression()
        return S.Relation(lhs, rhs, self.span_from(start))

    def object_def(self):
        """`object Car { mass : kg = 1200 kg  energy = 0.5 * mass * v^2 }`.

        Properties are declared with a unit and an optional default; formulas are either a value
        (`energy = ...`) or a call with parameters (`range(distance) = ...`).  An optional quoted
        string after a property documents it; `description = "..."` documents the type.
        """
        kw = self.next()
        name = self.expect_ident("a name for the object")
        self.skip_nl()
        self.expect_op("{", "Expected '{' to start the object body")
        properties: List[S.PropertySpec] = []
        formulas: List[S.FormulaSpec] = []
        doc = ""
        while True:
            self.skip_separators()
            if self.is_op("}"):
                break
            if self.peek().kind == "eof":
                self.fail(f"The object '{name.text}' is missing its closing '}}'", kw)
            item = self.object_item(name.text)
            if isinstance(item, S.PropertySpec):
                if any(existing.name == item.name for existing in properties):
                    self.fail(f"'{item.name}' is declared twice in {name.text}", item.span)
                if any(existing.name == item.name for existing in formulas):
                    self.fail(f"'{item.name}' is both a property and a formula", item.span)
                properties.append(item)
            elif isinstance(item, S.FormulaSpec):
                if any(existing.name == item.name for existing in formulas):
                    self.fail(f"'{item.name}' is defined twice in {name.text}", item.span)
                if any(existing.name == item.name for existing in properties):
                    self.fail(f"'{item.name}' is both a property and a formula", item.span)
                formulas.append(item)
            else:
                doc = item
            token = self.peek()
            if not (token.kind == "nl" or (token.kind == "op" and token.text in ";}")):
                self.fail(f"Unexpected {self.describe(token)}; this object item should end here", token)
        self.expect_op("}")
        return S.ObjectDef(name.text, tuple(properties), tuple(formulas), doc, self.span_from(kw.start),
                           Span(self.source, name.start, name.end))

    def formula_after_unit(self, name: Token, unit, span) -> S.FormulaSpec:
        """A formula written `name(...) : result-unit = body`."""
        params: Tuple[str, ...] = ()
        if self.is_op("("):
            self.next()
            self.depth += 1
            names: List[str] = []
            while not self.is_op(")"):
                param = self.expect_ident("a parameter name")
                if param.text in names:
                    self.fail(f"parameter '{param.text}' is listed twice", param)
                names.append(param.text)
                if self.is_op(":"):
                    self.next()
                    self.parse_unit_atoms(tight=False)
                if not self.is_op(","):
                    break
                self.next()
            self.expect_op(")", "Expected ',' or ')' in this parameter list")
            self.depth -= 1
            params = tuple(names)
        self.expect_op("=", f"Expected '=' and the formula for '{name.text}'")
        self.header = True
        try:
            body = self.expression()
        finally:
            self.header = False
        doc = self.next().value if self.peek().kind == "str" else ""
        return S.FormulaSpec(name.text, params, body, doc, unit, span)

    def object_item(self, owner: str):
        """One line of an object body: a documentation line, a property, or a formula."""
        token = self.peek()
        if token.kind == "ident" and token.text == "description" and self.is_op("=", 1):
            self.next()
            self.next()
            self.skip_nl()
            value = self.next()
            if value.kind != "str":
                self.fail("description needs quoted text", value)
            return value.value
        if token.kind != "ident" or token.text in KEYWORDS:
            self.fail(f"Expected a property or formula name in {owner} but found {self.describe(token)}",
                      token)
        if self.is_op(":", 1):
            name = self.next()
            self.next()  # ':'
            unit = self.make_unit(self.parse_unit_atoms(tight=False))
            if self.is_op("("):
                # `energy() : J = ...` is a formula that states its result unit.
                return self.formula_after_unit(name, unit, self.span_from(name.start))
            default = None
            if self.is_op("="):
                self.next()
                self.skip_nl()
                default = self.expression()
            doc = self.next().value if self.peek().kind == "str" else ""
            return S.PropertySpec(name.text, unit, default, doc, self.span_from(name.start))
        start = token.start
        name = self.next()
        params: Tuple[str, ...] = ()
        if self.is_op("("):
            self.next()
            self.depth += 1
            names: List[str] = []
            while not self.is_op(")"):
                param = self.expect_ident("a parameter name")
                if param.text in names:
                    self.fail(f"parameter '{param.text}' is listed twice", param)
                names.append(param.text)
                if self.is_op(":"):
                    self.next()
                    self.parse_unit_atoms(tight=False)
                if not self.is_op(","):
                    break
                self.next()
            self.expect_op(")", "Expected ',' or ')' in this parameter list")
            self.depth -= 1
            params = tuple(names)
        result_unit = None
        if self.is_op(":"):  # the formula's result unit: `distance(t) : m = v * t`
            self.next()
            result_unit = self.make_unit(self.parse_unit_atoms(tight=False))
        self.expect_op("=", f"Expected ':' (a unit) or '=' (a formula) after '{name.text}'",
                       f"Write: {name.text} : kg   or   {name.text} = ...")
        self.header = True
        try:
            body = self.expression()
        finally:
            self.header = False
        doc = self.next().value if self.peek().kind == "str" else ""
        return S.FormulaSpec(name.text, params, body, doc, result_unit, self.span_from(start))

    def worksheet_def(self):
        kw = self.next()
        name = self.expect_ident("a name for the worksheet")
        self.skip_nl()
        self.expect_op("{", "Expected '{' to start the worksheet body")
        items: List[object] = []
        while True:
            self.skip_separators()
            if self.is_op("}"):
                break
            if self.peek().kind == "eof":
                self.fail(f"The worksheet '{name.text}' is missing its closing '}}'", kw)
            items.append(self.worksheet_item())
            token = self.peek()
            if not (token.kind == "nl" or (token.kind == "op" and token.text in ";}")):
                self.fail(f"Unexpected {self.describe(token)}; this worksheet item should end here", token)
        self.expect_op("}")
        return S.WorksheetDef(name.text, tuple(items), self.span_from(kw.start),
                              Span(self.source, name.start, name.end))

    def worksheet_item(self):
        token = self.peek()
        if token.kind == "ident" and token.text == "input":
            start = self.next()
            name = self.expect_ident("an input name")
            self.expect_op(":", f"Expected ':' after input '{name.text}'")
            unit = self.make_unit(self.parse_unit_atoms(tight=False))
            self.expect_op("=", f"Expected '=' and a default value for input '{name.text}'")
            self.skip_nl()
            default = self.expression()
            doc = self.next().value if self.peek().kind == "str" else None
            return S.WorksheetInput(name.text, unit, default, doc, self.span_from(start.start))
        if token.kind == "ident" and token.text == "output":
            start = self.next()
            name = self.expect_ident("an output name")
            self.expect_op("=", f"Expected '=' after output '{name.text}'")
            self.skip_nl()
            expression = self.expression()
            return S.WorksheetOutput(name.text, expression, self.span_from(start.start))
        if token.kind == "ident" and token.text == "graph":
            start = self.next()
            output = self.expect_ident("an output to graph")
            over = self.peek()
            if over.kind != "ident" or over.text != "over":
                self.fail("Expected 'over' and the input to sweep", over)
            self.next()
            variable = self.expect_ident("an input to sweep")
            from_token = self.peek()
            if from_token.kind != "ident" or from_token.text != "from":
                self.fail("Expected 'from' and the start of the sweep", from_token)
            self.next()
            start_value = self.expression()
            to_token = self.peek()
            if to_token.kind != "ident" or to_token.text != "to":
                self.fail("Expected 'to' and the end of the sweep", to_token)
            self.next()
            stop_value = self.expression()
            return S.WorksheetGraph(output.text, variable.text, start_value, stop_value,
                                    self.span_from(start.start))
        if token.kind == "ident" and self.is_op("=", 1):
            j = self._index(0) + 2
            while self.toks[j].kind == "nl":
                j += 1
            if self.toks[j].kind == "str":
                key = self.next()
                self.next()
                self.skip_nl()
                value = self.next()
                return S.Meta(key.text, value.value, self.span_from(key.start))
        self.fail("Expected input, output, graph, or worksheet metadata", token)

    def decl(self):
        name = self.next()
        self.next()  # ':'
        atoms = self.parse_unit_atoms(tight=False)
        doc = None
        if self.peek().kind == "str":
            doc = self.next().value
        return S.Decl(name.text, self.make_unit(atoms), doc, self.span_from(name.start))

    # ---- units -----------------------------------------------------------------------------
    def make_unit(self, atoms: List[Atom]) -> Unit:
        for name, _, span in atoms:
            self.check_unit(name, span)
        try:
            return Unit.from_atoms([(n, e) for n, e, _ in atoms])
        except UnknownUnit as err:  # pragma: no cover - guarded by check_unit
            raise ForgeNameError(f"'{err.name}' is not a known unit", title="Unknown unit")

    def check_unit(self, name: str, span: Span, hint: Optional[str] = None) -> None:
        if lookup_unit(name) is None and name != "dimensionless":
            close = suggest_units(name)
            parts = []
            if close:
                parts.append("Did you mean " + " or ".join(f"'{c}'" for c in close) + "?")
            if hint:
                parts.append(hint)
            raise ForgeNameError(f"'{name}' is not a known unit", span, hint=" ".join(parts) or None,
                                 title="Unknown unit")

    def continues_unit(self, tight: bool, op: Token) -> bool:
        nxt = self.peek(1)
        if tight:
            if op.start != self.last_end or nxt.start != op.end:
                return False
            if nxt.kind == "ident":
                return lookup_unit(nxt.text) is not None or nxt.text == "dimensionless"
            return nxt.kind == "op" and nxt.text == "(" and op.text == "/"
        return nxt.kind in ("ident", "num") or (nxt.kind == "op" and nxt.text == "(")

    def parse_unit_atoms(self, tight: bool) -> List[Atom]:
        atoms = self.unit_term(tight, 1)
        while True:
            op = self.peek()
            if op.kind == "op" and op.text in ("*", "/") and self.continues_unit(tight, op):
                self.next()
                atoms += self.unit_term(tight, 1 if op.text == "*" else -1)
            else:
                return atoms

    def unit_term(self, tight: bool, sign: int) -> List[Atom]:
        t = self.next()
        if t.kind == "op" and t.text == "(":
            self.depth += 1
            atoms = self.parse_unit_atoms(False)
            self.expect_op(")")
            self.depth -= 1
        elif t.kind == "ident":
            if t.text == "dimensionless":
                atoms = []
            else:
                span = Span(self.source, t.start, t.end)
                self.check_unit(t.text, span)
                atoms = [(t.text, Fraction(1), span)]
        elif t.kind == "num" and t.text == "1":
            atoms = []
        else:
            self.fail(f"Expected a unit but found {self.describe(t)}", t, "For example: kg, m/s^2 or N*m")
        exp = self.unit_exponent(tight)
        mult = sign * (exp if exp is not None else 1)
        return [(n, e * mult, sp) for n, e, sp in atoms]

    def unit_exponent(self, tight: bool) -> Optional[Fraction]:
        t = self.peek()
        if t.kind == "super" and (not tight or t.start == self.last_end):
            self.next()
            return Fraction(t.value)
        if t.kind == "op" and t.text == "^" and (not tight or t.start == self.last_end):
            self.next()
            sign = 1
            if self.is_op("-") or self.is_op("+"):
                sign = -1 if self.next().text == "-" else 1
            t = self.peek()
            if t.kind == "num":
                self.next()
                return sign * Fraction(t.text.replace("_", ""))
            if t.kind == "op" and t.text == "(":
                self.next()
                self.depth += 1
                inner_sign = -1 if self.is_op("-") and self.next() else 1
                num = self.next()
                value = Fraction(num.text.replace("_", "")) if num.kind == "num" else self.fail(
                    "Expected a number in the exponent", num)
                if self.is_op("/"):
                    self.next()
                    den = self.next()
                    if den.kind != "num":
                        self.fail("Expected a number after '/' in the exponent", den)
                    value = value / Fraction(den.text.replace("_", ""))
                self.expect_op(")")
                self.depth -= 1
                return sign * inner_sign * value
            self.fail(f"Expected a number for the exponent but found {self.describe(t)}", t)
        return None

    # ---- expressions -----------------------------------------------------------------------
    @staticmethod
    def _join(a, b) -> Optional[Span]:
        if a.span is not None and b.span is not None:
            return a.span.join(b.span)
        return a.span or b.span

    @staticmethod
    def is_word(node, word: str) -> bool:
        return isinstance(node, S.Name) and node.name == word

    def expression(self):
        left = self.and_expression()
        while self.is_word(self.peek(), "or"):
            self.next()
            self.skip_nl()
            right = self.and_expression()
            left = S.Binary("or", left, right, self._join(left, right))
        return left

    def and_expression(self):
        left = self.not_expression()
        while self.is_word(self.peek(), "and"):
            self.next()
            self.skip_nl()
            right = self.not_expression()
            left = S.Binary("and", left, right, self._join(left, right))
        return left

    def not_expression(self):
        if self.is_word(self.peek(), "not"):
            op = self.next()
            operand = self.not_expression()
            span = Span(self.source, op.start, operand.span.end if operand.span else op.end)
            return S.Unary("not", operand, span)
        return self.comparison()

    _COMPARISONS = ("==", "!=", "<=", ">=", "<", ">")

    def comparison(self):
        left = self.expression_body()
        if (self.is_op("<") or self.is_op(">")) and self.is_op("=", 1):
            self.next()
            self.next()
            self.skip_nl()
            right = self.expression_body()
            return S.Binary("<=" if self.toks[self.i - 2].text == "<" else ">=", left, right,
                            self._join(left, right))
        op = self.peek()
        if op.kind == "op" and op.text == ">" and self.vector_depth:
            return left  # the '>' that closes <1, 2>, not a comparison
        if (op.kind == "op" and op.text in self._COMPARISONS) or self.is_word(op, "in"):
            self.next()
            self.skip_nl()
            right = self.expression_body()
            return S.Binary(op.text, left, right, self._join(left, right))
        return left

    def expression_body(self):
        if self.is_op("<") and self.vector_starts_here():
            left = self.vector_operand()  # the expression begins with a vector operand
        else:
            left = self.term()
        while self.is_op("+") or self.is_op("-"):
            op = self.next()
            self.skip_nl()
            right = self.vector_operand() if self.is_op("<") else self.term()
            left = S.Binary(op.text, left, right, self._join(left, right))
        return left

    def vector_operand(self):
        """A vector literal followed by its own factors and powers: `<1, 2>^2`, `<1, 2> * A`."""
        node = self.vector_literal("<", ">")
        if self.is_op("^") and self.peek().start == node.span.end:  # <1, 2>^2 raises each element
            self.next()
            self.skip_nl()
            exponent = self.unary()
            node = S.Binary("^", node, exponent, self._join(node, exponent))
        while self.is_op("*") or self.is_op("/") \
                or (self.is_op(".") and (self.is_op("*", 1) or self.is_op("/", 1))):
            op = self.next()
            text = op.text
            if text == ".":
                text += self.next().text  # `.*` and `./`
            self.skip_nl()
            right = self.vector_operand() if self.is_op("<") else self.unary()
            node = S.Binary(text, node, right, self._join(node, right))
        return node

    def vector_starts_here(self) -> bool:
        """Does the '<' at the cursor open a vector operand, as in `v + <1, 2>`?

        A comparison `a < b` follows a value; a vector begins where an operand may begin, so it
        is the first thing on its line or it follows an operator such as `+`, `-`, `(` or `,`.
        A `>` at its own level, or a comma, must appear later on the same statement.
        """
        if self.i > 0:
            before = self.toks[self.i - 1]
            if not (before.kind in ("nl", "op") and (before.kind == "nl" or before.text in ("=", "+", "-", "(", "[", ",", ";", "{", "}", "->"))):
                return False
        depth = 0
        k = 1
        while True:
            t = self.peek_raw(k)
            if t.kind == "eof":
                return False
            if t.kind == "op":
                if t.text in ("(", "["):
                    depth += 1
                elif t.text in (")", "]"):
                    depth -= 1
                elif t.text == ">" and depth == 0:
                    return True
                elif t.text == "," and depth == 0:
                    return True
                elif t.text in ("=", "==", "!=", "<=", ">=", ";", "{", "}", "->") and depth == 0:
                    return False
            k += 1

    def term(self):
        left = self.unary()
        while True:
            if self.is_op("*") or self.is_op("/"):
                op = self.next()
                text = op.text
            elif self.is_op(".") and (self.is_op("*", 1) or self.is_op("/", 1)):
                self.next()  # the '.' of `.*` or `./`: element by element (MATLAB style)
                text = "." + self.next().text
            else:
                return left
            self.skip_nl()
            right = self.vector_literal("<", ">") if self.is_op("<") else self.unary()
            left = S.Binary(text, left, right, self._join(left, right))

    def unary(self):
        if self.is_op("-") or self.is_op("+"):
            op = self.next()
            operand = self.unary()
            span = Span(self.source, op.start, operand.span.end if operand.span else op.end)
            if op.text == "+":
                return operand
            if isinstance(operand, S.QuantityLit):  # -40 degC is the temperature -40 degC, not -(40 degC)
                return S.QuantityLit(-operand.value, operand.unit, span)
            if isinstance(operand, S.Number):
                return S.Number(-operand.value, span)
            if isinstance(operand, S.Name) and operand.name in ("true", "false"):
                return S.Unary("not", operand, span)
            return S.Unary("-", operand, span)
        return self.power()

    def power(self):
        base = self.postfix()
        if self.is_op("^"):
            # `^` never opens a value (so `x = a ^2` after an assignment, or a new line after an
            # expression, is not mistaken for a power): it must touch what precedes it, as a
            # superscript would, or follow a value with whitespace on both sides.
            caret = self.peek()
            spaced = caret.start > self.last_end and self.peek(1).start > caret.end
            if caret.start != self.last_end and not spaced:
                return base
            self.next()
            self.skip_nl()
            exp = self.unary()  # right-associative; also allows 2^-3
            return S.Binary("^", base, exp, self._join(base, exp))
        return base

    def postfix(self):
        node = self.primary()
        while True:
            t = self.peek()
            if t.kind == "op" and t.text == "." and self.peek(1).kind == "ident" \
                    and self.peek(1).start == t.end:
                # `M.T` is a member; the `.` of `a .* b` is followed by a space and then `*`.
                self.next()
                attr = self.next()
                node = S.Member(node, attr.text, Span(self.source, node.span.start, attr.end))
                if self.is_op("(") and t.start == node.obj.span.end and self.peek().start == attr.end:
                    node = self.member_call(node)  # `rocket.burnTime(50 kN)`
            elif t.kind == "super":
                self.next()
                node = S.Binary("^", node, S.Number(float(t.value), Span(self.source, t.start, t.end)),
                                Span(self.source, node.span.start, t.end))
            elif t.kind == "op" and t.text == "[" and not is_literal(node):
                self.next()
                self.depth += 1
                try:
                    indices, count = self.index_items()
                    end = self.expect_op("]", "Expected ',' or ']' to close this index")
                finally:
                    self.depth -= 1
                node = S.Index(node, indices, Span(self.source, node.span.start, end.end), count)
            else:
                return node

    def member_call(self, member: S.Member):
        """The arguments of `rocket.burnTime(...)`: the member is the function being called."""
        self.next()  # '('
        self.depth += 1
        args: List[object] = []
        kwargs: List[Tuple[str, object, Optional[Span]]] = []
        try:
            while True:
                while self.peek().kind == "nl":
                    self.next()
                if self.is_op(")"):
                    break
                t = self.peek()
                follow = self.peek_raw(1)
                if t.kind == "ident" and follow.kind == "op" and follow.text == "=" and t.text not in KEYWORDS:
                    self.next()
                    self.next()
                    kwargs.append((t.text, self.expression(), Span(self.source, t.start, t.end)))
                else:
                    args.append(self.expression())
                if self.is_op(","):
                    self.next()
                    continue
                while self.peek().kind == "nl":
                    self.next()
                if not self.is_op(")"):
                    break
            end = self.expect_op(")", "Expected ',' or ')' in this call")
        finally:
            self.depth -= 1
        return S.MethodCall(member.obj, member.attr, tuple(args), tuple(kwargs),
                            Span(self.source, member.span.start, end.end))

    def index_items(self):
        """Index lists: `:` selects everything along that axis, `j:k` begins a counted selection."""
        indices = [self.index_item()]
        count = self._count  # read before the next index clears it
        while self.is_op(","):
            self.next()
            indices.append(self.index_item())
        return tuple(indices), count

    def index_item(self):
        self._count = None
        if self.is_op(":"):
            colon = self.next()
            return S.Name(":", Span(self.source, colon.start, colon.end))
        value = self.expression()
        if self.is_op(":"):
            self.next()
            self.skip_nl()
            self._count = self.expression()
            return S.Binary(":", value, self._count, self._join(value, self._count))
        return value

    def primary(self):
        t = self.peek()
        if t.kind == "nl" and self.i > 0:
            previous = self.toks[self.i - 1]
            if previous.kind == "op" and previous.text in ("=", "+", "-", "*", "/", "^", ",", "("):
                self.next()  # `A =` at the end of a line: the value starts on the next line
                t = self.peek()
        if t.kind == "num":
            return self.number_or_quantity()
        if t.kind == "ident" and t.text in ("true", "false", "i", "and", "or", "not"):
            self.next()
            return S.Name(t.text, Span(self.source, t.start, t.end))
        if t.kind == "ident":
            if t.text in KEYWORDS:
                self.fail(f"'{t.text}' is a keyword and cannot be used as a value", t)
            self.next()
            if self.is_op("("):
                return self.call(t)
            return S.Name(t.text, Span(self.source, t.start, t.end))
        if t.kind == "op" and t.text == "(":
            start = t.start
            self.next()
            self.depth += 1
            inner = self.expression()
            self.expect_op(")", "Expected ')' to close this bracket")
            self.depth -= 1
            # keep the inner node but widen nothing: errors point at the inner expression
            return inner
        if t.kind == "op" and t.text == "<":
            return self.vector_literal("<", ">")
        if t.kind == "op" and t.text == "[":
            return self.bracket_literal()
        if t.kind == "str":
            self.next()
            return S.StringLit(t.value, Span(self.source, t.start, t.end))
        self.fail(f"Expected a value but found {self.describe(t)}", t)

    def vector_literal(self, opening: str, closing: str, allow_trailing: bool = False):
        start = self.expect_op(opening).start  # read the '<' before raising the depth below
        self.depth += 1  # the first value may start on the next line
        if opening == "<":
            self.vector_depth += 1  # its own '>' closes the vector instead of comparing
        if opening == "<" and self.is_op(">"):  # <> is the empty vector
            empty = self.next()
            self.depth -= 1
            self.vector_depth -= 1
            return S.VectorLiteral((), Span(self.source, start, empty.end))
        items = []
        if self.is_op(closing):
            self.fail("A vector must contain at least one value", self.peek())
        while True:
            here = self.toks[self.i]  # a matrix row ends at the end of its line, so read it raw
            if here.kind == "op" and here.text == closing:
                break
            items.append(self.expression())
            if self.is_op(","):
                self.next()
                if allow_trailing and self.toks[self.i].kind == "nl":
                    continue  # the row ends its line: the matrix loop reads the next row
                continue
            break
        self.expect_op(closing, f"Expected ',' or '{closing}' in this vector")
        self.depth -= 1
        if opening == "<":
            self.vector_depth -= 1
        return S.VectorLiteral(tuple(items), Span(self.source, start, self.last_end))

    def bracket_literal(self):
        """[rows of values] is a matrix; [a, b, c] joins vectors into one."""
        start = self.expect_op("[").start  # read before raising depth: this '[' may sit alone
        self.depth += 1
        while self.toks[self.i].kind == "nl":
            self.i += 1  # the first row may start on the next line
        if self.is_op("]"):
            self.fail("A matrix or list must contain at least one value", self.peek())
        items: List[object] = []
        if self.is_op("["):
            rows = []
            while True:
                if self.is_op("]"):
                    break  # the matrix is complete after its last row
                if not self.is_op("["):
                    self.fail("Expected a row such as '[1, 2]' in this matrix", self.peek())
                row = self.vector_literal("[", "]", allow_trailing=True)
                rows.append(row.items)
                # A row ends at a comma, at the closing ']', or at the end of its line.  Inside a
                # bracket peek() steps over newlines, so read the neighbouring tokens directly.
                here = self.toks[self.i]
                if here.kind == "op" and here.text == ",":
                    self.next()  # a comma separates rows: [row], [row]
                    while self.toks[self.i].kind == "nl" or (
                            self.toks[self.i].kind == "op" and self.toks[self.i].text == ","):
                        self.i += 1  # a trailing comma, then the next row on the following line
                    continue
                while self.toks[self.i].kind == "nl":
                    self.i += 1  # the row's line ended; the next row starts on the following line
                nxt = self.toks[self.i]
                if nxt.kind == "op" and nxt.text in (",", "]", "["):
                    continue  # the next row, or the ']' that ends the matrix
                self.fail("Expected another matrix row or ']' to close the matrix", nxt)
            widths = {len(row) for row in rows if row}
            if len(widths) != 1:
                self.fail("All matrix rows must have the same number of values",
                          Span(self.source, start, self.last_end))
            items.append(S.MatrixLiteral(tuple(rows), Span(self.source, start, self.last_end)))
            keywords = any(self.is_op(w) for w in ("try", "catch"))  # MATLAB-style start/end
            if keywords:
                self.fail("Use [rows of values] for a matrix, or separate rows with commas", self.peek(),
                          "A list written with [ ] holds one row of values; write rows as [1, 2; 3, 4] "
                          "or [[1, 2], [3, 4]] for a matrix.")
        else:
            while True:
                items.append(self.expression())
                if self.is_op(","):
                    self.next()
                    if self.is_op("]"):
                        break
                    continue
                if self.is_op(";"):  # [1, 2; 3, 4] is a matrix in MATLAB; here ';' ends a statement
                    self.fail("Use commas between rows: [[1, 2], [3, 4]]", self.peek())
                break
        self.expect_op("]", "Expected ',' or ']' in this matrix or list")
        self.depth -= 1
        span = Span(self.source, start, self.last_end)
        if len(items) > 1:
            return S.ListLiteral(tuple(items), span)
        only = items[0]
        if isinstance(only, S.MatrixLiteral):  # [[1, 2]] is the 1x2 matrix [<1, 2>]
            return only
        return S.VectorLiteral(tuple(only.items), span)  # [1, 2] is the vector <1, 2>

    def number_or_quantity(self):
        start = self.i  # the index of the number itself, before `next()` moves past it
        tok = self.next()
        nxt = self.peek()
        # `0.5 1/s`: the token after the number is a `1` that begins an inverse unit.
        raw = self.toks[start + 1] if start + 1 < len(self.toks) else None
        slash = self.toks[start + 2] if start + 2 < len(self.toks) else None
        if raw is not None and raw.kind == "num" and raw.text == "1" and slash is not None \
                and slash.kind == "op" and slash.text == "/" and slash.start == raw.end:
            # `0.5 1/s`: an inverse unit, such as a frequency or a rate constant, belongs to the
            # number just as `0.5 m/s` does; the leading `1` is part of the unit.
            self.next()  # the 1; the '/' then opens a denominator, as in 1/s
            self.expect_op("/")
            atoms = [(n, -e, sp) for n, e, sp in self.parse_unit_atoms(tight=True)]
            return S.QuantityLit(tok.value, self.make_unit(atoms), self.span_from(tok.start))
        if nxt.kind == "ident" and nxt.text == "i":
            self.next()  # 3i, 2.5i: the imaginary part of a complex number
            after = self.peek()
            if after.kind == "ident" and after.text not in KEYWORDS and lookup_unit(after.text) is not None:
                # 4i ohm: an imaginary quantity, which keeps the unit it was written in.
                atoms = self.parse_unit_atoms(tight=True)
                return S.QuantityLit(complex(0, tok.value), self.make_unit(atoms),
                                     self.span_from(tok.start))
            return S.Number(complex(0, tok.value), Span(self.source, tok.start, nxt.end))
        if nxt.kind == "ident" and nxt.text not in KEYWORDS and nxt.text != "and":
            if nxt.text in ("in", "or", "not", "true", "false"):
                self.fail(f"'{nxt.text}' is a keyword and cannot be used as a unit", nxt,
                          f"If you meant multiplication, write {tok.text} * {nxt.text}.")
            self.check_unit(nxt.text, Span(self.source, nxt.start, nxt.end),
                            f"If you meant multiplication, write {tok.text} * {nxt.text}.")
            atoms = self.parse_unit_atoms(tight=True)
            return S.QuantityLit(tok.value, self.make_unit(atoms), self.span_from(tok.start))
        return S.Number(tok.value, Span(self.source, tok.start, tok.end))

    def call(self, name_tok: Token):
        self.next()  # '('
        self.depth += 1  # its arguments may wrap onto the following lines
        while self.toks[self.i].kind == "nl" and self.depth > 0:
            self.i += 1
        args: List[object] = []
        kwargs: List[Tuple[str, object, Optional[Span]]] = []
        try:
            while True:
                while self.peek().kind == "nl":
                    self.next()  # each argument may sit on its own line
                if self.is_op(")"):
                    break
                t = self.peek()
                follow = self.peek_raw(1)  # the next token on this line, not one across a newline
                if t.kind == "ident" and follow.kind == "op" and follow.text == "=" and t.text not in KEYWORDS:
                    self.next()
                    self.next()
                    kwargs.append((t.text, self.expression(), Span(self.source, t.start, t.end)))
                else:
                    if kwargs:
                        self.fail("Positional values must come before named ones", t)
                    args.append(self.expression())
                if self.is_op(","):
                    self.next()
                    continue
                while self.peek().kind == "nl":
                    self.next()  # the ')' may follow on the next line
                if not self.is_op(")"):
                    break
            self.expect_op(")", "Expected ',' or ')' in this call")
        finally:
            self.depth -= 1
        return S.Call(name_tok.text, tuple(args), tuple(kwargs), self.span_from(name_tok.start),
                      Span(self.source, name_tok.start, name_tok.end))


def parse(source: Source) -> List[object]:
    return Parser(source).parse_program()


def parse_text(text: str, name: str = "<input>") -> List[object]:
    return parse(Source(name, text))
