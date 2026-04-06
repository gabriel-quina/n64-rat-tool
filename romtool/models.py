from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class RomRecord:
    id: int
    path: str
    filename: str
    md5: str
    sha1: str
    size_bytes: int
    fmt: str
    byte_order: str
    created_at: str


@dataclass(slots=True)
class AnalysisRunRecord:
    id: int
    rom_id: int
    profile_name: str
    tool_version: str
    schema_version: str
    started_at: str
    finished_at: str | None
    status: str
    notes: str


@dataclass(slots=True)
class StringCandidate:
    string_uid: str
    rom_id: int
    analysis_run_id: int
    start_off: int
    end_off: int
    length_bytes: int
    encoding: str
    kind: str
    confidence: float
    raw_hex: str
    decoded_text: str
    normalized_text: str
    notes: str = ""


@dataclass(slots=True)
class SegmentRecord:
    id: int
    rom_id: int
    name: str
    start_off: int
    end_off: int
    kind: str
    encoding: str
    notes: str


@dataclass(slots=True)
class ScanStats:
    total_strings: int
    by_kind: dict[str, int]
    by_offset_band: dict[str, int]
    fingerprint: dict[str, str]
    last_scan: AnalysisRunRecord | None


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
