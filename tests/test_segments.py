from __future__ import annotations

import json
from pathlib import Path

from romtool.cli import main
from romtool.db import RomToolDB
from romtool.rom import calculate_fingerprint
from romtool.segments import build_segment_code_catalog, tokenize_raw_text


def _seed_workspace(workspace: Path, payload: bytes) -> None:
    (workspace / "work").mkdir(parents=True, exist_ok=True)
    rom_path = workspace / "sample.z64"
    rom_path.write_bytes(b"\x80\x37\x12\x40" + payload)

    db = RomToolDB(workspace / "work" / "romtool.sqlite3")
    db.init_schema()
    rom = db.upsert_rom(calculate_fingerprint(rom_path))
    run_id = db.create_analysis_run(rom.id, "generic_n64")

    sample1 = bytes.fromhex("8166") + "わかりました".encode("cp932") + bytes.fromhex("81708184")
    sample2 = bytes.fromhex("8168") + "名前".encode("cp932") + bytes.fromhex("8195")
    sample3 = "選択".encode("cp932") + bytes.fromhex("819c") + "してください".encode("cp932")

    entries = [
        ("STR_00000004_NUL", 0x4, sample1),
        ("STR_00000020_NUL", 0x20, sample2),
        ("STR_00000040_FIX", 0x40, sample3),
    ]

    for uid, start, raw in entries:
        db.conn.execute(
            """
            INSERT INTO string_candidate(
                rom_id, analysis_run_id, string_uid, start_off, end_off, length_bytes,
                encoding, kind, confidence, raw_hex, decoded_text, normalized_text, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')
            """,
            (
                rom.id,
                run_id,
                uid,
                start,
                start + len(raw),
                len(raw),
                "cp932",
                "nul_candidate" if uid.endswith("NUL") else "fixed_candidate",
                0.95,
                raw.hex(),
                raw.decode("cp932", errors="replace"),
                raw.decode("cp932", errors="replace"),
            ),
        )

    db.finish_analysis_run(run_id, "success")
    db.conn.commit()
    db.close()


def test_segment_add_list_show(workspace: Path, capsys) -> None:
    _seed_workspace(workspace, b"X" * 0x200)

    assert main(["segment-add", "--name", "stable_setup_prompts", "--start", "0x4", "--end", "0x80", "--kind", "system_prompt"]) == 0
    assert main(["segment-list"]) == 0
    listed = capsys.readouterr().out
    assert "stable_setup_prompts" in listed

    assert main(["segment-show", "--name", "stable_setup_prompts"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["kind"] == "system_prompt"
    assert shown["encoding"] == "cp932"


def test_export_segment_jsonl(workspace: Path) -> None:
    _seed_workspace(workspace, b"Y" * 0x300)
    assert main(["segment-add", "--name", "stable_setup_prompts", "--start", "0x0", "--end", "0x100", "--kind", "system_prompt"]) == 0

    out = workspace / "work" / "stable_setup_prompts.jsonl"
    assert main(["export-segment", "--name", "stable_setup_prompts", "--out", str(out)]) == 0

    lines = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 3
    first = lines[0]
    assert first["prefix_tokens"] == ["<CMD_8166>"]
    assert first["suffix_tokens"] == ["<CMD_8170>", "<CMD_8184>"]
    assert "わかりました" in first["text_visible"]


def test_tokenize_prefix_text_suffix_and_neutral_tokens() -> None:
    raw = (
        bytes.fromhex("8166")
        + "テキスト".encode("cp932")
        + bytes.fromhex("819c")
        + "です".encode("cp932")
        + bytes([0x01, 0x02])
        + bytes.fromhex("8170")
    )
    tokenized = tokenize_raw_text(raw)
    assert tokenized.prefix_tokens == ["<CMD_8166>"]
    assert "テキスト" in tokenized.text_visible
    assert "<CMD_819C>" in tokenized.text_visible
    assert tokenized.suffix_tokens == ["<CMD_0102>", "<CMD_8170>"]


def test_segment_codes_catalog(workspace: Path, capsys) -> None:
    _seed_workspace(workspace, b"Z" * 0x300)
    assert main(["segment-add", "--name", "stable_setup_prompts", "--start", "0x0", "--end", "0x100", "--kind", "system_prompt"]) == 0
    assert main(["segment-codes", "--name", "stable_setup_prompts", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert any(item["code"] == "<CMD_8166>" for item in payload)
    assert any("prefix" in item["positions"] for item in payload if item["code"] == "<CMD_8166>")

    catalog = build_segment_code_catalog(
        [
            {"string_uid": "A", "raw_hex": (bytes.fromhex("8166") + "はい".encode("cp932")).hex()},
            {"string_uid": "B", "raw_hex": ("いいえ".encode("cp932") + bytes.fromhex("8170")).hex()},
        ]
    )
    assert len(catalog) >= 2


def test_nontranslatable_segment_filtered(workspace: Path) -> None:
    _seed_workspace(workspace, b"W" * 0x200)
    assert main(["segment-add", "--name", "ptr_table", "--start", "0x0", "--end", "0x80", "--kind", "table"]) == 0
    out = workspace / "work" / "ptr_table.jsonl"
    assert main(["export-segment", "--name", "ptr_table", "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == ""
