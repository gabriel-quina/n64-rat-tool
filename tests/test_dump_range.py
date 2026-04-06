from __future__ import annotations

import json
from pathlib import Path

from romtool.cli import main
from romtool.db import RomToolDB
from romtool.rom import calculate_fingerprint


def _setup_workspace_with_rom(workspace: Path, blob: bytes) -> Path:
    (workspace / "work").mkdir(parents=True, exist_ok=True)
    rom_path = workspace / "sample.z64"
    rom_path.write_bytes(blob)

    db = RomToolDB(workspace / "work" / "romtool.sqlite3")
    db.init_schema()
    db.upsert_rom(calculate_fingerprint(rom_path))
    db.close()
    return rom_path


def test_dump_range_raw_has_offsets(workspace: Path, capsys) -> None:
    blob = b"\x80\x37\x12\x40" + bytes(range(0x20))
    _setup_workspace_with_rom(workspace, blob)

    rc = main(["dump-range", "--start", "0x0", "--end", "0x20", "--mode", "raw", "--chunk-size", "16"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "0x00000000  raw=" in out
    assert "0x00000010  raw=" in out


def test_dump_range_decode_cp932_blob(workspace: Path, capsys) -> None:
    text = "テスト１２３"
    blob = b"\x80\x37\x12\x40" + text.encode("cp932")
    _setup_workspace_with_rom(workspace, blob)

    rc = main([
        "dump-range",
        "--start",
        "0x4",
        "--end",
        hex(4 + len(text.encode("cp932"))),
        "--mode",
        "decode",
        "--encoding",
        "cp932",
    ])

    out = capsys.readouterr().out
    assert rc == 0
    assert "decoded=" in out
    assert "テスト１２３" in out


def test_dump_range_annotate_with_control_like_bytes(workspace: Path, capsys) -> None:
    payload = bytes.fromhex("8166") + "わかりました".encode("cp932") + bytes.fromhex("81708184")
    blob = b"\x80\x37\x12\x40" + payload
    _setup_workspace_with_rom(workspace, blob)

    rc = main([
        "dump-range",
        "--start",
        "0x4",
        "--end",
        hex(4 + len(payload)),
        "--mode",
        "annotate",
        "--encoding",
        "cp932",
    ])

    out = capsys.readouterr().out
    assert rc == 0
    assert "text_guess:" in out
    assert "わかりました" in out
    assert "<CMD_8166>" in out


def test_dump_range_decode_invalid_bytes_safe(workspace: Path, capsys) -> None:
    blob = b"\x80\x37\x12\x40" + bytes([0x82, 0xA0, 0xFF, 0x82, 0xA2])
    _setup_workspace_with_rom(workspace, blob)

    rc = main([
        "dump-range",
        "--start",
        "0x4",
        "--end",
        "0x9",
        "--mode",
        "decode",
        "--encoding",
        "cp932",
    ])

    out = capsys.readouterr().out
    assert rc == 0
    assert "decoded=" in out


def test_dump_range_json_output_stable(workspace: Path, capsys) -> None:
    text = "こんにちは"
    blob = b"\x80\x37\x12\x40" + text.encode("cp932")
    _setup_workspace_with_rom(workspace, blob)

    rc = main([
        "dump-range",
        "--start",
        "0x4",
        "--end",
        hex(4 + len(text.encode("cp932"))),
        "--mode",
        "decode",
        "--encoding",
        "cp932",
        "--json",
    ])

    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert isinstance(payload, list)
    assert payload[0]["offset"] == 4
    assert payload[0]["decoded"].startswith("こん")
