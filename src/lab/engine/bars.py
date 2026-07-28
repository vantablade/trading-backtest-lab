"""The immutable in-memory bar series the engine iterates over.

This is the engine's runtime representation of price data. The data layer
(``lab.data``) will produce these from ``data/raw/``; the engine only ever
consumes them. Construction validates the invariants the rest of the harness
relies on — timezone-aware UTC timestamps, strictly increasing, finite values —
so that a bad frame fails loudly at the edge rather than silently mid-backtest.

Timestamps are stored as an object array of timezone-aware :class:`datetime`
objects. "Naive datetimes are a bug" (CLAUDE.md) is checked literally here: each
timestamp must carry a UTC ``tzinfo``. The engine core deliberately depends only
on numpy; pandas/pyarrow belong to the data-loading and results-IO layers.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]
TimeArray = npt.NDArray[np.object_]  # of timezone-aware datetime

_ZERO = timedelta(0)


class BarLabel(Enum):
    """Which edge of its interval a bar's timestamp names.

    ``OPEN`` — the timestamp is the bar's open; bar ``t`` covers
    ``[t, t+interval)``, so its high/low/close are only known at ``t+interval``.
    At wall-clock time ``t`` the last *fully-formed* bar is ``t-1``. **This is
    the harness convention** (see ``engine/loop.py``): a trade executed at bar
    ``t``'s open uses only information from bars ``0..t-1``.

    ``CLOSE`` — the timestamp is the bar's close; bar ``t`` covers
    ``(t-interval, t]``. The engine does not support this: under it, a bar's
    timestamp already implies the interval's full OHLC is known *at* ``t``, which
    breaks the open-execution causality above. Relabel/resample before running.
    """

    OPEN = "open"
    CLOSE = "close"


class BarConventionError(ValueError):
    """Raised when a frame's bar-labeling convention is not the one assumed."""


class IntervalMismatchError(ValueError):
    """Raised when a frame's declared interval disagrees with observed spacing."""


@dataclass(frozen=True)
class OHLCVFrame:
    """Open/high/low/close/volume bars on a shared timezone-aware UTC index.

    Bars are labeled by ``label`` (default :class:`BarLabel.OPEN`): the timestamp
    names the bar's open and bar ``t`` covers ``[t, t+interval)``. The convention
    is carried explicitly, not assumed, so the engine can reject data that does
    not match what it relies on.

    ``interval`` is the bar spacing, *declared* rather than inferred. It is
    validated against the modal observed spacing: if they disagree the frame is
    rejected (:class:`IntervalMismatchError`). Carrying it means downstream code
    (metrics, annualisation) never has to guess it from the timestamps.
    """

    timestamps: TimeArray
    open: FloatArray
    high: FloatArray
    low: FloatArray
    close: FloatArray
    volume: FloatArray
    interval: timedelta
    label: BarLabel = BarLabel.OPEN

    def __post_init__(self) -> None:
        if not isinstance(self.timestamps, np.ndarray):
            raise TypeError("timestamps must be a numpy array of datetime objects")
        if not isinstance(self.label, BarLabel):
            raise TypeError(f"label must be a BarLabel, got {type(self.label)!r}")
        if not isinstance(self.interval, timedelta):
            raise TypeError(f"interval must be a timedelta, got {type(self.interval)!r}")
        if self.interval <= _ZERO:
            raise ValueError(f"interval must be positive, got {self.interval}")
        n = len(self.timestamps)
        if n == 0:
            raise ValueError("OHLCVFrame must contain at least one bar")

        for name, arr in self._channels():
            if not isinstance(arr, np.ndarray):
                raise TypeError(f"channel {name!r} must be a numpy array, got {type(arr)!r}")
            if arr.shape != (n,):
                raise ValueError(f"channel {name!r} has shape {arr.shape}, expected {(n,)}")
            if not np.all(np.isfinite(arr)):
                raise ValueError(f"channel {name!r} contains non-finite values")

        self._validate_timestamps()
        self._validate_interval(n)

    def _validate_interval(self, n: int) -> None:
        if n < 2:
            return  # a single bar has no observable spacing to check against
        modal = _modal_spacing(self.timestamps)
        if modal != self.interval:
            raise IntervalMismatchError(
                f"declared interval {self.interval} disagrees with the modal observed "
                f"spacing {modal} across {n} bars"
            )

    def _validate_timestamps(self) -> None:
        prev: datetime | None = None
        for k, ts in enumerate(self.timestamps):
            if not isinstance(ts, datetime):
                raise ValueError(
                    f"timestamps[{k}] must be a timezone-aware datetime, got {type(ts)!r}"
                )
            if ts.tzinfo is None or ts.utcoffset() is None:
                raise ValueError(
                    f"timestamps[{k}] is naive; timestamps must be timezone-aware UTC "
                    f"(naive datetimes are a bug)"
                )
            if ts.utcoffset() != _ZERO:
                raise ValueError(f"timestamps[{k}] must be UTC, got offset {ts.utcoffset()}")
            if prev is not None and ts <= prev:
                raise ValueError(
                    "timestamps must be strictly monotonically increasing "
                    f"(bar {k} at {ts.isoformat()} is not after {prev.isoformat()})"
                )
            prev = ts

    def _channels(self) -> tuple[tuple[str, Any], ...]:
        return (
            ("open", self.open),
            ("high", self.high),
            ("low", self.low),
            ("close", self.close),
            ("volume", self.volume),
        )

    def between(self, start: datetime, end: datetime) -> OHLCVFrame:
        """A new frame with only the bars whose timestamp is in ``[start, end]``.

        Used to enforce split boundaries: a run on one split literally cannot see
        another split's bars. Interval and label are preserved. Raises if the
        range contains no bars.
        """
        keep = [i for i, ts in enumerate(self.timestamps) if start <= ts <= end]
        if not keep:
            raise ValueError(f"no bars in [{start.isoformat()}, {end.isoformat()}]")
        idx = np.array(keep, dtype=np.intp)
        return OHLCVFrame(
            timestamps=self.timestamps[idx],
            open=self.open[idx],
            high=self.high[idx],
            low=self.low[idx],
            close=self.close[idx],
            volume=self.volume[idx],
            interval=self.interval,
            label=self.label,
        )

    def __len__(self) -> int:
        return len(self.timestamps)


def _modal_spacing(timestamps: TimeArray) -> timedelta:
    """The most common spacing between consecutive timestamps."""
    deltas = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
    modal: timedelta = Counter(deltas).most_common(1)[0][0]
    return modal
