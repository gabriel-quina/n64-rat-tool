from __future__ import annotations

import json
from pathlib import Path

from romtool.db import RomToolDB
from romtool.segments import NON_TRANSLATABLE_KINDS, build_segment_code_catalog, tokenize_raw_text


def export_jsonl(db: RomToolDB, out_path: Path, limit: int = 1_000_000) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = db.fetch_strings(limit=limit)
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            item = {
                "string_uid": row["string_uid"],
                "start_off": f"0x{row['start_off']:08X}",
                "end_off": f"0x{row['end_off']:08X}",
                "length_bytes": row["length_bytes"],
                "encoding": row["encoding"],
                "kind": row["kind"],
                "confidence": row["confidence"],
                "decoded_text": row["decoded_text"],
                "normalized_text": row["normalized_text"],
                "raw_hex": row["raw_hex"],
                "notes": row["notes"],
            }
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return len(rows)


def export_segment_jsonl(db: RomToolDB, rom_id: int, segment_name: str, out_path: Path, limit: int = 1_000_000) -> int:
    segment = db.get_segment_by_name(rom_id, segment_name)
    if not segment:
        raise ValueError(f"Segmento não encontrado: {segment_name}")
    if segment.kind in NON_TRANSLATABLE_KINDS:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("", encoding="utf-8")
        return 0

    rows = db.fetch_strings_for_segment(rom_id, segment_name, limit=limit)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            tokenized = tokenize_raw_text(bytes.fromhex(row["raw_hex"]), encoding=segment.encoding)
            item = {
                "segment": segment.name,
                "string_uid": row["string_uid"],
                "start_off": f"0x{row['start_off']:08X}",
                "end_off": f"0x{row['end_off']:08X}",
                "kind": row["kind"],
                "prefix_tokens": tokenized.prefix_tokens,
                "text_visible": tokenized.text_visible,
                "suffix_tokens": tokenized.suffix_tokens,
                "decoded_text": row["decoded_text"],
                "translation": "",
                "notes": "",
            }
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    catalog = build_segment_code_catalog([dict(row) for row in rows], encoding=segment.encoding)
    db.replace_segment_code_catalog(
        segment.id,
        [{**item, "example_strings_json": json.dumps(item["example_strings"], ensure_ascii=False)} for item in catalog],
    )
    return len(rows)
