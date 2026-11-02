"""Translate the scalar F²ORGE language subset to Python, C++, MicroPython, or TI-84 BASIC.

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
_TI_VARIABLES = "ABCDEFGHIJKLMNOPQRSTUVWXYZθ"


class TranspileError(ForgeError):
    """A source construct cannot be translated without changing its meaning."""

    title = "Cannot transpile"


@dataclass
class _Generator:
    target: str

    def __post_init__(self) -> None:
        self.assigned: Set[str] = set()
        self.used_constants: Set[str] = set()
        self.variable_names: List[str] = []
        self.variable_map: Dict[str, str] = {}

    @property
    def is_python(self) -> bool:
        return self.target in ("python", "micropython")

    @property
    def is_cpp(self) -> bool:
        return self.target == "cpp"

    @property
    def is_ti_basic(self) -> bool:
        return self.target == "ti-basic"

    def identifier(self, name: str) -> str:
        if self.is_ti_basic:
            return self.variable_map[name]
        if self.is_python:
            return f"f2orge_{name}" if keyword.iskeyword(name) or name == "math" or name.startswith("f2orge_") else name
        return f"f2orge_{name}" if name in _CPP_KEYWORDS or name in {"std", "main", "cout"} else name

    def prepare_ti_variables(self, statements: List[object]) -> None:
        assigned_names = {
            statement.name for statement in statements if isinstance(statement, S.Assign)
        }
        if any(isinstance(statement, (S.ExprStmt, S.Convert)) for statement in statements):
            assigned_names.add("ans")

        def remember(name: str) -> None:
            if name in assigned_names or name not in CONSTANTS:
                if name not in self.variable_names:
                    self.variable_names.append(name)

        for statement in statements:
            if isinstance(statement, S.Assign):
                remember(statement.name)
                for node in S.walk(statement.expr):
                    if isinstance(node, S.Name):
                        remember(node.name)
            elif isinstance(statement, (S.ExprStmt, S.Convert)):
                remember("ans")
                expression = statement.expr
                for node in S.walk(expression):
                    if isinstance(node, S.Name):
                        remember(node.name)
            elif isinstance(statement, S.Print):
                for expression in statement.items:
                    for node in S.walk(expression):
                        if isinstance(node, S.Name):
                            remember(node.name)
        if len(self.variable_names) > len(_TI_VARIABLES):
            raise TranspileError(
                f"TI-84 BASIC supports at most {len(_TI_VARIABLES)} scalar variables in this converter",
                hint="Reduce the number of distinct variables or use MicroPython instead.",
            )
        self.variable_map = {
            name: _TI_VARIABLES[index] for index, name in enumerate(self.variable_names)
        }

    def ti_name(self, name: str) -> str:
        if name == "theta":
            return "θ"
        return self.identifier(name)

    def expression(self, node: object) -> str:
        if isinstance(node, S.Number):
            return _number(node.value)
        if isinstance(node, S.QuantityLit):
            if self.is_ti_basic and node.unit.scale == 1 and node.unit.offset == 0:
                return _number(node.value)
            magnitude = _number(node.value)
            scaled = f"({magnitude} * {_number(node.unit.scale)})"
            if node.unit.offset:
                return f"({scaled} + {_number(node.unit.offset)})"
            return scaled
        if isinstance(node, S.StringLit):
            if self.is_ti_basic:
                if '"' in node.value or any(ord(char) < 32 for char in node.value):
                    raise TranspileError(
                        "TI-84 BASIC strings cannot contain quotes or control characters",
                        node.span,
                    )
                return f'"{node.value}"'
            return repr(node.value) if self.is_python else json.dumps(node.value, ensure_ascii=False)
        if isinstance(node, S.Name):
            if node.name in self.assigned:
                return self.identifier(node.name)
            if node.name in CONSTANTS:
                if self.is_ti_basic:
                    if node.name == "pi":
                        return "π"
                    return _number(CONSTANTS[node.name].value)
                self.used_constants.add(node.name)
                return _constant_identifier(node.name)
            return self.identifier(node.name)
        if isinstance(node, S.Unary):
            return f"({node.op}{self.expression(node.operand)})"
        if isinstance(node, S.Binary):
            left, right = self.expression(node.left), self.expression(node.right)
            if node.op == "^":
                if self.is_python:
                    return f"({left} ** {right})"
                if self.is_cpp:
                    return f"std::pow({left}, {right})"
                return f"({left}^{right})"
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
            if self.is_ti_basic:
                if node.func == "atan2":
                    raise TranspileError(
                        "atan2() is not supported by TI-84 BASIC code generation",
                        node.span,
                        hint="Use MicroPython or rewrite this expression for the calculator.",
                    )
                if node.func in ("min", "max"):
                    result = args[0]
                    for arg in args[1:]:
                        result = f"{node.func}({result},{arg})"
                    return result
                function = {
                    "asin": "sin⁻¹", "acos": "cos⁻¹", "atan": "tan⁻¹",
                    "exp": "e^", "sqrt": "√", "abs": "abs", "ln": "ln", "log": "log",
                }.get(node.func, node.func)
                return f"{function}({args[0]})"
            if self.is_python:
                if self.target == "micropython" and node.func == "log":
                    return f"(math.log({args[0]}) / math.log(10))"
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
            if self.is_ti_basic:
                return [f"{value}→{self.identifier(node.name)}"]
            terminator = ";" if self.target == "cpp" else ""
            return [f"{self.identifier(node.name)} = {value}{terminator}"]
        if isinstance(node, S.ExprStmt):
            value = self.expression(node.expr)
            self.assigned.add("ans")
            if self.is_ti_basic:
                return [f"{value}→{self.identifier('ans')}", f"Disp {self.identifier('ans')}"]
            terminator = ";" if self.target == "cpp" else ""
            return [f"ans = {value}{terminator}", self.print_value("ans")]
        if isinstance(node, S.Print):
            values = [self.expression(item) for item in node.items]
            if self.is_ti_basic:
                return [f"Disp {', '.join(values)}"]
            if self.is_python:
                return [f"print({', '.join(values)})"]
            return [("std::cout << " + ' << " " << '.join(values) + " << '\\n';")
                    if values else 'std::cout << "\\n";']
        if isinstance(node, S.Convert):
            value = self.expression(node.expr)
            scale = _number(node.unit.scale)
            converted = f"(({value} - {_number(node.unit.offset)}) / {scale})"
            self.assigned.add("ans")
            if self.is_ti_basic:
                converted = f"({value}/{scale})" if node.unit.offset == 0 else converted
                statements = [f"{converted}→{self.identifier('ans')}", f"Disp {self.identifier('ans')}"]
                symbol = node.unit.symbol(True)
                if symbol:
                    statements.append(f'Disp "{symbol}"')
                return statements
            terminator = ";" if self.target == "cpp" else ""
            if self.is_python:
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
        if self.is_python:
            return f"print({value})"
        return f"std::cout << {value} << '\\n';"


def _number(value: float) -> str:
    return repr(float(value))


def _constant_identifier(name: str) -> str:
    return f"_f2orge_constant_{name}"


def _constants(generator: _Generator, names: Iterable[str]) -> List[str]:
    lines = []
    for name in sorted(names):
        value = CONSTANTS[name].value
        identifier = _constant_identifier(name)
        if generator.is_python:
            lines.append(f"{identifier} = {_number(value)}")
        else:
            lines.append(f"constexpr double {identifier} = {_number(value)};")
    return lines


def transpile(source: str, target: str, filename: str = "<string>") -> str:
    """Translate a supported scalar F²ORGE program to a target-language source file."""
    aliases = {
        "c++": "cpp", "micro-py": "micropython", "micro_py": "micropython",
        "ti84": "ti-basic", "ti-84": "ti-basic", "ti84-basic": "ti-basic",
        "ti-84-basic": "ti-basic",
    }
    target = aliases.get(target.lower(), target.lower())
    if target not in ("python", "micropython", "cpp", "ti-basic"):
        raise ValueError("target must be 'python', 'micropython', 'cpp', or 'ti-basic'")

    statements = parse(Source(filename, source))
    generator = _Generator(target)
    if generator.is_ti_basic:
        generator.prepare_ti_variables(statements)
    body: List[str] = []
    for statement in statements:
        body.extend(generator.statement(statement))

    if generator.is_ti_basic:
        code = [
            ":ClrHome",
            ":If 0:Then",
            ':Disp "TI-BASIC variable map"',
        ]
        code.extend(
            f':Disp "{identifier}={name}"'
            for name, identifier in generator.variable_map.items()
            if len(name) != 1
        )
        code.extend([":End", *[f":{line}" for line in body]])
        return "\n".join(code) + "\n"

    header = [
        "# Generated by F²ORGE. Quantities are numeric SI magnitudes; unit-safety checks are not retained."
    ]
    if generator.is_python:
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
