"""Multi-asset panel: N OHLCVFrames aligned on one shared timeline.

Cross-sectional strategies need several assets at the same bar. A :class:`Panel`
holds one :class:`OHLCVFrame` per symbol, all aligned to a common set of
timestamps — the *intersection* of their calendars, with no forward-filling of
missing bars. A :class:`PanelView` hands a strategy a bounded
:class:`MarketView` per symbol, reusing the single-asset no-lookahead machinery
verbatim, so a cross-sectional ranking still cannot read bar ``t``.

This is a parallel track: the single-asset engine is untouched.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from .bars import BarLabel, OHLCVFrame
from .market_view import MarketView


@dataclass(frozen=True)
class Panel:
    """Aligned OHLCV frames keyed by symbol. All frames share timestamps."""

    frames: dict[str, OHLCVFrame]

    def __post_init__(self) -> None:
        if not self.frames:
            raise ValueError("Panel needs at least one asset")
        ref = next(iter(self.frames.values()))
        for symbol, frame in self.frames.items():
            if frame.interval != ref.interval:
                raise ValueError(f"{symbol}: interval {frame.interval} != {ref.interval}")
            if frame.label != ref.label:
                raise ValueError(f"{symbol}: bar label {frame.label} != {ref.label}")
            if len(frame.timestamps) != len(ref.timestamps) or not all(
                a == b for a, b in zip(frame.timestamps, ref.timestamps, strict=True)
            ):
                raise ValueError(f"{symbol}: timestamps are not aligned with the panel")

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(self.frames)

    @property
    def timestamps(self) -> np.ndarray:
        return next(iter(self.frames.values())).timestamps

    @property
    def interval(self) -> timedelta:
        return next(iter(self.frames.values())).interval

    @property
    def label(self) -> BarLabel:
        return next(iter(self.frames.values())).label

    def __len__(self) -> int:
        return len(self.timestamps)

    def between(self, start: datetime, end: datetime) -> Panel:
        """A new panel with only the bars whose timestamp is in ``[start, end]``."""
        return Panel({symbol: frame.between(start, end) for symbol, frame in self.frames.items()})


def align_panel(frames_by_symbol: Mapping[str, OHLCVFrame]) -> Panel:
    """Align frames to the intersection of their timestamps (no fill).

    All frames must share the same interval and bar label. Bars present in every
    frame survive; bars missing from any frame are dropped from all (an honest
    inner join rather than forward-filling a price nobody observed).
    """
    if not frames_by_symbol:
        raise ValueError("need at least one frame")
    intervals = {f.interval for f in frames_by_symbol.values()}
    labels = {f.label for f in frames_by_symbol.values()}
    if len(intervals) != 1:
        raise ValueError(f"frames have differing intervals: {intervals}")
    if len(labels) != 1:
        raise ValueError(f"frames have differing bar labels: {labels}")
    interval = intervals.pop()
    label = labels.pop()

    common = set.intersection(*(set(f.timestamps) for f in frames_by_symbol.values()))
    if len(common) < 2:
        raise ValueError("frames share fewer than two common timestamps")

    aligned: dict[str, OHLCVFrame] = {}
    for symbol, frame in frames_by_symbol.items():
        mask = np.array([ts in common for ts in frame.timestamps], dtype=bool)
        aligned[symbol] = OHLCVFrame(
            timestamps=frame.timestamps[mask],
            open=frame.open[mask],
            high=frame.high[mask],
            low=frame.low[mask],
            close=frame.close[mask],
            volume=frame.volume[mask],
            interval=interval,
            label=label,
        )
    return Panel(frames=aligned)


class PanelView:
    """Everything a cross-sectional strategy may see at one bar.

    ``view(symbol)`` returns a bounded :class:`MarketView` for that asset at the
    current cursor, so per-asset reads are subject to the same no-lookahead
    guard as single-asset strategies.
    """

    __slots__ = ("_cursor", "_panel")

    def __init__(self, panel: Panel, cursor: int) -> None:
        if not 0 <= cursor < len(panel):
            raise IndexError(f"cursor {cursor} out of range for {len(panel)} bars")
        self._panel = panel
        self._cursor = cursor

    @property
    def i(self) -> int:
        return self._cursor

    @property
    def now(self) -> datetime:
        return self._panel.timestamps[self._cursor]

    @property
    def symbols(self) -> tuple[str, ...]:
        return self._panel.symbols

    def view(self, symbol: str) -> MarketView:
        return MarketView(self._panel.frames[symbol], self._cursor)

    def __len__(self) -> int:
        return self._cursor + 1
