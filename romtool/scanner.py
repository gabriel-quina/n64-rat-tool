from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from romtool.models import StringCandidate
from romtool.profiles.base import BaseProfile


JP_PUNCT = set("。、・「」（）『』！？ー…：；〜")


@dataclass(slots=True)
class ScanResult:
    candidates: list[StringCandidate]
    scanned_bytes: int


def is_printable_ascii(byte: int) -> bool:
    return 0x20 <= byte <= 0x7E


def is_plausible_single_byte(byte: int) -> bool:
    return is_printable_ascii(byte) or byte in {0x09, 0x0A, 0x0D}


def cp932_char_len(data: bytes, i: int) -> int:
    b1 = data[i]
    if is_plausible_single_byte(b1):
        return 1
    if b1 == 0x00:
        return 0
    if (0x81 <= b1 <= 0x9F) or (0xE0 <= b1 <= 0xFC):
        if i + 1 >= len(data):
            return -1
        b2 = data[i + 1]
        if (0x40 <= b2 <= 0x7E) or (0x80 <= b2 <= 0xFC):
            return 2
    return -1


def decode_bytes(raw: bytes, encodings: list[str]) -> tuple[str | None, str | None]:
    for enc in encodings:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return None, None


def score_text(text: str) -> float:
    if not text:
        return 0.0
    total = len(text)
    printable = sum(ch.isprintable() for ch in text)
    jap = sum(("\u3040" <= ch <= "\u30ff") or ("\u4e00" <= ch <= "\u9fff") or ch in JP_PUNCT for ch in text)
    alnum = sum(ch.isalnum() for ch in text)
    weird = sum(ch in {"\ufffd", "\x00"} for ch in text)

    base = (printable / total) * 0.5 + ((jap + alnum) / total) * 0.45
    penalty = (weird / total) * 0.7
    return max(0.0, min(1.0, base - penalty))


def normalize_text(text: str) -> str:
    text = text.replace("\x00", "<NUL>")
    return re.sub(r"\s+", " ", text).strip()


def classify_kind(is_nul_terminated: bool) -> str:
    return "nul_candidate" if is_nul_terminated else "fixed_candidate"


def build_uid(start_off: int, kind: str) -> str:
    suffix = "NUL" if kind == "nul_candidate" else "FIX"
    return f"STR_{start_off:08X}_{suffix}"


def scan_rom_bytes(data: bytes, rom_id: int, run_id: int, profile: BaseProfile) -> ScanResult:
    candidates: list[StringCandidate] = []
    i = 0
    while i < len(data):
        if profile.is_excluded(i):
            i += 1
            continue

        run_start = i
        j = i
        while j < len(data):
            ln = cp932_char_len(data, j)
            if ln <= 0:
                break
            j += ln

        length = j - run_start
        if length >= profile.heuristic.min_length_bytes:
            raw = data[run_start:j]
            decoded, encoding = decode_bytes(raw, profile.encodings)
            if decoded and encoding:
                conf = score_text(decoded)
                next_is_nul = j < len(data) and data[j] == 0x00
                kind = classify_kind(next_is_nul)
                if conf >= profile.heuristic.min_confidence:
                    end_off = j if not next_is_nul else j + 1
                    candidate = StringCandidate(
                        string_uid=build_uid(run_start, kind),
                        rom_id=rom_id,
                        analysis_run_id=run_id,
                        start_off=run_start,
                        end_off=end_off,
                        length_bytes=end_off - run_start,
                        encoding=encoding,
                        kind=kind,
                        confidence=round(conf, 4),
                        raw_hex=data[run_start:end_off].hex(),
                        decoded_text=decoded,
                        normalized_text=normalize_text(decoded),
                    )
                    candidates.append(candidate)
                    i = end_off
                    continue

        i = run_start + 1

    # de-dup por uid estável
    unique: dict[str, StringCandidate] = {c.string_uid: c for c in candidates}
    return ScanResult(candidates=list(unique.values()), scanned_bytes=len(data))


def scan_rom_file(path: Path, rom_id: int, run_id: int, profile: BaseProfile) -> ScanResult:
    return scan_rom_bytes(path.read_bytes(), rom_id=rom_id, run_id=run_id, profile=profile)
