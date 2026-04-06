from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from romtool.db import RomToolDB
from romtool.dumpview import annotate_blocks, blocks_to_json, chunk_bytes, decode_chunks, lines_to_json
from romtool.exporter import export_jsonl
from romtool.profiles.generic_n64 import build_profile
from romtool.rom import calculate_fingerprint, import_rom
from romtool.scanner import scan_rom_file

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("romtool")


def workspace_root() -> Path:
    return Path.cwd()


def db_path() -> Path:
    return workspace_root() / "work" / "romtool.sqlite3"


def cmd_init(_: argparse.Namespace) -> int:
    root = workspace_root()
    for rel in ["work", "work/roms", "docs", "tests"]:
        (root / rel).mkdir(parents=True, exist_ok=True)
    db = RomToolDB(db_path())
    db.init_schema()
    db.close()
    logger.info("Workspace inicializado em %s", root)
    return 0


def cmd_import_rom(args: argparse.Namespace) -> int:
    src = Path(args.rom)
    target = import_rom(src, workspace_root(), copy=not args.no_copy)
    fp = calculate_fingerprint(target)

    db = RomToolDB(db_path())
    db.init_schema()
    row = db.upsert_rom(fp)
    db.close()

    logger.info("ROM importada: %s", row.filename)
    logger.info("SHA1=%s MD5=%s", row.sha1, row.md5)
    logger.info("Formato=%s ByteOrder=%s Size=%d", row.fmt, row.byte_order, row.size_bytes)
    return 0


def cmd_scan_text(args: argparse.Namespace) -> int:
    db = RomToolDB(db_path())
    db.init_schema()
    rom = db.get_latest_rom()
    if not rom:
        logger.error("Nenhuma ROM importada. Rode import-rom primeiro.")
        db.close()
        return 1

    profile = build_profile()
    if not args.force:
        cache_hit = db.last_successful_run(rom.id, profile.name)
        if cache_hit:
            logger.info("Cache hit: scan já existe (run_id=%s). Use --force para reescanear.", cache_hit.id)
            db.close()
            return 0

    run_id = db.create_analysis_run(rom.id, profile.name)
    rom_path = Path(rom.path)
    try:
        result = scan_rom_file(rom_path, rom.id, run_id, profile)
        inserted = db.insert_string_candidates(result.candidates)
        db.finish_analysis_run(run_id, "success", f"inserted={inserted}; scanned_bytes={result.scanned_bytes}")
        logger.info("Scan concluído. Candidatas encontradas=%d inseridas=%d", len(result.candidates), inserted)
    except Exception as exc:  # noqa: BLE001
        db.finish_analysis_run(run_id, "failed", str(exc))
        logger.exception("Falha no scan: %s", exc)
        db.close()
        return 2

    db.close()
    return 0


def cmd_export_strings(args: argparse.Namespace) -> int:
    out = Path(args.out)
    db = RomToolDB(db_path())
    db.init_schema()
    count = export_jsonl(db, out)
    db.close()
    logger.info("Exportadas %d strings em %s", count, out)
    return 0


def cmd_show_string(args: argparse.Namespace) -> int:
    db = RomToolDB(db_path())
    db.init_schema()
    row = db.fetch_string_by_uid(args.id)
    db.close()
    if not row:
        logger.error("String não encontrada: %s", args.id)
        return 1
    print(json.dumps(dict(row), indent=2, ensure_ascii=False))
    return 0


def cmd_stats(_: argparse.Namespace) -> int:
    db = RomToolDB(db_path())
    db.init_schema()
    rom = db.get_latest_rom()
    if not rom:
        logger.error("Nenhuma ROM importada.")
        db.close()
        return 1

    total = db.count_strings(rom.id)
    by_kind = db.count_by_kind(rom.id)
    by_band = db.count_by_offset_band(rom.id)
    last_run = db.last_successful_run(rom.id, build_profile().name)

    print(f"ROM: {rom.filename}")
    print(f"Fingerprint: sha1={rom.sha1} md5={rom.md5}")
    print(f"Total strings: {total}")
    print("Por tipo:")
    for k, v in by_kind.items():
        print(f"  - {k}: {v}")
    print("Por faixa de offset:")
    for k, v in by_band.items():
        print(f"  - {k}: {v}")
    if last_run:
        print(f"Último scan: run_id={last_run.id} started_at={last_run.started_at} status={last_run.status}")
    db.close()
    return 0


def cmd_list_strings(args: argparse.Namespace) -> int:
    db = RomToolDB(db_path())
    db.init_schema()
    rows = db.fetch_strings(limit=args.limit)
    db.close()
    for row in rows:
        print(
            f"{row['string_uid']} off=0x{row['start_off']:08X} kind={row['kind']} "
            f"conf={row['confidence']:.2f} text={row['normalized_text']}"
        )
    return 0


def _parse_hex(text: str) -> int:
    return int(text, 16) if text.lower().startswith("0x") else int(text)


def _read_dump_data() -> tuple[bytes, int]:
    db = RomToolDB(db_path())
    db.init_schema()
    rom = db.get_latest_rom()
    db.close()
    if not rom:
        raise RuntimeError("Nenhuma ROM importada.")
    return Path(rom.path).read_bytes(), rom.id


