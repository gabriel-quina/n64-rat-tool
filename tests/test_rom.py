from pathlib import Path

from romtool.rom import calculate_fingerprint


def test_fingerprint_detects_z64(tmp_path: Path) -> None:
    p = tmp_path / "a.z64"
    p.write_bytes(b"\x80\x37\x12\x40abc")
    fp = calculate_fingerprint(p)
    assert fp.fmt == "z64"
    assert fp.byte_order == "big"
    assert len(fp.md5) == 32
    assert len(fp.sha1) == 40
