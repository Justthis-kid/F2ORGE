"""Translate the scalar F²ORGE language subset to standalone Python or C++.

Unit literals and built-in physical constants are lowered to coherent SI magnitudes. Generated
programs are numerical code; they do not retain F²ORGE's runtime dimensional-safety checks.
"""
from __future__ import annotations

import json
import keyword
from dataclasses import dataclass
from typing import Dict, Iterable, List, Set

from . import syntax as S
from .constants import CONSTANTS
from .errors import ForgeError, Source, Span
from .parser import parse


_CPP_KEYWORDS = frozenset(
    "alignas alignof and and_eq asm atomic_cancel atomic_commit atomic_noexcept auto bitand "
    "bitor bool break case catch char char8_t char16_t char32_t class compl concept const "
    "consteval constexpr constinit const_cast continue co_await co_return co_yield decltype "
    "default delete do double dynamic_cast else enum explicit export extern false float for "
    "friend goto if inline int long mutable namespace new noexcept not not_eq nullptr operator "
    "or or_eq private protected public register reinterpret_cast requires return short signed "
    "sizeof static static_assert static_cast struct switch synchronized template this thread_local "
    "throw true try typedef typeid typename union unsigned using virtual void volatile wchar_t "
    "while xor xor_eq".split()
)

_FUNCTIONS = {
    "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "exp", "ln", "log",
    "sqrt", "abs", "min", "max",
}


class TranspileError(ForgeError):
    """A source construct cannot be translated without changing its meaning."""

    title = "Cannot transpile"


@dataclass
class _Generator:
    target: str

    def __post_init__(self) -> None:
        self.assigned: Set[str] = set()
        self.used_constants: Set[str] = set()

    def identifier(self, name: str) -> str:
        if self.target == "python":
            return f"f2orge_{name}" if keyword.iskeyword(name) or name == "math" or name.startswith("f2orge_") else name
        return f"f2orge_{name}" if name in _CPP_KEYWORDS or name in {"std", "main", "cout"} else name

    def expression(self, node: object) -> str:
        if isinstance(node, S.Number):
            return _number(node.value)
        if isinstance(node, S.QuantityLit):
            magnitude = _number(node.value)
            scaled = f"({magnitude} * {_number(node.unit.scale)})"
            if node.unit.offset:
                return f"({scaled} + {_number(node.unit.offset)})"
            return scaled
        if isinstance(node, S.StringLit):
            return repr(node.value) if self.target == "python" else json.dumps(node.value, ensure_ascii=False)
        if isinstance(node, S.Name):
            if node.name in self.assigned:
                return self.identifier(node.name)
            if node.name in CONSTANTS:
                self.used_constants.add(node.name)
                return _constant_identifier(node.name)
            return self.identifier(node.name)
        if isinstance(node, S.Unary):
            return f"({node.op}{self.expression(node.operand)})"
        if isinstance(node, S.Binary):
            left, right = self.expression(node.left), self.expression(node.right)
            if node.op == "^":
                return f"({left} ** {right})" if self.target == "python" else f"std::pow({left}, {right})"
            return f"({left} {node.op} {right})"
        if isinstance(node, S.Call):
            if node.func not in _FUNCTIONS:
                raise TranspileError(
                    f"equation call '{node.func}(...)' is not supported",
                    node.span,
                    hint="Inline the equation or use its scalar formula directly.",
                )
            if node.kwargs:
                raise TranspileError("named arguments are not supported in generated code", node.span)
            args = [self.expression(arg) for arg in node.args]
            if node.func in ("min", "max") and len(args) < 2:
                raise TranspileError(f"{node.func}() needs at least two arguments", node.span)
            if self.target == "python":
                function = {"ln": "log", "log": "log10"}.get(node.func, node.func)
                if function not in ("min", "max", "abs"):
                    function = f"math.{function}"
                return f"{function}({', '.join(args)})"
            function = {"ln": "log", "log": "log10"}.get(node.func, node.func)
            if function in ("min", "max"):
                return f"std::{function}({{{', '.join(args)}}})"
            return f"std::{function}({', '.join(args)})"
        if isinstance(node, (S.VectorLiteral, S.MatrixLiteral)):
            raise TranspileError(
                "vector and matrix literals are not supported by scalar code generation",
                node.span,
                hint="Use scalar expressions, or keep this program in F²ORGE.",
            )
        if isinstance(node, S.Member):
            raise TranspileError("equation member access is not supported in generated code", node.span)
        raise TranspileError(f"unsupported expression: {type(node).__name__}", getattr(node, "span", None))

    def statement(self, node: object) -> List[str]:
        if isinstance(node, S.Assign):
            value = self.expression(node.expr)
            self.assigned.add(node.name)
            terminator = ";" if self.target == "cpp" else ""
            return [f"{self.identifier(node.name)} = {value}{terminator}"]
        if isinstance(node, S.ExprStmt):
            value = self.expression(node.expr)
            self.assigned.add("ans")
            terminator = ";" if self.target == "cpp" else ""
            return [f"ans = {value}{terminator}", self.print_value("ans")]
        if isinstance(node, S.Print):
            values = [self.expression(item) for item in node.items]
            if self.target == "python":
                return [f"print({', '.join(values)})"]
            return [("std::cout << " + ' << " " << '.join(values) + " << '\\n';")
                    if values else 'std::cout << "\\n";']
        if isinstance(node, S.Convert):
            value = self.expression(node.expr)
            scale = _number(node.unit.scale)
            converted = f"(({value} - {_number(node.unit.offset)}) / {scale})"
            self.assigned.add("ans")
            terminator = ";" if self.target == "cpp" else ""
            if self.target == "python":
                suffix = f" {node.unit.symbol(True)}" if node.unit.symbol(True) else ""
                return [f"ans = {converted}", f'print(f"{{ans:g}}{suffix}")']
            suffix = f" {node.unit.symbol(True)}" if node.unit.symbol(True) else ""
            return [
                f"ans = {converted}{terminator}",
                f'std::cout << ans << "{suffix}" << \'\\n\';',
            ]
        raise TranspileError(
            f"'{type(node).__name__}' statements are not supported in generated code",
            getattr(node, "span", None),
            hint="Only scalar assignments, expressions, print, and convert statements are supported.",
        )

    def print_value(self, value: str) -> str:
        return f"print({value})" if self.target == "python" else f"std::cout << {value} << '\\n';"


