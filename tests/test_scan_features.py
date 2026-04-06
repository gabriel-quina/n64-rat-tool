from pathlib import Path

from romtool.cli import main
from romtool.db import RomToolDB


def test_scan_text_range_and_find_offset(workspace: Path, synthetic_rom: Path) -> None:
    assert main(["init"]) == 0
    assert main(["import-rom", "--rom", str(synthetic_rom)]) == 0
    assert main(["scan-text", "--start", "0x00000000", "--end", "0x00000040"]) == 0

    db = RomToolDB(workspace / "work" / "romtool.sqlite3")
    rom = db.get_latest_rom()
    assert rom is not None
    rows = db.fetch_strings(limit=100)
    assert rows
    target_offset = rows[0]["start_off"]
    db.close()

    assert main(["find-offset", "--offset", hex(target_offset)]) == 0
