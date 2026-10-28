"""Recursive-descent parser.

Expression precedence, lowest to highest:   + -   <   * /   <   unary -   <   ^ (right-assoc)
A number immediately followed by a unit name is a quantity literal:  9.81 m/s^2.  Inside such
a unit the operators must touch their operands (m/s^2, not m / s^2) so that
`10 m / 2 s` still means (10 m) / (2 s).  Declarations and `convert` targets run to the end of
the line, so they may be written with spaces.
"""
from __future__ import annotations

from fractions import Fraction
from typing import List, Optional, Tuple

from . import syntax as S
from .errors import ForgeNameError, ForgeSyntaxError, Source, Span
from .lexer import KEYWORDS, Token, tokenize
from .units import Unit, UnknownUnit, lookup_unit, suggest_units

Atom = Tuple[str, Fraction, Span]


class Parser:
    def __init__(self, source: Source):
        self.source = source
        self.toks = tokenize(source)
        self.i = 0
        self.depth = 0  # >0 inside ( ): newlines are then ignored
        self.last_end = 0

    # ---- token access ----------------------------------------------------------------------
    def _index(self, k: int = 0) -> int:
        i, count, last = self.i, 0, len(self.toks) - 1
        while True:
            if i >= last:
                return last
            if self.depth > 0 and self.toks[i].kind == "nl":
                i += 1
                continue
            if count == k:
                return i
            count += 1
            i += 1

    def peek(self, k: int = 0) -> Token:
        return self.toks[self._index(k)]

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
        span = where if isinstance(where, Span) else Span(self.source, where.start, max(where.end, where.start + 1))
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
            if kw == "for":
                self.fail("'for' can only be used inside a solve statement", t,
                          "Write: solve Equation for variable { ... }")
            if self.is_op("=", 1):
                return self.assign()
        expr = self.expression()
        return S.ExprStmt(expr, expr.span)

    def assign(self):
        name = self.next()
        self.next()  # '='
        self.skip_nl()
        expr = self.expression()
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

    def convert_stmt(self):
        kw = self.next()
        expr = self.expression()
        self.expect_op("->", "Expected '->' and a target unit", "For example: convert 10 ft -> m")
        atoms = self.parse_unit_atoms(tight=False)
        return S.Convert(expr, self.make_unit(atoms), self.span_from(kw.start))

    def solve_stmt(self):
        kw = self.next()
        eq = self.expect_ident("the name of the equation to solve")
        t = self.peek()
        if not (t.kind == "ident" and t.text == "for"):
            self.fail("Expected 'for' and the variable to solve for", t,
                      f"Write: solve {eq.text} for x {{ ... }}")
        self.next()
        target = self.expect_ident("the variable to solve for")
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
        return S.Solve(eq.text, target.text, tuple(givens), self.span_from(kw.start),
                       Span(self.source, eq.start, eq.end), Span(self.source, target.start, target.end))

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

    def expression(self):
        left = self.term()
        while self.is_op("+") or self.is_op("-"):
            op = self.next()
            self.skip_nl()
            right = self.term()
            left = S.Binary(op.text, left, right, self._join(left, right))
        return left

    def term(self):
        left = self.unary()
        while self.is_op("*") or self.is_op("/"):
            op = self.next()
            self.skip_nl()
            right = self.unary()
            left = S.Binary(op.text, left, right, self._join(left, right))
        return left

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
            return S.Unary("-", operand, span)
        return self.power()

    def power(self):
        base = self.postfix()
        if self.is_op("^"):
            self.next()
            self.skip_nl()
            exp = self.unary()  # right-associative; also allows 2^-3
            return S.Binary("^", base, exp, self._join(base, exp))
        return base

    def postfix(self):
        node = self.primary()
        while True:
            t = self.peek()
            if t.kind == "op" and t.text == "." and self.peek(1).kind == "ident":
                self.next()
                attr = self.next()
                node = S.Member(node, attr.text, Span(self.source, node.span.start, attr.end))
            elif t.kind == "super":
                self.next()
                node = S.Binary("^", node, S.Number(float(t.value), Span(self.source, t.start, t.end)),
                                Span(self.source, node.span.start, t.end))
            else:
                return node

    def primary(self):
        t = self.peek()
        if t.kind == "num":
            return self.number_or_quantity()
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
        if t.kind == "str":
            self.fail("Text can only be used with print and in equation metadata", t)
        self.fail(f"Expected a value but found {self.describe(t)}", t)

    def number_or_quantity(self):
        tok = self.next()
        nxt = self.peek()
        if nxt.kind == "ident" and nxt.text not in KEYWORDS:
            self.check_unit(nxt.text, Span(self.source, nxt.start, nxt.end),
                            f"If you meant multiplication, write {tok.text} * {nxt.text}.")
            atoms = self.parse_unit_atoms(tight=True)
            return S.QuantityLit(tok.value, self.make_unit(atoms), self.span_from(tok.start))
        return S.Number(tok.value, Span(self.source, tok.start, tok.end))

    def call(self, name_tok: Token):
        self.next()  # '('
        self.depth += 1
        args: List[object] = []
        kwargs: List[Tuple[str, object, Optional[Span]]] = []
        if not self.is_op(")"):
            while True:
                t = self.peek()
                if t.kind == "ident" and self.is_op("=", 1) and t.text not in KEYWORDS:
                    self.next()
                    self.next()
                    kwargs.append((t.text, self.expression(), Span(self.source, t.start, t.end)))
                else:
                    if kwargs:
                        self.fail("Positional values must come before named ones", t)
                    args.append(self.expression())
                if self.is_op(","):
                    self.next()
                    if self.is_op(")"):  # trailing comma
                        break
                    continue
                break
        self.expect_op(")", "Expected ',' or ')' in this call")
        self.depth -= 1
        return S.Call(name_tok.text, tuple(args), tuple(kwargs), self.span_from(name_tok.start),
                      Span(self.source, name_tok.start, name_tok.end))


def parse(source: Source) -> List[object]:
    return Parser(source).parse_program()


def parse_text(text: str, name: str = "<input>") -> List[object]:
    return parse(Source(name, text))
