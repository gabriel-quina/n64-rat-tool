from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def synthetic_rom(tmp_path: Path) -> Path:
    text1 = "テストです".encode("cp932") + b"\x00"
    text2 = "HELLO N64".encode("cp932")
    junk = bytes([0xFF, 0x01, 0x02, 0x00, 0xAA, 0xBB, 0xCC])
    blob = b"\x80\x37\x12\x40" + junk + text1 + junk + text2 + junk
    path = tmp_path / "sample.z64"
    path.write_bytes(blob)
    return path
