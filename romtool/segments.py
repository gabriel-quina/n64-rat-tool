from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from romtool.scanner import cp932_char_len

KNOWN_COMMAND_CODES = {"8166", "8168", "8170", "8184", "8195", "819C"}
NON_TRANSLATABLE_KINDS = {"table", "nontranslatable"}


@dataclass(slots=True)
class TokenizedString:
    prefix_tokens: list[str]
    text_visible: str
    suffix_tokens: list[str]
    inline_tokens: list[str]


def _cmd(code: str) -> str:
    return f"<CMD_{code.upper()}>"


def _is_unknown_cmd_lead(byte: int) -> bool:
    return byte < 0x20 or byte in {0x7F, 0xFF}


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

    first_text = next((idx for idx, item in enumerate(units) if item[0] == "text"), None)
    last_text = next((idx for idx in range(len(units) - 1, -1, -1) if units[idx][0] == "text"), None)

    if first_text is None or last_text is None:
        return TokenizedString(
            prefix_tokens=[token for _, token in units],
            text_visible="",
            suffix_tokens=[],
            inline_tokens=[],
        )

    prefix_tokens = [token for kind, token in units[:first_text] if kind == "cmd"]
    suffix_tokens = [token for kind, token in units[last_text + 1 :] if kind == "cmd"]

    text_parts: list[str] = []
    inline_tokens: list[str] = []
    for kind, token in units[first_text : last_text + 1]:
        if kind == "text":
            text_parts.append(token)
        else:
            inline_tokens.append(token)
            text_parts.append(token)

    return TokenizedString(
        prefix_tokens=prefix_tokens,
        text_visible="".join(text_parts),
        suffix_tokens=suffix_tokens,
        inline_tokens=inline_tokens,
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
