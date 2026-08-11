"""Load several CSVs into one aligned multi-asset :class:`Panel`.

Each file is loaded and validated exactly like a single-asset frame (via
:func:`load_csv_bars`), then the frames are aligned on the intersection of their
timestamps. Per-symbol :class:`IntegrityReport`s are kept so a run's manifest can
pin every source by checksum.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from ..engine import BarLabel, Panel, align_panel
from .integrity import IntegrityReport
from .loader import load_csv_bars


@dataclass(frozen=True)
class PanelLoadResult:
    """An aligned panel plus the per-symbol integrity reports."""

    panel: Panel
    reports: dict[str, IntegrityReport]


def load_panel(
    sources: Mapping[str, str | Path],
    *,
    interval: timedelta,
    label: BarLabel = BarLabel.OPEN,
) -> PanelLoadResult:
    """Load ``{symbol: path}`` into an aligned panel."""
    frames = {}
    reports = {}
    for symbol, path in sources.items():
        result = load_csv_bars(path, interval=interval, label=label)
        frames[symbol] = result.frame
        reports[symbol] = result.report
    return PanelLoadResult(panel=align_panel(frames), reports=reports)
