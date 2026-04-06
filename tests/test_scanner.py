from romtool.profiles.generic_n64 import build_profile
from romtool.scanner import scan_rom_bytes


def test_scanner_finds_cp932_and_ignores_most_noise() -> None:
    data = b"\x80\x37\x12\x40" + bytes([0xAA, 0xBB, 0x01, 0x02])
    data += "こんにちは".encode("cp932") + b"\x00"
    data += bytes([0xFF, 0xFE, 0xFD, 0x10, 0x00])
    data += "N64 TEST".encode("cp932")

    result = scan_rom_bytes(data, rom_id=1, run_id=1, profile=build_profile())

    assert len(result.candidates) >= 2
    kinds = {c.kind for c in result.candidates}
    assert "nul_candidate" in kinds
    assert any("こんにちは" in c.decoded_text for c in result.candidates)
