from __future__ import annotations

from romtool.profiles.base import BaseProfile, HeuristicConfig


def build_profile() -> BaseProfile:
    return BaseProfile(
        name="generic_n64",
        encodings=["cp932"],
        heuristic=HeuristicConfig(
            min_length_bytes=4,
            min_confidence=0.60,
            max_control_ratio=0.05,
            require_multibyte_ratio=0.05,
        ),
        exclude_ranges=[],
    )
