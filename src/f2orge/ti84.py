"""Tokenize generated TI-84 BASIC into a transferable .8xp program file.

The text produced by ``transpile(..., "ti-basic")`` is readable source.  A calculator needs the
tokenized form: every command, function and variable is a one- or two-byte token, and the whole
program is wrapped in a TI variable file with a checksum.  This module performs that conversion,
so ``forge transpile program.forge --target ti-basic -o program.8xp`` writes a file that TI
Connect (or another link tool) can send to a TI-83/84 Plus or Plus CE.

Only the subset the transpiler emits is tokenized: assignments, ``Disp``, ``ClrHome``, the
``If 0:Then ... End`` variable map, arithmetic, comparisons, the scientific functions, the
``π``/``θ``/``√``/``⁻¹``/``e^`` tokens, and the 27 single-letter variables.  Anything else is
reported with the offending line instead of being written as a broken program.
"""
from __future__ import annotations

import re
from typing import Dict, Tuple

from .errors import ForgeError

# ---- token table ---------------------------------------------------------------------------
# name -> (token bytes, number of following bytes that belong to the token)
_TOKENS: Dict[str, Tuple[bytes, int]] = {}


def _token(name: str, *codes: int, extra: int = 0) -> None:
    _TOKENS[name] = (bytes(codes), extra)


for _name, _code in (
    ("If", 0xCE), ("Then", 0xCF), ("Else", 0xD0), ("For(", 0xD3), ("While", 0xD7),
    ("Repeat", 0xD6), ("End", 0xD4), ("Pause", 0xD8), ("Lbl", 0xD9), ("Goto", 0xDA),
    ("prgm", 0xDF), ("Return", 0xE1), ("Stop", 0xE2), ("Input", 0xE3), ("Prompt", 0xE4),
    ("Disp", 0xE5), ("DispGraph", 0xE6), ("Output(", 0xE7), ("ClrHome", 0xE8),
    ("ClrTable", 0xE9), ("GetCalc(", 0xEA), ("DelVar", 0xEF), ("GraphStyle(", 0xF0),
    ("ClrList", 0xF1), ("ClrAllLists", 0xF2), ("SetUpEditor", 0xF3), ("Archive", 0xF4),
    ("UnArchive", 0xF5), ("Asm(", 0xF6), ("AsmComp(", 0xF7), ("AsmPrgm", 0xF8),
    ("sin(", 0xC2), ("cos(", 0xC3), ("tan(", 0xC4), ("sin⁻¹(", 0xC5), ("cos⁻¹(", 0xC6),
    ("tan⁻¹(", 0xC7), ("√(", 0xBC), ("³√(", 0xBD), ("ln(", 0xBE), ("e^(", 0xBF),
    ("log(", 0xC0), ("10^(", 0xC1), ("abs(", 0xB9), ("round(", 0xBA), ("iPart(", 0xBB),
    ("int(", 0xB8), ("rand", 0xAB), ("π", 0xAC), ("θ", 0xAD), ("min(", 0xFA), ("max(", 0xFB),
    ("mean(", 0xFC), ("median(", 0xFD), ("sum(", 0xFE), ("prod(", 0xFF), ("not(", 0xA5),
    ("Ans", 0x72), ("⁻¹", 0xB5), ("→", 0x04), ("=", 0x6A), ("≠", 0x6B), ("≥", 0x6C),
    ("≤", 0x6D), ("<", 0x6E), (">", 0x6F), ("+", 0x70), ("-", 0x71), ("*", 0x82),
    ("/", 0x83), ("^", 0xF3), ("(", 0x10), (")", 0x11), (",", 0x2B), (":", 0x3E),
    ("!", 0x21), ('"', 0x2A), ("?", 0x3F), ("[", 0x16), ("]", 0x17), ("{", 0x08),
    ("}", 0x09), ("°", 0x3B), ("ᴇ", 0x3B), ("L₁", 0x5D), ("L₂", 0x5E), ("L₃", 0x5F),
    ("L₄", 0x60), ("L₅", 0x61), ("L₆", 0x62), ("Xmin", 0x0A), ("Xmax", 0x0B),
    ("Ymin", 0x0C), ("Ymax", 0x0D), ("Xres", 0x0E), ("ΔX", 0x8C), ("ΔY", 0x8D),
    ("XFact", 0x8E), ("YFact", 0x8F), ("TblMin", 0x90), ("TblStep", 0x91),
    ("Plot1(", 0x95), ("Plot2(", 0x96), ("Plot3(", 0x97), ("FnOn ", 0x9C), ("FnOff ", 0x9D),
    ("StoreGDB ", 0x9E), ("RecallGDB ", 0x9F), ("Line(", 0xA0), ("Pt-On(", 0xA1),
    ("Pt-Off(", 0xA2), ("Pt-Change(", 0xA3), ("Pxl-On(", 0xA4), ("Pxl-Off(", 0xA5),
    ("Pxl-Change(", 0xA6), ("pxl-Test(", 0xA7), ("Shade(", 0xA8), ("Tangent(", 0xA9),
    ("DrawF ", 0xAA), ("Circle(", 0x9A), ("Horizontal ", 0x93), ("Vertical ", 0x94),
    ("Text(", 0x93), ("ClrDraw", 0x9B), ("AxesOn ", 0x9A), ("AxesOff ", 0x9B),
    ("GridOn ", 0x9C), ("GridOff ", 0x9D), ("LabelOn ", 0x9E), ("LabelOff ", 0x9F),
    ("Degree", 0x9A), ("Radian", 0x9B), ("Normal", 0x9C), ("Sci", 0x9D), ("Eng", 0x9E),
    ("Float", 0x9F), ("Fix ", 0xA0), ("Full", 0xA1), ("Horiz", 0xA2), ("G-T", 0xA3),
    ("Param", 0xA4), ("Polar", 0xA5), ("Seq", 0xA6), ("IndpntAuto", 0xA7),
    ("IndpntAsk", 0xA8), ("DependAuto", 0xA9), ("DependAsk", 0xAA), ("FnInt(", 0xB6),
    ("FnDeriv(", 0xB7), ("expr(", 0xB8),
):
    _token(_name, _code)

