"""Execution-layer tests: trades fire on signal transitions, not every bar."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np

from lab.engine import MarketView, OHLCVFrame, Signal, run_backtest


def _frame(closes: list[float]) -> OHLCVFrame:
    n = len(closes)
    base = datetime(2024, 1, 1, tzinfo=UTC)
    ts = np.array([base + timedelta(days=k) for k in range(n)], dtype=object)
    c = np.array(closes, dtype=float)
    return OHLCVFrame(
        timestamps=ts,
        open=c,
        high=c + 1.0,
        low=c - 1.0,
        close=c,
        volume=np.full(n, 1_000.0),
        interval=timedelta(days=1),
    )


class _AlwaysLong:
    def on_bar(self, view: MarketView) -> Signal:
        return Signal(1.0)


class _LongThenFlat:
    """Long while ``view.i < flip``, flat afterwards."""

    def __init__(self, flip: int) -> None:
        self.flip = flip

    def on_bar(self, view: MarketView) -> Signal:
        return Signal(1.0 if view.i < self.flip else 0.0)


def test_constant_signal_produces_a_single_entry() -> None:
    # Signal held at 1.0 for all 30 bars => one entry, not 30 rebalancing trades.
    result = run_backtest(_frame([100.0 + k for k in range(30)]), _AlwaysLong())
    assert len(result.fills) == 1
    assert result.fills[0].units > 0  # the entry is a buy


def test_trades_only_on_transitions() -> None:
    # Long then flat => exactly one entry and one exit.
    result = run_backtest(_frame([100.0 + k for k in range(30)]), _LongThenFlat(flip=15))
    assert len(result.fills) == 2
    assert result.fills[0].units > 0  # entry (buy)
    assert result.fills[1].units < 0  # exit (sell)
    assert result.final_position == 0  # ended flat
