from __future__ import annotations

from romtool.profiles.base import BaseProfile, HeuristicConfig


def build_profile() -> BaseProfile:
    return BaseProfile(
        name="generic_n64",
        encodings=["cp932"],
        heuristic=HeuristicConfig(
            min_length_bytes=6,
            min_confidence=0.60,
            max_control_ratio=0.05,
            require_multibyte_ratio=0.05,
            min_useful_chars_nul=5,
            min_useful_chars_fixed=8,
            min_score_nul=0.74,
            min_score_fixed=0.86,
            anchor_at_scan_start=True,
            anchor_after_nul=True,
            anchor_after_non_text=True,
            anchor_binary_transition=True,
            binary_window=8,
            binary_textish_ratio_max=0.30,
            max_symbol_ratio=0.30,
            max_overlap_bytes=0,
        ),
        exclude_ranges=[],
    )