# Two-byte tokens: 0xBB is the "extended" prefix on the TI-84 Plus family.
for _name, _code in (
    ("ClrHome", 0x11), ("ClrTable", 0x12), ("GetCalc(", 0x13), ("DelVar", 0x14),
    ("GraphStyle(", 0x15), ("sin(", 0x16), ("cos(", 0x17), ("tan(", 0x18),
    ("sin⁻¹(", 0x19), ("cos⁻¹(", 0x1A), ("tan⁻¹(", 0x1B), ("√(", 0x1C), ("³√(", 0x1D),
    ("ln(", 0x1E), ("e^(", 0x1F), ("log(", 0x20), ("10^(", 0x21), ("abs(", 0x22),
    ("round(", 0x23), ("iPart(", 0x24), ("int(", 0x25), ("rand", 0x26), ("π", 0x27),
    ("θ", 0x28), ("min(", 0x29), ("max(", 0x2A), ("mean(", 0x2B), ("median(", 0x2C),
    ("sum(", 0x2D), ("prod(", 0x2E), ("not(", 0x2F), ("Ans", 0x30), ("⁻¹", 0x31),
    ("→", 0x32), ("=", 0x33), ("≠", 0x34), ("≥", 0x35), ("≤", 0x36), ("<", 0x37),
    (">", 0x38), ("+", 0x39), ("-", 0x3A), ("*", 0x3B), ("/", 0x3C), ("^", 0x3D),
    ("(", 0x3E), (")", 0x3F), (",", 0x40), (":", 0x41), ("!", 0x42), ('"', 0x43),
    ("?", 0x44), ("[", 0x45), ("]", 0x46), ("{", 0x47), ("}", 0x48), ("°", 0x49),
    ("ᴇ", 0x4A), ("L₁", 0x4B), ("L₂", 0x4C), ("L₃", 0x4D), ("L₄", 0x4E), ("L₅", 0x4F),
    ("L₆", 0x50), ("Xmin", 0x51), ("Xmax", 0x52), ("Ymin", 0x53), ("Ymax", 0x54),
    ("Xres", 0x55), ("ΔX", 0x56), ("ΔY", 0x57), ("XFact", 0x58), ("YFact", 0x59),
    ("TblMin", 0x5A), ("TblStep", 0x5B), ("Plot1(", 0x5C), ("Plot2(", 0x5D),
    ("Plot3(", 0x5E), ("FnOn ", 0x5F), ("FnOff ", 0x60), ("StoreGDB ", 0x61),
    ("RecallGDB ", 0x62), ("Line(", 0x63), ("Pt-On(", 0x64), ("Pt-Off(", 0x65),
    ("Pt-Change(", 0x66), ("Pxl-On(", 0x67), ("Pxl-Off(", 0x68), ("Pxl-Change(", 0x69),
    ("pxl-Test(", 0x6A), ("Shade(", 0x6B), ("Tangent(", 0x6C), ("DrawF ", 0x6D),
    ("Circle(", 0x6E), ("Horizontal ", 0x6F), ("Vertical ", 0x70), ("Text(", 0x71),
    ("ClrDraw", 0x72), ("AxesOn ", 0x73), ("AxesOff ", 0x74), ("GridOn ", 0x75),
    ("GridOff ", 0x76), ("LabelOn ", 0x77), ("LabelOff ", 0x78), ("Degree", 0x79),
    ("Radian", 0x7A), ("Normal", 0x7B), ("Sci", 0x7C), ("Eng", 0x7D), ("Float", 0x7E),
    ("Fix ", 0x7F), ("Full", 0x80), ("Horiz", 0x81), ("G-T", 0x82), ("Param", 0x83),
    ("Polar", 0x84), ("Seq", 0x85), ("IndpntAuto", 0x86), ("IndpntAsk", 0x87),
    ("DependAuto", 0x88), ("DependAsk", 0x89), ("FnInt(", 0x8A), ("FnDeriv(", 0x8B),
    ("expr(", 0x8C),
):
    _token(_name, 0xBB, _code)

