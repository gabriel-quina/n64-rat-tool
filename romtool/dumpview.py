from __future__ import annotations

import json
from dataclasses import dataclass

from romtool.scanner import cp932_char_len, score_text


@dataclass(slots=True)
class DumpLine:
    offset: int
    raw_hex: str
    decoded: str | None = None


@dataclass(slots=True)
class AnnotatedBlock:
    offset: int
    raw_hex: str
    decoded: str
    text_guess: str
    prefix_tokens: list[str]
    suffix_tokens: list[str]


def chunk_bytes(data: bytes, start: int, chunk_size: int) -> list[DumpLine]:
    lines: list[DumpLine] = []
    for rel in range(0, len(data), chunk_size):
        chunk = data[rel : rel + chunk_size]
        lines.append(DumpLine(offset=start + rel, raw_hex=chunk.hex()))
    return lines


def decode_chunks(data: bytes, start: int, chunk_size: int, encoding: str, only_text: bool) -> list[DumpLine]:
    lines: list[DumpLine] = []
    for line in chunk_bytes(data, start, chunk_size):
        raw = bytes.fromhex(line.raw_hex)
        decoded = raw.decode(encoding, errors="replace")
        if only_text and score_text(decoded) < 0.45:
            continue
        line.decoded = decoded
        lines.append(line)
    return lines


@dataclass(slots=True)
class _Unit:
    start: int
    end: int
    raw: bytes
    decoded: str
    textlike: bool


def _is_textlike_char(ch: str) -> bool:
    if not ch:
        return False
    if ch == "\ufffd":
        return False
    if ch.isspace():
        return True
    return ch.isalnum() or ch in "。、・「」（）『』！？ー…：；〜.,!?-_'\"()[]{}<>$%&*+/=＾〜　"


def _build_units(data: bytes, start: int, encoding: str) -> list[_Unit]:
    units: list[_Unit] = []
    i = 0
    while i < len(data):
        cp_len = cp932_char_len(data, i)
        if cp_len > 0:
            raw = data[i : i + cp_len]
            decoded = raw.decode(encoding, errors="replace")
            units.append(
                _Unit(
                    start=start + i,
                    end=start + i + cp_len,
                    raw=raw,
                    decoded=decoded,
                    textlike=all(_is_textlike_char(ch) for ch in decoded),
                )
            )
            i += cp_len
            continue

        raw = data[i : i + 1]
        units.append(
            _Unit(
                start=start + i,
                end=start + i + 1,
                raw=raw,
                decoded=raw.decode(encoding, errors="replace"),
                textlike=False,
            )
        )
        i += 1
    return units


def _token(unit: _Unit) -> str:
    tag = "TEXTLIKE" if unit.textlike else "CMD"
    return f"<{tag}_{unit.raw.hex().upper()}>"


def annotate_blocks(data: bytes, start: int, encoding: str, only_text: bool) -> list[AnnotatedBlock]:
    units = _build_units(data, start, encoding)
    blocks: list[AnnotatedBlock] = []

    i = 0
    while i < len(units):
        if not units[i].textlike:
            i += 1
            continue

        run_start = i
        while i < len(units) and units[i].textlike:
            i += 1
        run_end = i

        text_guess = "".join(u.decoded for u in units[run_start:run_end]).strip()
        if len(text_guess) < 3:
            continue

        p0 = run_start
        while p0 > 0 and not units[p0 - 1].textlike and (run_start - (p0 - 1)) <= 4:
            p0 -= 1

        s1 = run_end
        while s1 < len(units) and not units[s1].textlike and (s1 - run_end) < 4:
            s1 += 1

        block_units = units[p0:s1]
        raw = b"".join(u.raw for u in block_units)
        decoded = raw.decode(encoding, errors="replace")

        if only_text and score_text(text_guess) < 0.5:
            continue

        blocks.append(
            AnnotatedBlock(
                offset=block_units[0].start,
                raw_hex=raw.hex(),
                decoded=decoded,
                text_guess=text_guess,
                prefix_tokens=[_token(u) for u in units[p0:run_start]],
                suffix_tokens=[_token(u) for u in units[run_end:s1]],
            )
        )

    if not blocks and not only_text:
        raw = data.hex()
        decoded = data.decode(encoding, errors="replace")
        blocks.append(
            AnnotatedBlock(
                offset=start,
                raw_hex=raw,
                decoded=decoded,
                text_guess="",
                prefix_tokens=[],
                suffix_tokens=[],
            )
        )

    return blocks


def lines_to_json(lines: list[DumpLine]) -> str:
    return json.dumps(
        [
            {
                "offset": item.offset,
                "raw_hex": item.raw_hex,
                "decoded": item.decoded,
            }
            for item in lines
        ],
        ensure_ascii=False,
        indent=2,
    )


def blocks_to_json(blocks: list[AnnotatedBlock]) -> str:
    return json.dumps(
        [
            {
                "offset": item.offset,
                "raw_hex": item.raw_hex,
                "decoded": item.decoded,
                "text_guess": item.text_guess,
                "prefix_tokens": item.prefix_tokens,
                "suffix_tokens": item.suffix_tokens,
            }
            for item in blocks
        ],
        ensure_ascii=False,
        indent=2,
    )
