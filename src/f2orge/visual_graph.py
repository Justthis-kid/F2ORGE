"""Blueprint-style visual expression graph model and F²ORGE code generation."""
from __future__ import annotations

import re
from dataclasses import dataclass
from math import isfinite
from typing import Dict, List, Tuple

from . import syntax as S
from .errors import ForgeError, Source
from .parser import parse

NODE_INPUTS = {
    "Input": 0,
    "Constant": 0,
    "Script": 0,
    "Function": 1,
    "Add": 2,
    "Subtract": 2,
    "Multiply": 2,
    "Divide": 2,
    "Power": 2,
    "Compare": 2,
    "Call": 2,  # a minimum; `connect()` allows more argument pins on a Call node
    "Output": 1,
    "Output2": 1,
}
NODE_SYMBOLS = {
    "Add": "+",
    "Subtract": "-",
    "Multiply": "*",
    "Divide": "/",
    "Power": "^",
    "Compare": "<=",
    "Call": "f(x)",
}
# A Compare node's value is a comparison operator, or a magnitude comparison's function name.
# `mag<` and `mag<=` compare sizes and ignore the kind of quantity, which is what a threshold
# on a mixed graph needs; plain `<` stays unit-safe and refuses mismatched units.
_COMPARISONS = {
    "<": ("<", None), "<=": ("<=", None), ">": (">", None), ">=": (">=", None),
    "==": ("==", None), "!=": ("!=", None),
    "lt": ("<", None), "le": ("<=", None), "gt": (">", None), "ge": (">=", None),
    "eq": ("==", None), "ne": ("!=", None),
    "mag<": (None, "less_mag"), "mag<=": (None, "less_equal_mag"),
    "mag>": (None, "greater_mag"), "mag>=": (None, "greater_equal_mag"),
}
_SHORT_NAMES = {"lt": "<", "le": "<=", "gt": ">", "ge": ">=", "eq": "==", "ne": "!="}


def _comparison_value(text: str) -> str:
    """The canonical spelling of a Compare node's value, or '' when it is not a comparison.

    `le` becomes `<=` and `mag<=` stays as it is; either spelling means the same thing.
    """
    key = text.lower().replace(" ", "")
    key = _SHORT_NAMES.get(key, key)
    return key if key in _COMPARISONS else ""
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_KEYWORDS = {"eq", "import", "export", "solve", "convert", "print", "for"}
_FUNCTIONS = {
    "sin", "cos", "tan", "asin", "acos", "atan", "exp", "ln", "log", "sqrt", "abs",
    # The newer expressions a student reaches for, all of one argument.
    "cross", "sum", "mean", "median", "std", "var", "percentile", "linreg", "det",
    "transpose", "inverse", "real", "imag", "conj", "arg", "mag", "cbrt", "sign",
    "fft", "ifft", "lowpass", "highpass", "db", "undb", "pH", "fromPH", "normalize",
    "cumsum", "diff", "trapz", "ceil", "floor",
}
# Nodes whose value is text that must be a valid name, or a choice from a fixed set.
_CALL_TARGETS = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class GraphNode:
    id: int
    kind: str
    value: str = ""
    x: float = 80
    y: float = 80
    width: float = 190
    height: float = 88


