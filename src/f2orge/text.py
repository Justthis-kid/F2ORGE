"""Text: a first-class string value.

Text only comes from quoted literals and functions that return it (e.g. `format()`), so it is
never mixed with quantities by accident: arithmetic on text is a type error.  A vector or matrix
built from text becomes a list of text values, which is what `read_table` columns produce.
"""
from __future__ import annotations

from typing import Union


class Text:
    __slots__ = ("value",)

    def __init__(self, value: str):
        self.value = str(value)

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"Text({self.value!r})"

    def __eq__(self, other) -> bool:
        return isinstance(other, Text) and other.value == self.value

    def __hash__(self) -> int:
        return hash(self.value)


def is_text(value) -> bool:
    return isinstance(value, Text)


def as_text(value) -> str:
    """The text of a Text value, or the printed form of any other value."""
    return value.value if isinstance(value, Text) else str(value)


def text_of(*values: object) -> Union["Text", object]:
    return Text("".join(as_text(v) for v in values))
