"""The bar interval is declared, validated against observed spacing, and recorded.

Declared, not inferred: the frame carries ``interval`` explicitly and rejects it
if it disagrees with the modal spacing of its own timestamps. The engine copies
it onto the result so downstream metrics never have to guess it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from lab.engine import IntervalMismatchError, MarketView, OHLCVFrame, Signal, run_backtest


def _frame(interval: timedelta, n: int = 8, step: timedelta = timedelta(hours=1)) -> OHLCVFrame:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    ts = np.array([base + step * k for k in range(n)], dtype=object)
    close = np.linspace(100.0, 100.0 + (n - 1), n)
    return OHLCVFrame(
        timestamps=ts,
        open=close - 0.5,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=np.full(n, 1_000.0),
        interval=interval,
    )


class _Flat:
    def on_bar(self, view: MarketView) -> Signal:
        return Signal(0.0)


def test_matching_interval_is_accepted() -> None:
    frame = _frame(timedelta(hours=1))
    assert frame.interval == timedelta(hours=1)


def test_mismatched_interval_is_rejected() -> None:
    # Hourly timestamps, but 30 minutes is declared.
    with pytest.raises(IntervalMismatchError, match="disagrees"):
        _frame(timedelta(minutes=30))


def test_interval_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        _frame(timedelta(0))


def test_interval_must_be_a_timedelta() -> None:
    with pytest.raises(TypeError, match="interval must be a timedelta"):
        _frame("1h")  # type: ignore[arg-type]


def test_single_bar_skips_the_modal_check() -> None:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    ts = np.array([base], dtype=object)
    z = np.array([100.0])
    frame = OHLCVFrame(
        timestamps=ts,
        open=z,
        high=z + 1,
        low=z - 1,
        close=z,
        volume=z + 10,
        interval=timedelta(days=7),  # nothing to contradict it with one bar
    )
    assert frame.interval == timedelta(days=7)


def test_gaps_do_not_break_the_modal_check() -> None:
    # Modal spacing is still 1h even with a doubled gap, so 1h is accepted.
    base = datetime(2024, 1, 1, tzinfo=UTC)
    hours = [0, 1, 2, 4, 5]  # hour 3 missing
    ts = np.array([base + timedelta(hours=h) for h in hours], dtype=object)
    close = np.linspace(100.0, 104.0, len(hours))
    frame = OHLCVFrame(
        timestamps=ts,
        open=close - 0.5,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=np.full(len(hours), 1_000.0),
        interval=timedelta(hours=1),
    )
    assert frame.interval == timedelta(hours=1)


def test_backtest_result_records_interval() -> None:
    result = run_backtest(_frame(timedelta(hours=1)), _Flat())
    assert result.interval == timedelta(hours=1)
    assert result.interval == result.frame.interval
