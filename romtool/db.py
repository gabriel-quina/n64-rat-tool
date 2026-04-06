from __future__ import annotations

import sqlite3
from pathlib import Path

from romtool import ANALYSIS_VERSION, SCHEMA_VERSION, __version__
from romtool.models import AnalysisRunRecord, RomRecord, SegmentRecord, StringCandidate, now_iso
from romtool.rom import RomFingerprint


class RomToolDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS rom (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                filename TEXT NOT NULL,
                md5 TEXT NOT NULL,
                sha1 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                format TEXT NOT NULL,
                byte_order TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS ux_rom_sha1 ON rom(sha1);

            CREATE TABLE IF NOT EXISTS analysis_run (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rom_id INTEGER NOT NULL,
                profile_name TEXT NOT NULL,
                tool_version TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                analysis_version TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(rom_id) REFERENCES rom(id)
            );

            CREATE INDEX IF NOT EXISTS ix_analysis_run_lookup
            ON analysis_run(rom_id, profile_name, schema_version, analysis_version, status);

            CREATE TABLE IF NOT EXISTS string_candidate (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rom_id INTEGER NOT NULL,
                analysis_run_id INTEGER NOT NULL,
                string_uid TEXT NOT NULL,
                start_off INTEGER NOT NULL,
                end_off INTEGER NOT NULL,
                length_bytes INTEGER NOT NULL,
                encoding TEXT NOT NULL,
                kind TEXT NOT NULL,
                confidence REAL NOT NULL,
                raw_hex TEXT NOT NULL,
                decoded_text TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(rom_id) REFERENCES rom(id),
                FOREIGN KEY(analysis_run_id) REFERENCES analysis_run(id)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS ux_string_uid ON string_candidate(string_uid);
            CREATE INDEX IF NOT EXISTS ix_string_rom ON string_candidate(rom_id, start_off);

            CREATE TABLE IF NOT EXISTS segment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rom_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                start_off INTEGER NOT NULL,
                end_off INTEGER NOT NULL,
                kind TEXT NOT NULL,
                encoding TEXT NOT NULL DEFAULT 'cp932',
                notes TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(rom_id) REFERENCES rom(id)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS ux_segment_rom_name ON segment(rom_id, name);

            CREATE TABLE IF NOT EXISTS segment_code_catalog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                segment_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                count INTEGER NOT NULL,
                prefix_count INTEGER NOT NULL DEFAULT 0,
                inline_count INTEGER NOT NULL DEFAULT 0,
                suffix_count INTEGER NOT NULL DEFAULT 0,
                example_strings_json TEXT NOT NULL DEFAULT '[]',
                FOREIGN KEY(segment_id) REFERENCES segment(id)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS ux_segment_code ON segment_code_catalog(segment_id, code);
            """
        )
        self._ensure_segment_columns()
        self.conn.commit()

    def _ensure_segment_columns(self) -> None:
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(segment)").fetchall()}
        if "name" not in columns:
            self.conn.execute("ALTER TABLE segment ADD COLUMN name TEXT")
            self.conn.execute("UPDATE segment SET name = 'segment_' || id WHERE name IS NULL OR name = ''")
        if "encoding" not in columns:
            self.conn.execute("ALTER TABLE segment ADD COLUMN encoding TEXT")
        self.conn.execute("UPDATE segment SET encoding='cp932' WHERE encoding IS NULL OR encoding=''")

    def upsert_rom(self, fp: RomFingerprint) -> RomRecord:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM rom WHERE sha1 = ?", (fp.sha1,))
        row = cur.fetchone()
        if row:
            return self._row_to_rom(row)

        cur.execute(
            """
            INSERT INTO rom(path, filename, md5, sha1, size_bytes, format, byte_order, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (str(fp.path), fp.filename, fp.md5, fp.sha1, fp.size_bytes, fp.fmt, fp.byte_order, now_iso()),
        )
        self.conn.commit()
        cur.execute("SELECT * FROM rom WHERE id=?", (cur.lastrowid,))
        return self._row_to_rom(cur.fetchone())

    def get_latest_rom(self) -> RomRecord | None:
        row = self.conn.execute("SELECT * FROM rom ORDER BY id DESC LIMIT 1").fetchone()
        return self._row_to_rom(row) if row else None

    def create_analysis_run(self, rom_id: int, profile_name: str, status: str = "started") -> int:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO analysis_run(
                rom_id, profile_name, tool_version, schema_version, analysis_version,
                started_at, status, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, '')
            """,
            (rom_id, profile_name, __version__, SCHEMA_VERSION, ANALYSIS_VERSION, now_iso(), status),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_analysis_run(self, run_id: int, status: str, notes: str = "") -> None:
        self.conn.execute(
            "UPDATE analysis_run SET finished_at=?, status=?, notes=? WHERE id=?",
            (now_iso(), status, notes, run_id),
        )
        self.conn.commit()

    def last_successful_run(self, rom_id: int, profile_name: str) -> AnalysisRunRecord | None:
        row = self.conn.execute(
            """
            SELECT * FROM analysis_run
            WHERE rom_id=? AND profile_name=?
              AND schema_version=? AND analysis_version=? AND status='success'
            ORDER BY id DESC LIMIT 1
            """,
            (rom_id, profile_name, SCHEMA_VERSION, ANALYSIS_VERSION),
        ).fetchone()
        return self._row_to_run(row) if row else None

    def insert_string_candidates(self, items: list[StringCandidate]) -> int:
        cur = self.conn.cursor()
        inserted = 0
        for item in items:
            cur.execute(
                """
                INSERT OR IGNORE INTO string_candidate(
                    rom_id, analysis_run_id, string_uid, start_off, end_off, length_bytes,
                    encoding, kind, confidence, raw_hex, decoded_text, normalized_text, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.rom_id,
                    item.analysis_run_id,
                    item.string_uid,
                    item.start_off,
                    item.end_off,
                    item.length_bytes,
                    item.encoding,
                    item.kind,
                    item.confidence,
                    item.raw_hex,
                    item.decoded_text,
                    item.normalized_text,
                    item.notes,
                ),
            )
            inserted += cur.rowcount
        self.conn.commit()
        return inserted

    def fetch_string_by_uid(self, uid: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM string_candidate WHERE string_uid=?", (uid,)).fetchone()

    def fetch_strings(self, limit: int = 1000) -> list[sqlite3.Row]:
        cur = self.conn.execute(
            "SELECT * FROM string_candidate ORDER BY start_off LIMIT ?",
            (limit,),
        )
        return cur.fetchall()

    def find_string_by_offset(self, rom_id: int, offset: int) -> sqlite3.Row | None:
        return self.conn.execute(
            """
            SELECT * FROM string_candidate
            WHERE rom_id=? AND ((start_off <= ? AND end_off > ?) OR start_off = ?)
            ORDER BY CASE WHEN start_off = ? THEN 0 ELSE 1 END, confidence DESC, length_bytes DESC
            LIMIT 1
            """,
            (rom_id, offset, offset, offset, offset),
        ).fetchone()

    def fetch_candidates_covering_offset(self, rom_id: int, offset: int, limit: int = 20) -> list[sqlite3.Row]:
        cur = self.conn.execute(
            """
            SELECT * FROM string_candidate
            WHERE rom_id=? AND start_off <= ? AND end_off > ?
            ORDER BY start_off
            LIMIT ?
            """,
            (rom_id, offset, offset, limit),
        )
        return cur.fetchall()

    def fetch_candidates_in_range(self, rom_id: int, start: int, end: int, limit: int = 200) -> list[sqlite3.Row]:
        cur = self.conn.execute(
            """
            SELECT * FROM string_candidate
            WHERE rom_id=? AND NOT (end_off <= ? OR start_off >= ?)
            ORDER BY start_off
            LIMIT ?
            """,
            (rom_id, start, end, limit),
        )
        return cur.fetchall()

    def upsert_segment(
        self,
        rom_id: int,
        name: str,
        start_off: int,
        end_off: int,
        kind: str,
        encoding: str = "cp932",
        notes: str = "",
    ) -> SegmentRecord:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO segment(rom_id, name, start_off, end_off, kind, encoding, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rom_id, name) DO UPDATE SET
                start_off=excluded.start_off,
                end_off=excluded.end_off,
                kind=excluded.kind,
                encoding=excluded.encoding,
                notes=excluded.notes
            """,
            (rom_id, name, start_off, end_off, kind, encoding, notes),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM segment WHERE rom_id=? AND name=?", (rom_id, name)).fetchone()
        return self._row_to_segment(row)

    def list_segments(self, rom_id: int) -> list[SegmentRecord]:
        rows = self.conn.execute("SELECT * FROM segment WHERE rom_id=? ORDER BY start_off", (rom_id,)).fetchall()
        return [self._row_to_segment(row) for row in rows]

    def get_segment_by_name(self, rom_id: int, name: str) -> SegmentRecord | None:
        row = self.conn.execute("SELECT * FROM segment WHERE rom_id=? AND name=?", (rom_id, name)).fetchone()
        return self._row_to_segment(row) if row else None

    def fetch_strings_for_segment(self, rom_id: int, segment_name: str, limit: int = 100000) -> list[sqlite3.Row]:
        cur = self.conn.execute(
            """
            SELECT sc.*
            FROM string_candidate sc
            JOIN segment s ON s.rom_id=sc.rom_id
            WHERE sc.rom_id=? AND s.name=? AND NOT (sc.end_off <= s.start_off OR sc.start_off >= s.end_off)
            ORDER BY sc.start_off
            LIMIT ?
            """,
            (rom_id, segment_name, limit),
        )
        return cur.fetchall()

    def replace_segment_code_catalog(self, segment_id: int, items: list[dict]) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM segment_code_catalog WHERE segment_id=?", (segment_id,))
        for item in items:
            cur.execute(
                """
                INSERT INTO segment_code_catalog(
                    segment_id, code, count, prefix_count, inline_count, suffix_count, example_strings_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    segment_id,
                    item["code"],
                    item["count"],
                    item["position_counts"]["prefix"],
                    item["position_counts"]["inline"],
                    item["position_counts"]["suffix"],
                    item["example_strings_json"],
                ),
            )
        self.conn.commit()

    def fetch_segment_code_catalog(self, segment_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM segment_code_catalog WHERE segment_id=? ORDER BY count DESC, code ASC",
            (segment_id,),
        ).fetchall()

    def count_strings(self, rom_id: int) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS c FROM string_candidate WHERE rom_id=?", (rom_id,)).fetchone()
        return int(row["c"])

    def count_by_kind(self, rom_id: int) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT kind, COUNT(*) AS c FROM string_candidate WHERE rom_id=? GROUP BY kind",
            (rom_id,),
        ).fetchall()
        return {r["kind"]: int(r["c"]) for r in rows}

    def count_by_offset_band(self, rom_id: int, band_size: int = 0x100000) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT start_off FROM string_candidate WHERE rom_id=?",
            (rom_id,),
        ).fetchall()
        bands: dict[str, int] = {}
        for row in rows:
            start = (int(row["start_off"]) // band_size) * band_size
            end = start + band_size - 1
            key = f"0x{start:08X}-0x{end:08X}"
            bands[key] = bands.get(key, 0) + 1
        return dict(sorted(bands.items()))

    def avg_length_by_kind(self, rom_id: int) -> dict[str, float]:
        rows = self.conn.execute(
            "SELECT kind, AVG(length_bytes) AS avg_len FROM string_candidate WHERE rom_id=? GROUP BY kind",
            (rom_id,),
        ).fetchall()
        return {r["kind"]: float(r["avg_len"]) for r in rows}

    def top_confidence(self, rom_id: int, limit: int = 5) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT string_uid, start_off, kind, confidence, normalized_text
            FROM string_candidate
            WHERE rom_id=?
            ORDER BY confidence DESC, length_bytes DESC
            LIMIT ?
            """,
            (rom_id, limit),
        ).fetchall()

    @staticmethod
    def _row_to_rom(row: sqlite3.Row) -> RomRecord:
        return RomRecord(
            id=row["id"],
            path=row["path"],
            filename=row["filename"],
            md5=row["md5"],
            sha1=row["sha1"],
            size_bytes=row["size_bytes"],
            fmt=row["format"],
            byte_order=row["byte_order"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> AnalysisRunRecord:
        return AnalysisRunRecord(
            id=row["id"],
            rom_id=row["rom_id"],
            profile_name=row["profile_name"],
            tool_version=row["tool_version"],
            schema_version=row["schema_version"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            status=row["status"],
            notes=row["notes"],
        )

    @staticmethod
    def _row_to_segment(row: sqlite3.Row) -> SegmentRecord:
        return SegmentRecord(
            id=row["id"],
            rom_id=row["rom_id"],
            name=row["name"],
            start_off=row["start_off"],
            end_off=row["end_off"],
            kind=row["kind"],
            encoding=row["encoding"],
            notes=row["notes"],
        )