def _number(value: float) -> str:
    return repr(float(value))


def _constant_identifier(name: str) -> str:
    return f"_f2orge_constant_{name}"


def _constants(generator: _Generator, names: Iterable[str]) -> List[str]:
    lines = []
    for name in sorted(names):
        value = CONSTANTS[name].value
        identifier = _constant_identifier(name)
        if generator.target == "python":
            lines.append(f"{identifier} = {_number(value)}")
        else:
            lines.append(f"constexpr double {identifier} = {_number(value)};")
    return lines


def transpile(source: str, target: str, filename: str = "<string>") -> str:
    """Translate a supported F²ORGE program to Python or C++ source."""
    if target not in ("python", "cpp"):
        raise ValueError("target must be 'python' or 'cpp'")

    statements = parse(Source(filename, source))
    generator = _Generator(target)
    body: List[str] = []
    for statement in statements:
        body.extend(generator.statement(statement))

    header = [
        "# Generated by F²ORGE. Quantities are numeric SI magnitudes; unit-safety checks are not retained."
    ]
    if target == "python":
        code = header + ["import math"] + _constants(generator, generator.used_constants)
        if body:
            code.extend(["", *body])
        return "\n".join(code) + "\n"

    header = [
        "// Generated by F²ORGE. Quantities are numeric SI magnitudes; unit-safety checks are not retained.",
        "#include <algorithm>",
        "#include <cmath>",
        "#include <initializer_list>",
        "#include <iostream>",
    ]
    code = header + _constants(generator, generator.used_constants)
    if body:
        code.extend(["", "int main() {", *[f"    {line}" for line in body], "    return 0;", "}"])
    return "\n".join(code) + "\n"


def transpile_source(source: str, target: str, filename: str = "<string>") -> str:
    """Alias for callers that prefer an explicit function name."""
    return transpile(source, target, filename)