def cmd_dump_range(args: argparse.Namespace) -> int:
    try:
        rom_data, _ = _read_dump_data()
    except RuntimeError as exc:
        logger.error(str(exc))
        return 1

    start = _parse_hex(args.start)
    end = _parse_hex(args.end)
    if end <= start:
        logger.error("Faixa inválida: --end deve ser maior que --start")
        return 2

    data = rom_data[start:end]
    if args.mode == "raw":
        lines = chunk_bytes(data, start=start, chunk_size=args.chunk_size)
        if args.json:
            print(lines_to_json(lines))
            return 0
        for line in lines:
            print(f"0x{line.offset:08X}  raw={line.raw_hex}")
        return 0

    if args.mode == "decode":
        lines = decode_chunks(data, start=start, chunk_size=args.chunk_size, encoding=args.encoding, only_text=args.only_text)
        if args.json:
            print(lines_to_json(lines))
            return 0
        for line in lines:
            print(f"0x{line.offset:08X}  raw={line.raw_hex}")
            print(f"decoded={line.decoded}")
        return 0

    blocks = annotate_blocks(data, start=start, encoding=args.encoding, only_text=args.only_text)
    if args.json:
        print(blocks_to_json(blocks))
        return 0

    for block in blocks:
        print(f"0x{block.offset:08X}")
        print(f"raw: {block.raw_hex}")
        print(f"decoded: {block.decoded}")
        print(f"prefix: {''.join(block.prefix_tokens) if block.prefix_tokens else '-'}")
        print(f"text_guess: {block.text_guess if block.text_guess else '-'}")
        print(f"suffix: {''.join(block.suffix_tokens) if block.suffix_tokens else '-'}")
    return 0


def cmd_find_offset(args: argparse.Namespace) -> int:
    offset = _parse_hex(args.offset)
    db = RomToolDB(db_path())
    db.init_schema()
    rom = db.get_latest_rom()
    if not rom:
        logger.error("Nenhuma ROM importada.")
        db.close()
        return 1

    rows = db.fetch_candidates_covering_offset(rom.id, offset, limit=args.limit)
    db.close()
    if not rows:
        print(f"Nenhum candidato cobre 0x{offset:08X}")
        return 0

    for row in rows:
        print(
            f"{row['string_uid']} start=0x{row['start_off']:08X} end=0x{row['end_off']:08X} "
            f"kind={row['kind']} conf={row['confidence']:.2f} text={row['normalized_text']}"
        )
    return 0


def cmd_list_range_candidates(args: argparse.Namespace) -> int:
    start = _parse_hex(args.start)
    end = _parse_hex(args.end)
    db = RomToolDB(db_path())
    db.init_schema()
    rom = db.get_latest_rom()
    if not rom:
        logger.error("Nenhuma ROM importada.")
        db.close()
        return 1

    rows = db.fetch_candidates_in_range(rom.id, start, end, limit=args.limit)
    db.close()
    for row in rows:
        print(
            f"{row['string_uid']} start=0x{row['start_off']:08X} end=0x{row['end_off']:08X} "
            f"kind={row['kind']} conf={row['confidence']:.2f}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="romtool", description="MVP scanner de texto para ROM N64")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Inicializa workspace")
    p_init.set_defaults(func=cmd_init)

    p_import = sub.add_parser("import-rom", help="Importa ROM .z64")
    p_import.add_argument("--rom", required=True)
    p_import.add_argument("--no-copy", action="store_true", help="Apenas registra caminho")
    p_import.set_defaults(func=cmd_import_rom)

    p_scan = sub.add_parser("scan-text", help="Escaneia candidatos de texto")
    p_scan.add_argument("--force", action="store_true", help="Ignora cache e reexecuta")
    p_scan.set_defaults(func=cmd_scan_text)

    p_export = sub.add_parser("export-strings", help="Exporta JSONL")
    p_export.add_argument("--out", required=True)
    p_export.set_defaults(func=cmd_export_strings)

    p_show = sub.add_parser("show-string", help="Exibe string por uid")
    p_show.add_argument("--id", required=True)
    p_show.set_defaults(func=cmd_show_string)

    p_stats = sub.add_parser("stats", help="Resumo")
    p_stats.set_defaults(func=cmd_stats)

    p_list = sub.add_parser("list-strings", help="Lista strings")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.set_defaults(func=cmd_list_strings)

    p_dump = sub.add_parser("dump-range", help="Visualiza faixa de ROM em raw/decode/annotate")
    p_dump.add_argument("--start", required=True)
    p_dump.add_argument("--end", required=True)
    p_dump.add_argument("--mode", choices=["raw", "decode", "annotate"], default="raw")
    p_dump.add_argument("--encoding", default="cp932")
    p_dump.add_argument("--chunk-size", type=int, default=16)
    p_dump.add_argument("--only-text", action="store_true")
    p_dump.add_argument("--json", action="store_true", dest="json")
    p_dump.set_defaults(func=cmd_dump_range)

    p_find_off = sub.add_parser("find-offset", help="Busca candidatos cobrindo um offset")
    p_find_off.add_argument("--offset", required=True)
    p_find_off.add_argument("--limit", type=int, default=20)
    p_find_off.set_defaults(func=cmd_find_offset)

    p_range = sub.add_parser("list-range-candidates", help="Lista candidatos que intersectam um range")
    p_range.add_argument("--start", required=True)
    p_range.add_argument("--end", required=True)
    p_range.add_argument("--limit", type=int, default=200)
    p_range.set_defaults(func=cmd_list_range_candidates)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