# Longest names first so "sin⁻¹(" wins over "sin(" and "ClrHome" over "Clr".
_NAMES = sorted(_TOKENS, key=len, reverse=True)
_NAME_PATTERN = re.compile("|".join(re.escape(name) for name in _NAMES))
# Names that start with a letter are matched before single-letter variables, so "ClrHome"
# is not read as C, l, r, H, o, m, e.  A lone letter is still a variable.
_WORD_PATTERN = re.compile("|".join(re.escape(name) for name in _NAMES if name[0].isalpha()))
# A name that starts with a letter must not be followed by another letter, so "Ans" is not
# read as A, n, s and "Disp" is not read as D, i, s, p.
_WORD_END = re.compile(r"(?![A-Za-z])")
_NUMBER = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:ᴇ-?\d+)?")
_VARIABLES = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZθ")
_STRING = re.compile(r'"[^"\n]*"')
_MAX_PROGRAM_BYTES = 24000  # the TI-84 Plus stores programs up to about 24 KB


class Ti84Error(ForgeError):
    title = "Cannot build TI-84 program"


def _encode_number(text: str) -> bytes:
    """TI floating point: 0x00, sign byte, 7 big-endian BCD bytes, exponent byte."""
    if "ᴇ" in text:
        mantissa, exponent = text.split("ᴇ")
        exponent_value = int(exponent)
    else:
        mantissa, exponent_value = text, 0
    negative = mantissa.startswith("-")
    mantissa = mantissa.lstrip("-")
    whole, _, fraction = mantissa.partition(".")
    digits = (whole + fraction).lstrip("0")
    if not digits:
        return bytes(8)
    leading_zeros = len(whole + fraction) - len((whole + fraction).lstrip("0"))
    exponent_value += len(whole) - leading_zeros - 1
    digits = digits.rstrip("0") or "0"
    if len(digits) > 14:
        digits = digits[:14]
    digits = digits.ljust(14, "0")
    bcd = bytes(int(digits[i:i + 2]) for i in range(0, 14, 2))
    return bytes([0x00, 0x80 if negative else 0x00]) + bcd + bytes([exponent_value & 0xFF])


def _decode_number(data: bytes) -> float:
    """Inverse of _encode_number: a checked reference for the binary number format."""
    if data == bytes(8):
        return 0.0
    sign = -1.0 if data[1] & 0x80 else 1.0
    digits = "".join(f"{byte:02d}" for byte in data[2:9])
    exponent = data[9] - 0x80 if data[9] & 0x80 else data[9]
    return sign * float(digits[0] + "." + digits[1:]) * 10 ** (exponent - 1)


