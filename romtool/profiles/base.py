from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(slots=True)
class HeuristicConfig:
    min_length_bytes: int = 4
    min_confidence: float = 0.55
    max_control_ratio: float = 0.10
    require_multibyte_ratio: float = 0.10
    min_useful_chars_nul: int = 5
    min_useful_chars_fixed: int = 8
    min_score_nul: float = 0.72
    min_score_fixed: float = 0.82
    anchor_at_scan_start: bool = True
    anchor_after_nul: bool = True
    anchor_after_non_text: bool = True
    anchor_binary_transition: bool = True
    binary_window: int = 8
    binary_textish_ratio_max: float = 0.30
    max_symbol_ratio: float = 0.35
    max_overlap_bytes: int = 0


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
