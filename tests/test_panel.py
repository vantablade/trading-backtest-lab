"""Tests for the multi-asset Panel: alignment, slicing, and the benchmark run."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest

from lab.engine import OHLCVFrame, Panel, align_panel, run_panel_backtest
from lab.strategies.equal_weight_buy_hold import EqualWeightBuyHold

BASE = datetime(2024, 1, 1, tzinfo=UTC)


def _frame_on_days(days: list[int], first_close: float = 100.0) -> OHLCVFrame:
    ts = np.array([BASE + timedelta(days=d) for d in days], dtype=object)
    close = np.array([first_close + d for d in days], dtype=float)
    return OHLCVFrame(
        timestamps=ts,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=np.full(len(days), 1_000_000.0),
        interval=timedelta(days=1),
    )


def _panel(series: dict[str, list[float]]) -> Panel:
    frames = {}
    for symbol, closes in series.items():
        n = len(closes)
        ts = np.array([BASE + timedelta(days=d) for d in range(n)], dtype=object)
        c = np.array(closes, dtype=float)
        frames[symbol] = OHLCVFrame(
            timestamps=ts,
            open=c,
            high=c + 1.0,
            low=c - 1.0,
            close=c,
            volume=np.full(n, 1_000_000.0),
            interval=timedelta(days=1),
        )
    return align_panel(frames)


def test_align_intersects_timestamps() -> None:
    a = _frame_on_days(list(range(10)))  # days 0..9
    b = _frame_on_days([d for d in range(10) if d != 5], 200.0)  # day 5 missing
    panel = align_panel({"A": a, "B": b})

    assert len(panel) == 9  # day 5 dropped from both (honest inner join)
    assert panel.symbols == ("A", "B")
    assert list(panel.frames["A"].timestamps) == list(panel.frames["B"].timestamps)
    assert (BASE + timedelta(days=5)) not in set(panel.frames["A"].timestamps)


def test_panel_between_slices_all_frames() -> None:
    panel = _panel({"A": [100.0 + k for k in range(20)], "B": [200.0 + k for k in range(20)]})
    sub = panel.between(BASE + timedelta(days=5), BASE + timedelta(days=9))
    assert len(sub) == 5  # days 5..9 inclusive
    assert sub.symbols == ("A", "B")
    assert sub.frames["A"].timestamps[0] == BASE + timedelta(days=5)


def test_panel_rejects_misaligned_frames() -> None:
    a = _frame_on_days([0, 1, 2])
    b = _frame_on_days([0, 1, 3])  # same length, different timestamps
    with pytest.raises(ValueError, match="aligned"):
        Panel({"A": a, "B": b})


def test_equal_weight_enters_each_asset_once() -> None:
    panel = _panel(
        {
            "A": [100.0 + k for k in range(30)],
            "B": [50.0 + 0.5 * k for k in range(30)],
            "C": [200.0 - k for k in range(30)],
        }
    )
    result = run_panel_backtest(panel, EqualWeightBuyHold(), initial_cash=Decimal("100000"))
    assert len(result.fills) == 3  # one entry per asset, then held
    assert all(f.units > 0 for f in result.fills)  # all buys
    assert {f.symbol for f in result.fills} == {"A", "B", "C"}
