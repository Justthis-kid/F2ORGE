import pytest

from f2orge.errors import ForgeError
from f2orge.ti84 import build_8xp, tokenize, tokenize_line
from f2orge.transpile import transpile
from helpers import TempDir, forge


def test_tokenize_line_encodes_commands_numbers_and_variables():
    assert tokenize_line("ClrHome") == bytes([0xBB, 0x11])
    assert tokenize_line("If 0:Then") == bytes([0xCE]) + bytes(8) + bytes([0xBB, 0x41, 0xCF])
    assert tokenize_line("150.0→A") == bytes([0x00, 0x00, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02,
                                              0xBB, 0x32, 0x41])
    assert tokenize_line('Disp "A=mass"') == bytes([0xE5, 0x2A]) + b"A=mass" + bytes([0x2A])


def test_tokenize_line_handles_functions_and_constants():
    assert tokenize_line("√(9.80665)") == bytes([0xBB, 0x1C]) + bytes(
        [0x00, 0x00, 0x62, 0x06, 0x41, 0x00, 0x00, 0x00, 0x00, 0x00]) + bytes([0xBB, 0x3F])
    assert tokenize_line("sin((π / 2.0))") == bytes([0xBB, 0x16, 0xBB, 0x3E, 0xBB, 0x27, 0xBB, 0x3C]) + bytes(
        [0x00, 0x00, 0x14, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]) + bytes([0xBB, 0x3F, 0xBB, 0x3F])


def test_tokenize_rejects_unknown_characters_with_the_line_number():
    with pytest.raises(ForgeError, match="line 2") as caught:
        tokenize(":ClrHome\n:Disp @\n")
    assert caught.value.title == "Cannot build TI-84 program"


def test_build_8xp_wraps_the_program_in_a_ti_variable_file():
    basic = transpile("answer = 42\nanswer\n", "ti-basic")
    blob = build_8xp(basic, "ANSWER")
    assert blob.startswith(b"**TI83F*\x1a\x0a\x00")
    assert blob[11:53].rstrip(b"\x00") == b"F2ORGE generated program"
    body_length = int.from_bytes(blob[53:55], "little")
    body = blob[55:55 + body_length]
    assert len(blob) == 55 + body_length + 2
    assert int.from_bytes(blob[-2:], "little") == sum(body) & 0xFFFF
    assert body[2] == 0x06
    assert body[3:11] == b"ANSWER\x00\x00"
    assert body[:2] == bytes([0x05, 0x00])
    program_length = int.from_bytes(body[14:16], "little")
    program = body[16:]
    assert program == tokenize(basic)
    assert program_length == len(program)
    assert body[11:14] == bytes([0x00, 0x00, 0x00])
    assert len(program) == program_length
    assert program.endswith(bytes([0x3F]))
    assert len(program) == program_length
    assert program.endswith(bytes([0x3F]))


def test_transpile_cli_writes_a_tokenized_8xp_program():
    with TempDir() as directory:
        source = directory / "program.forge"
        output = directory / "program.8xp"
        source.write_text("distance = 10 ft\nconvert distance -> m\n", encoding="utf-8")
        result = forge("transpile", str(source), "--target", "ti-basic", "-o", str(output))
        assert result.returncode == 0, result.stderr
        assert "tokenized" in result.stdout
        blob = output.read_bytes()
        assert blob.startswith(b"**TI83F*")
        assert b"PROGRAM" in blob[55:70]
        assert b":ClrHome" not in blob
