from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(slots=True)
class HeuristicConfig:
    min_length_bytes: int = 4
    min_confidence: float = 0.55
    max_control_ratio: float = 0.10
    require_multibyte_ratio: float = 0.10


class Profile(Protocol):
    name: str
    encodings: list[str]
    heuristic: HeuristicConfig
    exclude_ranges: list[tuple[int, int]]

    def is_excluded(self, offset: int) -> bool: ...


@dataclass(slots=True)
class BaseProfile:
    name: str
    encodings: list[str] = field(default_factory=lambda: ["cp932"])
    heuristic: HeuristicConfig = field(default_factory=HeuristicConfig)
    exclude_ranges: list[tuple[int, int]] = field(default_factory=list)

    def is_excluded(self, offset: int) -> bool:
        return any(start <= offset <= end for start, end in self.exclude_ranges)
