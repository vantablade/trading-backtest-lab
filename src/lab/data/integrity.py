"""Integrity checks and the summary report for loaded bar data.

Fatal violations (raised as :class:`DataIntegrityError`) are the ones that would
make a backtest silently wrong: non-finite values, naive timestamps, out-of-order
or duplicate bars, and OHLC bars that violate ``low <= open, close <= high``.

Gaps in the time grid are *reported*, not raised. Real markets have gaps
(weekends, holidays, halts); silently filling or dropping them would be
dishonest, and blindly rejecting them would make most real data unusable. The
loader surfaces them in the report and lets the caller decide.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]
TimeArray = npt.NDArray[np.object_]


class DataIntegrityError(ValueError):
    """Raised when raw bar data violates an invariant the harness relies on."""


@dataclass(frozen=True)
class IntegrityReport:
    """A summary of what was loaded and what, if anything, looks irregular."""

    source: str
    sha256: str
    n_bars: int
    start: datetime
    end: datetime
    bar_interval: timedelta  # the declared, spacing-checked bar interval
    n_gaps: int  # number of inter-bar spacings larger than bar_interval
    gap_after: tuple[datetime, ...]  # timestamps a gap follows (capped list)

    def summary(self) -> str:
        return (
            f"{self.n_bars} bars {self.start.isoformat()} -> {self.end.isoformat()} "
            f"@ {self.bar_interval}, {self.n_gaps} gap(s), sha256={self.sha256[:12]}..."
        )


def check_ohlc_consistency(
    open_: FloatArray,
    high: FloatArray,
    low: FloatArray,
    close: FloatArray,
    volume: FloatArray,
) -> None:
    """Raise on the first bar whose OHLC/volume relationships are impossible."""
    bad_hl = low > high
    if bad_hl.any():
        i = int(np.argmax(bad_hl))
        raise DataIntegrityError(f"bar {i}: low {low[i]} > high {high[i]}")

    bad_open = (open_ < low) | (open_ > high)
    if bad_open.any():
        i = int(np.argmax(bad_open))
        raise DataIntegrityError(f"bar {i}: open {open_[i]} outside [low {low[i]}, high {high[i]}]")

    bad_close = (close < low) | (close > high)
    if bad_close.any():
        i = int(np.argmax(bad_close))
        raise DataIntegrityError(
            f"bar {i}: close {close[i]} outside [low {low[i]}, high {high[i]}]"
        )

    bad_vol = volume < 0
    if bad_vol.any():
        i = int(np.argmax(bad_vol))
        raise DataIntegrityError(f"bar {i}: negative volume {volume[i]}")


def find_gaps(timestamps: TimeArray, interval: timedelta) -> tuple[datetime, ...]:
    """Timestamps after which the spacing to the next bar exceeds ``interval``.

    The interval is declared and validated elsewhere (see
    :class:`lab.engine.OHLCVFrame`); here it is taken as given and used only to
    locate gaps. Fewer than two bars means there is nothing to check.
    """
    n = len(timestamps)
    if n < 2:
        return ()
    return tuple(
        timestamps[i] for i in range(n - 1) if (timestamps[i + 1] - timestamps[i]) > interval
    )
