import json
from pathlib import Path

from romtool.db import RomToolDB
from romtool.exporter import export_jsonl
from romtool.models import StringCandidate


def test_export_jsonl(tmp_path: Path) -> None:
    db = RomToolDB(tmp_path / "db.sqlite3")
    db.init_schema()
    db.conn.execute(
        """INSERT INTO rom(path, filename, md5, sha1, size_bytes, format, byte_order, created_at)
        VALUES ('x','x.z64','m','s',1,'z64','big','t')"""
    )
    rom_id = db.conn.execute("SELECT id FROM rom").fetchone()[0]
    run_id = db.create_analysis_run(rom_id, "generic_n64")
    db.finish_analysis_run(run_id, "success")

    db.insert_string_candidates([
        StringCandidate(
            string_uid="STR_00000010_NUL",
            rom_id=rom_id,
            analysis_run_id=run_id,
            start_off=0x10,
            end_off=0x20,
            length_bytes=0x10,
            encoding="cp932",
            kind="nul_candidate",
            confidence=0.9,
            raw_hex="aa",
            decoded_text="abc",
            normalized_text="abc",
        )
    ])

    out = tmp_path / "strings.jsonl"
    n = export_jsonl(db, out)
    db.close()

    assert n == 1
    line = out.read_text(encoding="utf-8").strip()
    item = json.loads(line)
    assert item["string_uid"] == "STR_00000010_NUL"
