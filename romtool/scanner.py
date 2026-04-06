from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from romtool.models import StringCandidate
from romtool.profiles.base import BaseProfile, HeuristicConfig


JP_PUNCT = set("。、・「」（）『』！？ー…：；〜")
FULLWIDTH_DIGITS = set("０１２３４５６７８９")
FULLWIDTH_LATIN = set("ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ")


@dataclass(slots=True)
class ScanResult:
    candidates: list[StringCandidate]
    scanned_bytes: int


@dataclass(slots=True)
class TextMetrics:
    total: int
    useful_chars: int
    score: float
    symbol_ratio: float


def is_printable_ascii(byte: int) -> bool:
    return 0x20 <= byte <= 0x7E


def is_plausible_single_byte(byte: int) -> bool:
    return is_printable_ascii(byte) or byte in {0x09, 0x0A, 0x0D}


def is_textish_byte(byte: int) -> bool:
    return is_plausible_single_byte(byte) or (0x81 <= byte <= 0x9F) or (0xE0 <= byte <= 0xFC)


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


def _is_hiragana(ch: str) -> bool:
    return "\u3040" <= ch <= "\u309f"


def _is_katakana(ch: str) -> bool:
    return "\u30a0" <= ch <= "\u30ff"


def _is_kanji(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def _is_fullwidth_alnum(ch: str) -> bool:
    return ch in FULLWIDTH_DIGITS or ch in FULLWIDTH_LATIN


def _is_ascii_symbol(ch: str) -> bool:
    return ch.isascii() and ch.isprintable() and not ch.isalnum() and not ch.isspace()


def score_text(text: str, anchored: bool) -> TextMetrics:
    if not text:
        return TextMetrics(total=0, useful_chars=0, score=0.0, symbol_ratio=1.0)

    total = len(text)
    hira = sum(_is_hiragana(ch) for ch in text)
    kata = sum(_is_katakana(ch) for ch in text)
    kanji = sum(_is_kanji(ch) for ch in text)
    jp_punct = sum(ch in JP_PUNCT for ch in text)
    fw_alnum = sum(_is_fullwidth_alnum(ch) for ch in text)
    ascii_alnum = sum(ch.isascii() and ch.isalnum() for ch in text)
    spaces = sum(ch.isspace() for ch in text)
    ascii_sym = sum(_is_ascii_symbol(ch) for ch in text)
    weird = sum((not ch.isprintable()) or ch == "\ufffd" for ch in text)

    japanese = hira + kata + kanji + jp_punct
    useful = japanese + fw_alnum + ascii_alnum

    japanese_ratio = japanese / total
    ascii_ratio = ascii_alnum / total
    useful_ratio = useful / total
    score = 0.35 + useful_ratio * 0.30 + japanese_ratio * 0.28 + min(0.10, ascii_ratio * 0.10)

    # Penaliza mistura estranha e símbolo excessivo.
    symbol_ratio = ascii_sym / total
    mixed_ascii_kanji = ascii_alnum > 0 and kanji > 0 and (ascii_alnum / total) > 0.25 and (kanji / total) > 0.10
    short_random = total < 8 and japanese == 0 and ascii_alnum <= 3

    score -= (symbol_ratio * 0.80)
    score -= (weird / total) * 1.20
    score -= (spaces / total) * 0.25
    if mixed_ascii_kanji:
        score -= 0.28
    if short_random:
        score -= 0.24
    if total < 5:
        score -= 0.20
    if not anchored:
        score -= 0.20

    return TextMetrics(total=total, useful_chars=useful, score=max(0.0, min(1.0, score)), symbol_ratio=symbol_ratio)


def normalize_text(text: str) -> str:
    text = text.replace("\x00", "<NUL>")
    return re.sub(r"\s+", " ", text).strip()


def classify_kind(is_nul_terminated: bool) -> str:
    return "nul_candidate" if is_nul_terminated else "fixed_candidate"


def build_uid(start_off: int, kind: str) -> str:
    suffix = "NUL" if kind == "nul_candidate" else "FIX"
    return f"STR_{start_off:08X}_{suffix}"


def _is_anchor(data: bytes, start: int, cfg: HeuristicConfig) -> bool:
    if start == 0:
        return cfg.anchor_at_scan_start

    prev = data[start - 1]
    if cfg.anchor_after_nul and prev == 0x00:
        return True

    if cfg.anchor_after_non_text and not is_textish_byte(prev):
        return True

    if cfg.anchor_binary_transition:
        window = min(cfg.binary_window, start)
        if window > 0:
            prefix = data[start - window:start]
            textish = sum(is_textish_byte(b) for b in prefix)
            ratio = textish / window
            if ratio <= cfg.binary_textish_ratio_max:
                return True

    return False


def _candidate_rank(item: StringCandidate) -> tuple[int, float, int]:
    nul_bonus = 1 if item.kind == "nul_candidate" else 0
    useful = len([c for c in item.decoded_text if c.isalnum() or _is_hiragana(c) or _is_katakana(c) or _is_kanji(c) or c in JP_PUNCT])
    return (useful, item.confidence, nul_bonus)


def _overlap_len(a: StringCandidate, b: StringCandidate) -> int:
    return max(0, min(a.end_off, b.end_off) - max(a.start_off, b.start_off))


def _select_non_overlapping(candidates: list[StringCandidate], max_overlap: int) -> list[StringCandidate]:
    selected: list[StringCandidate] = []
    for cand in sorted(candidates, key=lambda x: (_candidate_rank(x), x.length_bytes, -x.start_off), reverse=True):
        conflict_idx: int | None = None
        for idx, cur in enumerate(selected):
            if _overlap_len(cand, cur) > max_overlap:
                conflict_idx = idx
                break
        if conflict_idx is None:
            selected.append(cand)
            continue

        cur = selected[conflict_idx]
        if _candidate_rank(cand) > _candidate_rank(cur):
            selected[conflict_idx] = cand

    return sorted(selected, key=lambda x: x.start_off)


def scan_rom_bytes(data: bytes, rom_id: int, run_id: int, profile: BaseProfile, base_offset: int = 0) -> ScanResult:
    candidates: list[StringCandidate] = []
    i = 0
    cfg = profile.heuristic

    while i < len(data):
        if profile.is_excluded(base_offset + i):
            i += 1
            continue

        if not _is_anchor(data, i, cfg):
            i += 1
            continue

        run_start = i
        j = i
        while j < len(data) and not profile.is_excluded(base_offset + j):
            ln = cp932_char_len(data, j)
            if ln <= 0:
                break
            j += ln

        length = j - run_start
        if length < cfg.min_length_bytes:
            i = run_start + 1
            continue

        raw = data[run_start:j]
        decoded, encoding = decode_bytes(raw, profile.encodings)
        if not decoded or not encoding:
            i = run_start + 1
            continue

        next_is_nul = j < len(data) and data[j] == 0x00
        kind = classify_kind(next_is_nul)
        metrics = score_text(decoded, anchored=True)
        if metrics.symbol_ratio > cfg.max_symbol_ratio:
            i = run_start + 1
            continue

        if kind == "nul_candidate":
            if metrics.useful_chars < cfg.min_useful_chars_nul or metrics.score < cfg.min_score_nul:
                i = run_start + 1
                continue
        else:
            if metrics.useful_chars < cfg.min_useful_chars_fixed or metrics.score < cfg.min_score_fixed:
                i = run_start + 1
                continue

        end_off = j + 1 if next_is_nul else j
        abs_start = base_offset + run_start
        abs_end = base_offset + end_off
        candidate = StringCandidate(
            string_uid=build_uid(abs_start, kind),
            rom_id=rom_id,
            analysis_run_id=run_id,
            start_off=abs_start,
            end_off=abs_end,
            length_bytes=abs_end - abs_start,
            encoding=encoding,
            kind=kind,
            confidence=round(metrics.score, 4),
            raw_hex=data[run_start:end_off].hex(),
            decoded_text=decoded,
            normalized_text=normalize_text(decoded),
        )
        candidates.append(candidate)
        i = run_start + 1

    selected = _select_non_overlapping(candidates, max_overlap=cfg.max_overlap_bytes)
    unique: dict[str, StringCandidate] = {c.string_uid: c for c in selected}
    return ScanResult(candidates=list(unique.values()), scanned_bytes=len(data))


def scan_rom_file(
    path: Path,
    rom_id: int,
    run_id: int,
    profile: BaseProfile,
    start: int | None = None,
    end: int | None = None,
) -> ScanResult:
    blob = path.read_bytes()
    scan_start = 0 if start is None else max(0, start)
    scan_end = len(blob) if end is None else min(len(blob), end)
    if scan_start >= scan_end:
        return ScanResult(candidates=[], scanned_bytes=0)
    data = blob[scan_start:scan_end]
    return scan_rom_bytes(data, rom_id=rom_id, run_id=run_id, profile=profile, base_offset=scan_start)
