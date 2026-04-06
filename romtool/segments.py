from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from romtool.scanner import cp932_char_len

KNOWN_COMMAND_CODES = {"8166", "8168", "8170", "8184", "8195", "819C"}
NON_TRANSLATABLE_KINDS = {"table", "nontranslatable"}
FULLWIDTH_DIGITS = frozenset("０１２３４５６７８９")


@dataclass(slots=True)
class TokenizedString:
    prefix_tokens: list[str]
    text_visible: str
    suffix_tokens: list[str]
    inline_tokens: list[str]
    warnings: list[str]


def _cmd(code: str) -> str:
    return f"<CMD_{code.upper()}>"


def _is_unknown_cmd_lead(byte: int) -> bool:
    return byte < 0x20 or byte in {0x7F, 0xFF}


def _is_control_parameter_text(text: str) -> bool:
    return bool(text) and all(ch in FULLWIDTH_DIGITS for ch in text)


def _visible_text_starts_mid_sentence(text: str) -> bool:
    if len(text) < 2:
        return False
    if text.startswith("れでは"):
        return True
    if text[0] not in "ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮー":
        return False
    return text[1] not in FULLWIDTH_DIGITS


def tokenize_raw_text(raw: bytes, encoding: str = "cp932", known_codes: set[str] | None = None) -> TokenizedString:
    known = known_codes or KNOWN_COMMAND_CODES
    units: list[tuple[str, str]] = []
    i = 0
    while i < len(raw):
        if i + 1 < len(raw):
            pair = raw[i : i + 2].hex().upper()
            if pair in known:
                units.append(("cmd", _cmd(pair)))
                i += 2
                continue

        ln = cp932_char_len(raw, i)
        if ln > 0:
            chunk = raw[i : i + ln]
            units.append(("text", chunk.decode(encoding, errors="replace")))
            i += ln
            continue

        if i + 1 < len(raw) and _is_unknown_cmd_lead(raw[i]):
            pair = raw[i : i + 2].hex().upper()
            units.append(("cmd", _cmd(pair)))
            i += 2
            continue

        units.append(("cmd", _cmd(raw[i : i + 1].hex().upper())))
        i += 1

    if not any(kind == "text" for kind, _ in units):
        return TokenizedString(
            prefix_tokens=[token for _, token in units],
            text_visible="",
            suffix_tokens=[],
            inline_tokens=[],
            warnings=[],
        )

    body_start = 0
    prefix_tokens: list[str] = []
    saw_prefix_cmd = False
    while body_start < len(units):
        kind, token = units[body_start]
        if kind == "cmd":
            prefix_tokens.append(token)
            saw_prefix_cmd = True
            body_start += 1
            continue
        if saw_prefix_cmd and _is_control_parameter_text(token):
            text_run: list[str] = []
            while body_start < len(units) and units[body_start][0] == "text" and _is_control_parameter_text(units[body_start][1]):
                text_run.append(units[body_start][1])
                body_start += 1
            prefix_tokens.append("".join(text_run))
            continue
        break

    body_end = len(units) - 1
    suffix_tokens_reversed: list[str] = []
    saw_suffix_cmd = False
    while body_end >= body_start:
        kind, token = units[body_end]
        if kind == "cmd":
            suffix_tokens_reversed.append(token)
            saw_suffix_cmd = True
            body_end -= 1
            continue
        if saw_suffix_cmd and _is_control_parameter_text(token):
            text_run_reversed: list[str] = []
            while body_end >= body_start and units[body_end][0] == "text" and _is_control_parameter_text(units[body_end][1]):
                text_run_reversed.append(units[body_end][1])
                body_end -= 1
            suffix_tokens_reversed.append("".join(reversed(text_run_reversed)))
            continue
        break
    suffix_tokens = list(reversed(suffix_tokens_reversed))

    text_parts: list[str] = []
    inline_tokens: list[str] = []
    warnings: list[str] = []
    visible_units = units[body_start : body_end + 1]
    if not visible_units:
        return TokenizedString(
            prefix_tokens=prefix_tokens,
            text_visible="",
            suffix_tokens=suffix_tokens,
            inline_tokens=[],
            warnings=[],
        )

    for idx, (kind, token) in enumerate(visible_units):
        if kind == "text":
            text_parts.append(token)
        else:
            inline_tokens.append(token)
            text_parts.append(token)
            next_text = visible_units[idx + 1][1] if idx + 1 < len(visible_units) and visible_units[idx + 1][0] == "text" else ""
            if next_text and _is_control_parameter_text(next_text):
                warnings.append("ambiguous_embedded_control_split")

    text_visible = "".join(text_parts)
    if text_visible and _visible_text_starts_mid_sentence(text_visible):
        warnings.append("warning_possible_truncated_start")

    return TokenizedString(
        prefix_tokens=prefix_tokens,
        text_visible=text_visible,
        suffix_tokens=suffix_tokens,
        inline_tokens=inline_tokens,
        warnings=sorted(set(warnings)),
    )


def build_segment_code_catalog(rows: list[dict], encoding: str = "cp932") -> list[dict]:
    stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "prefix": 0, "inline": 0, "suffix": 0, "examples": []})

    for row in rows:
        tokenized = tokenize_raw_text(bytes.fromhex(row["raw_hex"]), encoding=encoding)
        for token in tokenized.prefix_tokens:
            bucket = stats[token]
            bucket["count"] += 1
            bucket["prefix"] += 1
            if row["string_uid"] not in bucket["examples"] and len(bucket["examples"]) < 5:
                bucket["examples"].append(row["string_uid"])
        for token in tokenized.inline_tokens:
            bucket = stats[token]
            bucket["count"] += 1
            bucket["inline"] += 1
            if row["string_uid"] not in bucket["examples"] and len(bucket["examples"]) < 5:
                bucket["examples"].append(row["string_uid"])
        for token in tokenized.suffix_tokens:
            bucket = stats[token]
            bucket["count"] += 1
            bucket["suffix"] += 1
            if row["string_uid"] not in bucket["examples"] and len(bucket["examples"]) < 5:
                bucket["examples"].append(row["string_uid"])

    out: list[dict] = []
    for code in sorted(stats.keys()):
        bucket = stats[code]
        positions = [name for name in ["prefix", "inline", "suffix"] if bucket[name] > 0]
        out.append(
            {
                "code": code,
                "count": bucket["count"],
                "positions": positions,
                "position_counts": {
                    "prefix": bucket["prefix"],
                    "inline": bucket["inline"],
                    "suffix": bucket["suffix"],
                },
                "example_strings": bucket["examples"],
            }
        )
    return out
