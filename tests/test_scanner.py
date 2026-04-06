from romtool.profiles.base import BaseProfile, HeuristicConfig
from romtool.profiles.generic_n64 import build_profile
from romtool.scanner import scan_rom_bytes


def test_scanner_rejects_binary_noise_that_looks_like_short_text() -> None:
    data = b"\xAA\xBB\xCC\xDD" + b"IW_4" + b"\x01\x02\x03" + b"5)(8" + b"\x00"
    result = scan_rom_bytes(data, rom_id=1, run_id=1, profile=build_profile())
    assert result.candidates == []


def test_scanner_prefers_longest_non_overlapping_match() -> None:
    txt = "これはテストです。よろしくお願いします".encode("cp932") + b"\x00"
    data = b"\x00" + txt
    result = scan_rom_bytes(data, rom_id=1, run_id=1, profile=build_profile())
    assert len(result.candidates) == 1
    assert result.candidates[0].kind == "nul_candidate"


def test_scanner_distinguishes_nul_vs_fixed_thresholds() -> None:
    data = b"\x00"
    data += "かなかなかな".encode("cp932") + b"\x00"
    data += b"\x11\x22\x33"
    data += "AB12CD34".encode("cp932")
    result = scan_rom_bytes(data, rom_id=1, run_id=1, profile=build_profile())

    kinds = {c.kind for c in result.candidates}
    assert "nul_candidate" in kinds
    assert "fixed_candidate" not in kinds


def test_profile_threshold_override_can_allow_fixed_candidate() -> None:
    profile = BaseProfile(
        name="relaxed",
        heuristic=HeuristicConfig(min_length_bytes=4, min_useful_chars_fixed=4, min_score_fixed=0.40),
        encodings=["cp932"],
    )
    data = b"\x00" + "AB12CD34".encode("cp932")
    result = scan_rom_bytes(data, rom_id=1, run_id=1, profile=profile)
    assert any(c.kind == "fixed_candidate" for c in result.candidates)