class VisualGraph:
    """Directed acyclic graph with one output per expression node."""

    def __init__(self) -> None:
        self.nodes: Dict[int, GraphNode] = {}
        self.connections: Dict[Tuple[int, int], int] = {}
        self._next_id = 1

    def add_node(self, kind: str, value: str = "", x: float = 80, y: float = 80) -> GraphNode:
        if not isinstance(kind, str) or kind not in NODE_INPUTS:
            raise ForgeError(f"unknown visual node type '{kind}'", title="Invalid visual node")
        if not isinstance(value, str):
            raise ForgeError("node values must be text", title="Invalid visual node")
        try:
            x_position, y_position = float(x), float(y)
        except (TypeError, ValueError) as err:
            raise ForgeError("node positions must be finite numbers", title="Invalid visual node") from err
        if not isfinite(x_position) or not isfinite(y_position):
            raise ForgeError("node positions must be finite", title="Invalid visual node")
        if kind == "Output2":
            names = [part.strip() for part in value.split(",")]
            if len(names) < 2:
                raise ForgeError("a two-output node needs at least two names, separated by commas",
                                 title="Invalid visual node", hint="For example: time, velocity")
            for name in names:
                self._check_name(name, "output")
            value = ", ".join(names)
        elif kind in ("Input", "Output"):
            self._check_name(value, kind.lower())
        if kind == "Constant":
            if not isinstance(value, str) or not value.strip():
                raise ForgeError("a constant node needs a F²ORGE value", title="Invalid visual node")
            statements = parse(Source("<visual constant>", value.strip()))
            if len(statements) != 1 or not isinstance(statements[0], S.ExprStmt):
                raise ForgeError("a constant node must contain one F²ORGE expression",
                                 title="Invalid visual node")
        if kind == "Script":
            if not value.strip():
                raise ForgeError("a script node needs F²ORGE statements", title="Invalid visual node")
            parse(Source("<visual script>", value.strip()))
        if kind == "Function" and value not in _FUNCTIONS:
            raise ForgeError(
                f"'{value}' is not a supported single-input function node",
                title="Invalid visual node",
                hint=f"Choose one of: {', '.join(sorted(_FUNCTIONS))}.",
            )
        if kind == "Compare":
            spelled = value.strip()
            value = _comparison_value(spelled)
            if not value:
                raise ForgeError(
                    f"'{spelled}' is not a comparison",
                    title="Invalid visual node",
                    hint="Use <, <=, >, >=, ==, != (or lt, le, gt, ge, eq, ne) to compare like kinds; "
                         "mag<, mag<=, mag>, mag>= compare sizes and ignore units.",
                )
        if kind == "Call":
            # A call node names a definition, which the script or equation must provide.
            if not _CALL_TARGETS.fullmatch(value.strip()):
                raise ForgeError(f"'{value}' is not a function or equation name",
                                 title="Invalid visual node",
                                 hint="Use a name such as area or Force.")

        default_height = 190 if kind == "Script" else max(88, 62 + NODE_INPUTS[kind] * 22)
        node = GraphNode(
            self._next_id, kind, value.strip(), x_position, y_position,
            height=default_height,
        )
        self._next_id += 1
        self.nodes[node.id] = node
        return node

    def remove_node(self, node_id: int) -> None:
        if node_id not in self.nodes:
            return
        del self.nodes[node_id]
        self.connections = {
            key: source for key, source in self.connections.items()
            if key[0] != node_id and source != node_id
        }

    def connect(self, source_id: int, target_id: int, input_index: int) -> None:
        source = self.nodes.get(source_id)
        target = self.nodes.get(target_id)
        if source is None or target is None:
            raise ForgeError("both visual nodes must exist", title="Invalid connection")
        if source_id == target_id:
            raise ForgeError("a node cannot connect to itself", title="Invalid connection")
        if source.kind in ("Output", "Script"):
            raise ForgeError(f"a {source.kind} node has no output pin", title="Invalid connection")
        # A Call node takes as many arguments as the function it names, so its pins are open.
        if target.kind != "Call" and not 0 <= input_index < NODE_INPUTS[target.kind]:
            raise ForgeError("the target node has no such input pin", title="Invalid connection")
        if self._would_cycle(source_id, target_id):
            raise ForgeError("this connection would create a cycle", title="Invalid connection")
        self.connections[(target_id, input_index)] = source_id

    def _would_cycle(self, source_id: int, target_id: int) -> bool:
        pending = [target_id]
        visited = set()
        while pending:
            current = pending.pop()
            if current == source_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            pending.extend(
                consumer for (consumer, _), dependency in self.connections.items() if dependency == current
            )
        return False

    @staticmethod
    def _check_name(name: str, role: str) -> None:
        if not _IDENTIFIER.fullmatch(name) or name in _KEYWORDS:
            raise ForgeError(
                f"'{name}' is not a valid {role} variable name",
                title="Invalid visual node",
                hint="Use a name starting with a letter or underscore, such as force_result.",
            )

    def compile(self) -> str:
        outputs = [node for node in self.nodes.values() if node.kind in ("Output", "Output2")]
        scripts = [node for node in self.nodes.values() if node.kind == "Script" and node.value.strip()]
        if not outputs and not scripts:
            raise ForgeError("add an Output or Script node", title="Cannot build visual graph")
        compiled: Dict[int, str] = {}
        visiting = set()

        def expression(node_id: int) -> str:
            if node_id in compiled:
                return compiled[node_id]
            if node_id in visiting:
                raise ForgeError("visual graph contains a cycle", title="Cannot build visual graph")
            node = self.nodes[node_id]
            visiting.add(node_id)
            if node.kind in ("Input", "Constant"):
                result = node.value
            elif node.kind == "Function":
                source_id = self.connections.get((node_id, 0))
                if source_id is None:
                    raise ForgeError(f"{node.value} node {node.id} needs an input connected",
                                     title="Incomplete visual graph")
                result = f"{node.value}({expression(source_id)})"
            elif node.kind == "Call":
                # One input pin per argument, so `area(r)` uses one and `cross(a, b)` two.
                arguments: List[str] = []
                index = 0
                while (node_id, index) in self.connections:
                    arguments.append(expression(self.connections[(node_id, index)]))
                    index += 1
                # A Call node with no pins at all is a bare call, for a function that takes nothing:
                # `pair()`.  A function that needs arguments simply fails when the program runs.
                result = f"{node.value}({', '.join(arguments)})"
            elif node.kind in NODE_SYMBOLS:
                inputs = []
                for index in range(2):
                    source_id = self.connections.get((node_id, index))
                    if source_id is None:
                        raise ForgeError(
                            f"{node.kind} node {node.id} needs both inputs connected",
                            title="Incomplete visual graph",
                        )
                    inputs.append(expression(source_id))
                if node.kind == "Compare":
                    operator, magnitude = _COMPARISONS[node.value]
                    if magnitude is not None:
                        result = f"{magnitude}({inputs[0]}, {inputs[1]})"
                    else:
                        result = f"({inputs[0]} {operator} {inputs[1]})"
                else:
                    result = f"({inputs[0]} {NODE_SYMBOLS[node.kind]} {inputs[1]})"
            elif node.kind in ("Output", "Output2"):
                raise ForgeError("Output nodes are statements, not values", title="Cannot build visual graph")
            else:
                raise ForgeError(f"unsupported node type '{node.kind}'", title="Cannot build visual graph")
            visiting.remove(node_id)
            compiled[node_id] = result
            return result

        lines: List[str] = []
        seen_outputs = set()
        for node in outputs:
            source_id = self.connections.get((node.id, 0))
            if source_id is None:
                raise ForgeError(f"Output node {node.id} needs an input connection",
                                 title="Incomplete visual graph")
            if node.value in seen_outputs:
                raise ForgeError(f"output variable '{node.value}' is used more than once",
                                 title="Invalid visual graph")
            seen_outputs.add(node.value)
        outputs_by_name = {node.value: node for node in outputs}
        ordered_outputs = []
        visited_outputs = set()
        visiting_outputs = set()

        def input_names(node_id: int, visited=None) -> set:
            visited = visited or set()
            if node_id in visited:
                return set()
            visited.add(node_id)
            node = self.nodes[node_id]
            if node.kind == "Input":
                return {node.value}
            found = set()
            for index in range(NODE_INPUTS[node.kind]):
                dependency = self.connections.get((node_id, index))
                if dependency is not None:
                    found.update(input_names(dependency, visited))
            return found

        def order_output(node: GraphNode) -> None:
            if node.id in visited_outputs:
                return
            if node.id in visiting_outputs:
                raise ForgeError(
                    f"shared variables create a circular dependency involving '{node.value}'",
                    title="Invalid visual graph",
                )
            visiting_outputs.add(node.id)
            source_id = self.connections[(node.id, 0)]
            for name in input_names(source_id):
                dependency = outputs_by_name.get(name)
                if dependency is not None:
                    order_output(dependency)
            visiting_outputs.remove(node.id)
            visited_outputs.add(node.id)
            ordered_outputs.append(node)

        for node in outputs:
            order_output(node)
        lines: List[str] = [
            node.value.strip() for node in self.nodes.values()
            if node.kind == "Script" and node.value.strip()
        ]
        for node in ordered_outputs:
            source_id = self.connections[(node.id, 0)]
            if node.kind == "Output2":
                # A two-output node unpacks a function that returns several parts, such as
                # solveODE or bode: `[t, v] = solveODE(...)`.
                names = [part.strip() for part in node.value.split(",")]
                lines.append(f"[{', '.join(names)}] = {expression(source_id)}")
                lines.extend(names)
                continue
            lines.extend((f"{node.value} = {expression(source_id)}", node.value))
        return "\n".join(lines)

    def to_data(self) -> dict:
        return {
            "version": 2,
            "nodes": [
                {"id": node.id, "kind": node.kind, "value": node.value,
                 "x": node.x, "y": node.y, "width": node.width, "height": node.height}
                for node in self.nodes.values()
            ],
            "connections": [
                {"source": source, "target": target, "input": input_index}
                for (target, input_index), source in self.connections.items()
            ],
        }

    @classmethod
    def from_data(cls, data: dict) -> "VisualGraph":
        if not isinstance(data, dict) or data.get("version") not in (1, 2):
            raise ForgeError("unsupported visual graph file version", title="Cannot open graph")
        nodes = data.get("nodes")
        connections = data.get("connections")
        if not isinstance(nodes, list) or not isinstance(connections, list):
            raise ForgeError("visual graph file is malformed", title="Cannot open graph")
        graph = cls()
        ids = set()
        for item in nodes:
            if not isinstance(item, dict):
                raise ForgeError("visual graph node is malformed", title="Cannot open graph")
            node_id = item.get("id")
            if not isinstance(node_id, int) or node_id <= 0 or node_id in ids:
                raise ForgeError("visual graph contains an invalid node ID", title="Cannot open graph")
            ids.add(node_id)
            try:
                kind = item.get("kind")
                if not isinstance(kind, str):
                    raise ValueError("node kind must be text")
                value = item.get("value", "")
                if not isinstance(value, str):
                    raise ValueError("node value must be text")
                node = graph.add_node(
                    kind, value,
                    item.get("x", 80), item.get("y", 80),
                )
            except (AttributeError, TypeError, ValueError) as err:
                raise ForgeError("visual graph node is malformed", title="Cannot open graph") from err
            del graph.nodes[node.id]
            node.id = node_id
            width = item.get("width", node.width)
            height = item.get(
                "height",
                190 if kind == "Script" else max(88, 62 + NODE_INPUTS[kind] * 22),
            )
            if (not isinstance(width, (int, float)) or isinstance(width, bool)
                    or not isfinite(width) or not 150 <= width <= 900
                    or not isinstance(height, (int, float)) or isinstance(height, bool)
                    or not isfinite(height) or not 88 <= height <= 900):
                raise ForgeError("visual graph node has an invalid size", title="Cannot open graph")
            node.width = float(width)
            node.height = float(height)
            graph.nodes[node_id] = node
        graph._next_id = max(ids, default=0) + 1
        for item in connections:
            if not isinstance(item, dict):
                raise ForgeError("visual graph connection is malformed", title="Cannot open graph")
            if (not isinstance(item.get("source"), int) or isinstance(item.get("source"), bool)
                    or not isinstance(item.get("target"), int) or isinstance(item.get("target"), bool)
                    or not isinstance(item.get("input"), int) or isinstance(item.get("input"), bool)):
                raise ForgeError("visual graph connection is malformed", title="Cannot open graph")
            try:
                graph.connect(item["source"], item["target"], item["input"])
            except (KeyError, TypeError) as err:
                raise ForgeError("visual graph connection is malformed", title="Cannot open graph") from err
        return graph
