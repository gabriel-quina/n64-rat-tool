from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class RomFingerprint:
    path: Path
    filename: str
    md5: str
    sha1: str
    size_bytes: int
    fmt: str
    byte_order: str


def _detect_n64_format(header4: bytes) -> tuple[str, str]:
    signatures = {
        b"\x80\x37\x12\x40": ("z64", "big"),
        b"\x37\x80\x40\x12": ("v64", "byteswapped"),
        b"\x40\x12\x37\x80": ("n64", "little"),
    }
    return signatures.get(header4, ("unknown", "unknown"))


def calculate_fingerprint(rom_path: Path) -> RomFingerprint:
    if not rom_path.exists() or not rom_path.is_file():
        raise FileNotFoundError(f"ROM não encontrada: {rom_path}")

    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    with rom_path.open("rb") as f:
        while chunk := f.read(65536):
            md5.update(chunk)
            sha1.update(chunk)

    with rom_path.open("rb") as f:
        header4 = f.read(4)

    fmt, byte_order = _detect_n64_format(header4)
    return RomFingerprint(
        path=rom_path,
        filename=rom_path.name,
        md5=md5.hexdigest(),
        sha1=sha1.hexdigest(),
        size_bytes=rom_path.stat().st_size,
        fmt=fmt,
        byte_order=byte_order,
    )


def import_rom(source: Path, workspace: Path, copy: bool = True) -> Path:
    roms_dir = workspace / "work" / "roms"
    roms_dir.mkdir(parents=True, exist_ok=True)
    target = roms_dir / source.name
    if copy:
        shutil.copy2(source, target)
        return target
    return source
