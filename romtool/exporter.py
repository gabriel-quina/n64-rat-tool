from __future__ import annotations

import json
from pathlib import Path

from romtool.db import RomToolDB


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
