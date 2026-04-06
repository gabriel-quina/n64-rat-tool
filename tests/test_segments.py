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
    assert "<CMD_8170>" not in first["text_visible"]


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


def test_tokenize_real_tail_commands_move_out_of_text_visible() -> None:
    raw = bytes.fromhex(
        "8166824f824f82ed82a982e882dc82b582bd814282bb82ea82c582cd82e082a482a282bf82c78141"
        "89588ec982cc96bc914f82f082ab82df82c482ad82be82b382a2814281708184824f824f00"
    )
    tokenized = tokenize_raw_text(raw)
    assert tokenized.prefix_tokens == ["<CMD_8166>", "００"]
    assert tokenized.text_visible.endswith("ください。")
    assert tokenized.suffix_tokens == ["<CMD_8170>", "<CMD_8184>", "００", "<CMD_00>"]
    assert "<CMD_8170>" not in tokenized.text_visible
    assert tokenized.warnings == []


def test_tokenize_question_tail_command_classified_as_suffix() -> None:
    raw = bytes.fromhex(
        "8166824f825182b182cc82dc82dc82c582cd835a815b837582aa82c582ab82dc82b982f1824182e6"
        "82eb82b582a282cc82c582b782a9814881958250825400"
    )
    tokenized = tokenize_raw_text(raw)
    assert tokenized.text_visible.endswith("よろしいのですか？")
    assert tokenized.suffix_tokens == ["<CMD_8195>", "１５", "<CMD_00>"]
    assert "<CMD_8195>" not in tokenized.text_visible


def test_tokenize_flags_ambiguous_embedded_control_split() -> None:
    raw = bytes.fromhex(
        "8168824f824f824f825182bb82f182c882a982c182b182ed82e982a296bc914f814182a282e282c582"
        "b782ed81428166824f824f82e082a482a282bf82c7814189588ec982cc96bc914f82f082ab82df82c4"
        "82ad82be82b382a2814281708184824f824f00"
    )
    tokenized = tokenize_raw_text(raw)
    assert "ambiguous_embedded_control_split" in tokenized.warnings
    assert "<CMD_8166>" in tokenized.text_visible


def test_tokenize_flags_possible_truncated_start() -> None:
    raw = bytes.fromhex(
        "82ea82c582cd8141819c824f825189588ec982cc8a4a8bc682c582b78166824f8250814281708184824f824f00"
    )
    tokenized = tokenize_raw_text(raw)
    assert tokenized.text_visible.startswith("れでは、")
    assert "warning_possible_truncated_start" in tokenized.warnings


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
            {"string_uid": "B", "raw_hex": ("いいえ".encode("cp932") + bytes.fromhex("81708184824f824f00")).hex()},
            {"string_uid": "C", "raw_hex": ("よろしいですか？".encode("cp932") + bytes.fromhex("81958250825400")).hex()},
        ]
    )
    by_code = {item["code"]: item for item in catalog}
    assert len(catalog) >= 3
    assert "suffix" in by_code["<CMD_8170>"]["positions"]
    assert "inline" not in by_code["<CMD_8170>"]["positions"]
    assert "suffix" in by_code["<CMD_8195>"]["positions"]


def test_nontranslatable_segment_filtered(workspace: Path) -> None:
    _seed_workspace(workspace, b"W" * 0x200)
    assert main(["segment-add", "--name", "ptr_table", "--start", "0x0", "--end", "0x80", "--kind", "table"]) == 0
    out = workspace / "work" / "ptr_table.jsonl"
    assert main(["export-segment", "--name", "ptr_table", "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == ""


def test_export_segment_jsonl_warns_on_ambiguous_entries(workspace: Path) -> None:
    _seed_workspace(workspace, b"Y" * 0x300)
    db = RomToolDB(workspace / "work" / "romtool.sqlite3")
    db.init_schema()
    rom = db.get_latest_rom()
    assert rom is not None
    run_id = db.create_analysis_run(rom.id, "generic_n64")

    problematic = bytes.fromhex(
        "8168824f824f824f825182bb82f182c882a982c182b182ed82e982a296bc914f814182a282e282c582"
        "b782ed81428166824f824f82e082a482a282bf82c7814189588ec982cc96bc914f82f082ab82df82c4"
        "82ad82be82b382a2814281708184824f824f00"
    )
    truncated = bytes.fromhex(
        "82ea82c582cd8141819c824f825189588ec982cc8a4a8bc682c582b78166824f8250814281708184824f824f00"
    )

    for uid, start, raw in [
        ("STR_00000100_NUL", 0x100, problematic),
        ("STR_00000180_NUL", 0x180, truncated),
    ]:
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
                "nul_candidate",
                0.95,
                raw.hex(),
                raw.decode("cp932", errors="replace"),
                raw.decode("cp932", errors="replace"),
            ),
        )
    db.finish_analysis_run(run_id, "success")
    db.conn.commit()
    db.close()

    assert main(["segment-add", "--name", "warnings", "--start", "0x100", "--end", "0x1C0", "--kind", "system_prompt"]) == 0
    out = workspace / "work" / "warnings.jsonl"
    assert main(["export-segment", "--name", "warnings", "--out", str(out)]) == 0

    lines = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    by_uid = {item["string_uid"]: item for item in lines}
    assert "ambiguous_embedded_control_split" in by_uid["STR_00000100_NUL"]["notes"]
    assert "warning_possible_truncated_start" in by_uid["STR_00000180_NUL"]["notes"]
