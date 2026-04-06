from pathlib import Path

from romtool.db import RomToolDB
from romtool.rom import calculate_fingerprint


def test_db_schema_and_import(tmp_path: Path) -> None:
    db = RomToolDB(tmp_path / "x.sqlite3")
    db.init_schema()

    rom = tmp_path / "r.z64"
    rom.write_bytes(b"\x80\x37\x12\x40ROMDATA")
    fp = calculate_fingerprint(rom)
    row = db.upsert_rom(fp)

    assert row.filename == "r.z64"
    assert db.get_latest_rom() is not None
    db.close()
