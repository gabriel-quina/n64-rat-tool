from pathlib import Path

from romtool.cli import main


def test_scan_cache_hit_and_force(workspace: Path, synthetic_rom: Path) -> None:
    assert main(["init"]) == 0
    assert main(["import-rom", "--rom", str(synthetic_rom)]) == 0
    assert main(["scan-text"]) == 0
    assert main(["scan-text"]) == 0  # cache hit
    assert main(["scan-text", "--force"]) == 0