def _encode_string(text: str) -> bytes:
    body = text[1:-1]
    if any(ord(char) < 32 or ord(char) > 126 for char in body):
        raise ValueError("strings may only contain printable ASCII characters")
    return bytes([0x2A]) + body.encode("ascii") + bytes([0x2A])


def tokenize_line(line: str) -> bytes:
    """Tokenize one line of TI-BASIC source (a leading ':' is ignored)."""
    if line.startswith(":"):
        line = line[1:]
    out = bytearray()
    position = 0
    while position < len(line):
        char = line[position]
        if char == " ":
            position += 1
            continue
        if char == '"':
            match = _STRING.match(line, position)
            if match is None:
                raise ValueError("unterminated string")
            out += _encode_string(match.group())
            position = match.end()
            continue
        if char.isdigit() or (char == "." and position + 1 < len(line) and line[position + 1].isdigit()):
            match = _NUMBER.match(line, position)
            out += _encode_number(match.group())
            position = match.end()
            continue
        if char.isalpha():
            word = _WORD_PATTERN.match(line, position)
            followed_by_stop = _WORD_END.match(line, word.end()) is not None if word else False
            if word is not None and followed_by_stop:
                token, extra = _TOKENS[word.group()]
                out += token
                position = word.end()
                if extra:
                    out += line[position:position + extra].encode("ascii")
                    position += extra
                continue
            if char in _VARIABLES:
                out.append(ord(char))
                position += 1
                continue
        match = _NAME_PATTERN.match(line, position)
        if match is None:
            raise ValueError(f"unsupported character {char!r}")
        out += _TOKENS[match.group()][0]
        position = match.end()
    return bytes(out)


def tokenize(source: str) -> bytes:
    """Tokenize a whole TI-BASIC program, one ':'-separated line at a time."""
    program = bytearray()
    for number, raw in enumerate(source.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith(":"):
            line = line[1:]
        try:
            program += tokenize_line(line)
        except ValueError as err:
            raise Ti84Error(f"line {number} cannot be tokenized: {err}",
                            hint=f"Offending line: {raw.strip()[:60]}") from None
        program.append(0x3F)  # newline
    if not program:
        raise Ti84Error("the program is empty")
    if len(program) > _MAX_PROGRAM_BYTES:
        raise Ti84Error(f"the tokenized program is {len(program)} bytes; "
                        f"a TI-84 Plus program can hold about {_MAX_PROGRAM_BYTES}")
    return bytes(program)


def _checksum(data: bytes) -> int:
    return sum(data) & 0xFFFF


def build_8xp(source: str, name: str = "F2ORGE") -> bytes:
    """Wrap tokenized TI-BASIC in a .8xp variable file (header, data section, checksum)."""
    program_name = re.sub(r"[^A-Z0-9]", "", name.upper())[:8] or "F2ORGE"
    data = tokenize(source)
    body = bytearray()
    body += bytes([0x05, 0x00])                      # length of the variable name
    body += bytes([0x06])                            # type: protected program
    body += program_name.encode("ascii").ljust(8, b"\x00")
    body += bytes([0x00, 0x00])                      # version
    body += bytes([0x00])                            # program flag
    body += len(data).to_bytes(2, "little")          # bytes 14-15 of the entry
    body += data
    # Layout: 2 name length, 1 type, 8 name, 2 version, 1 flag, 2 data length, data.
    # The name length (always 5) counts the type byte plus the 4 msb bytes of the name.
    # The file checksum covers the whole body; no terminator follows the data.
    header = bytearray(b"**TI83F*")
    header += bytes([0x1A, 0x0A, 0x00])
    comment = b"F2ORGE generated program".ljust(42, b"\x00")
    header += comment
    header += len(body).to_bytes(2, "little")
    header += body
    header += _checksum(body).to_bytes(2, "little")
    return bytes(header)


def write_8xp(path, source: str, name: str = "F2ORGE") -> None:
    """Write a .8xp file for the given TI-BASIC source."""
    from pathlib import Path

    Path(path).write_bytes(build_8xp(source, name))
