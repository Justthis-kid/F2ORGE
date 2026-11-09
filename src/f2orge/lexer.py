"""Tokenizer.

Newlines are statement separators, so they are tokens.  Superscript exponents (m/s²) become a
SUPER token carrying an integer.  The line after `import` is read raw because import paths
(./formulas/Force.eq) are not valid expressions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from .errors import ForgeSyntaxError, Source, Span

SUPER_CHARS = "⁰¹²³⁴⁵⁶⁷⁸⁹⁻"
_SUPER_TO_ASCII = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")
_UNICODE_OPS = {"×": "*", "·": "*", "÷": "/", "−": "-", "→": "->"}
_OPS = set("+-*/^=(),.:;{}[]<>")
_NUMBER = re.compile(r"(?:[0-9][0-9_]*(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_WORD_EXTRA = "_µΩ°"

KEYWORDS = {
    "eq", "import", "export", "solve", "convert", "print", "for", "plot",
    "worksheet", "input", "output", "graph", "over", "from", "to",
}


@dataclass
class Token:
    kind: str  # num ident str super op nl path eof
    text: str
    start: int
    end: int
    value: object = None


def _is_word_start(ch: str) -> bool:
    return (ch.isalpha() or ch in _WORD_EXTRA) and ch not in SUPER_CHARS


def _is_word_char(ch: str) -> bool:
    return (ch.isalnum() or ch in _WORD_EXTRA) and ch not in SUPER_CHARS


def tokenize(source: Source) -> List[Token]:
    text = source.text
    n = len(text)
    toks: List[Token] = []
    i = 0

    def fail(message: str, start: int, end: int, hint: Optional[str] = None):
        raise ForgeSyntaxError(message, Span(source, start, end), hint=hint)

    while i < n:
        ch = text[i]
        if ch in " \t\r":
            i += 1
        elif ch == "\\" and text[i + 1 : i + 2] in ("\n", "\r"):  # explicit line continuation
            i += 1
            while i < n and text[i] in "\r\n":
                i += 1
        elif ch == "\n":
            if toks and toks[-1].kind != "nl":
                toks.append(Token("nl", "\n", i, i + 1))
            i += 1
        elif ch == "#" or text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif ch in "0123456789" or (ch == "." and text[i + 1 : i + 2] in tuple("0123456789") and text[i + 1 : i + 2]):
            m = _NUMBER.match(text, i)
            toks.append(Token("num", m.group(), i, m.end(), float(m.group().replace("_", ""))))
            i = m.end()
        elif _is_word_start(ch):
            j = i + 1
            while j < n and _is_word_char(text[j]):
                j += 1
            word = text[i:j]
            at_start = not toks or toks[-1].kind == "nl" or (toks[-1].kind == "op" and toks[-1].text in (";", "{"))
            toks.append(Token("ident", word, i, j))
            i = j
            if word == "import" and at_start:  # the rest of the line is a name or a file path
                k = i
                while k < n and text[k] != "\n":
                    k += 1
                raw = text[i:k]
                stripped = raw.strip()
                if stripped:
                    first = i + (len(raw) - len(raw.lstrip()))
                    toks.append(Token("path", stripped.strip("\"'"), first, first + len(stripped)))
                i = k
        elif ch == '"':
            j = i + 1
            out: List[str] = []
            while j < n and text[j] != '"':
                if text[j] == "\n":
                    fail("This text is missing its closing quote", i, j, 'End the text with a " on the same line.')
                if text[j] == "\\" and j + 1 < n:
                    out.append({"n": "\n", "t": "\t"}.get(text[j + 1], text[j + 1]))
                    j += 2
                else:
                    out.append(text[j])
                    j += 1
            if j >= n:
                fail("This text is missing its closing quote", i, n, 'End the text with a ".')
            toks.append(Token("str", text[i : j + 1], i, j + 1, "".join(out)))
            i = j + 1
        elif ch in SUPER_CHARS:
            j = i
            while j < n and text[j] in SUPER_CHARS:
                j += 1
            toks.append(Token("super", text[i:j], i, j, int(text[i:j].translate(_SUPER_TO_ASCII))))
            i = j
        elif ch == "-" and text[i + 1 : i + 2] == ">":
            toks.append(Token("op", "->", i, i + 2))
            i += 2
        elif ch in _UNICODE_OPS:
            mapped = _UNICODE_OPS[ch]
            toks.append(Token("op", mapped, i, i + 1))
            i += 1
        elif ch in _OPS:
            toks.append(Token("op", ch, i, i + 1))
            i += 1
        else:
            fail(f"Unexpected character {ch!r}", i, i + 1)
    if toks and toks[-1].kind != "nl":
        toks.append(Token("nl", "\n", n, n))
    toks.append(Token("eof", "", n, n))
    return toks
