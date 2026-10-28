"""AST -> source text.  Used by `export` (writing .eq files), the generated docs and `solve --explain`."""
from __future__ import annotations

from typing import List

from . import syntax as S

# binding strength: higher binds tighter
_PREC = {"+": 1, "-": 1, "*": 2, "/": 2}
_UNARY, _POW, _QUANTITY, _ATOM = 3, 4, 5, 6


def format_number(x: float) -> str:
    if float(x).is_integer() and abs(x) < 1e15:
        return str(int(x))
    return f"{x:.12g}"


def quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _prec(node) -> int:
    if isinstance(node, S.Binary):
        return _POW if node.op == "^" else _PREC[node.op]
    if isinstance(node, S.Unary):
        return _UNARY
    if isinstance(node, (S.Number, S.QuantityLit)) and node.value < 0:
        return _UNARY
    if isinstance(node, S.QuantityLit):
        return _QUANTITY
    return _ATOM


def format_expr(node, parent: int = 0) -> str:
    """Render an expression with the fewest parentheses that keep its meaning."""
    if isinstance(node, S.Number):
        text = format_number(node.value)
    elif isinstance(node, S.QuantityLit):
        symbol = node.unit.symbol(ascii_only=True)
        text = f"{format_number(node.value)} {symbol}" if symbol else format_number(node.value)
    elif isinstance(node, S.StringLit):
        text = quote(node.value)
    elif isinstance(node, S.Name):
        text = node.name
    elif isinstance(node, S.Member):
        text = f"{format_expr(node.obj, _ATOM)}.{node.attr}"
    elif isinstance(node, S.Call):
        parts: List[str] = [format_expr(a) for a in node.args]
        parts += [f"{k} = {format_expr(v)}" for k, v, _ in node.kwargs]
        text = f"{node.func}({', '.join(parts)})"
    elif isinstance(node, S.Unary):
        text = "-" + format_expr(node.operand, _UNARY)
    elif isinstance(node, S.Binary):
        if node.op == "^":
            text = f"{format_expr(node.left, _ATOM)}^{format_expr(node.right, _POW)}"
        else:
            p = _PREC[node.op]
            right_parent = p + 1 if node.op in "-/" or node.op in "+*" else p
            text = f"{format_expr(node.left, p)} {node.op} {format_expr(node.right, right_parent)}"
    else:  # pragma: no cover
        text = repr(node)
    return f"({text})" if _prec(node) < parent else text


def format_relation(rel: S.Relation) -> str:
    return f"{format_expr(rel.lhs)} = {format_expr(rel.rhs)}"


def format_equation(eq) -> str:
    """Canonical .eq text for an Equation (metadata, declarations, then relations)."""
    lines = [f"eq {eq.name} {{"]
    for key, value in eq.metadata.items():
        lines.append(f"    {key} = {quote(value)}")
    if eq.metadata:
        lines.append("")
    for decl in eq.decls.values():
        symbol = decl.unit.symbol(ascii_only=True) or "dimensionless"
        doc = f" {quote(decl.doc)}" if decl.doc else ""
        lines.append(f"    {decl.name} : {symbol}{doc}")
    if eq.decls:
        lines.append("")
    for rel in eq.relations:
        lines.append(f"    {format_relation(rel)}")
    lines.append("}")
    return "\n".join(lines) + "\n"
