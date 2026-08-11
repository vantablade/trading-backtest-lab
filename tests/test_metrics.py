"""Tests for the summary metrics (Sharpe, CAGR, max drawdown)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np

from lab.engine import MarketView, OHLCVFrame, Signal, run_backtest
from lab.metrics import compute_metrics


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


class _Flat:
    def on_bar(self, view: MarketView) -> Signal:
        return Signal(0.0)


class _AlwaysLong:
    def on_bar(self, view: MarketView) -> Signal:
        return Signal(1.0)


def test_flat_has_zero_risk_metrics() -> None:
    # Never invested => constant equity => no return, no volatility, no drawdown.
    m = compute_metrics(run_backtest(_frame([100.0 + k for k in range(30)]), _Flat()))
    assert m["n_trades"] == 0
    assert m["total_return"] == 0.0
    assert m["cagr"] == 0.0
    assert m["sharpe"] == 0.0
    assert m["max_drawdown"] == 0.0


def test_monotonic_gains_have_positive_cagr_and_sharpe() -> None:
    # Buy and hold a steadily rising asset: up-only equity.
    m = compute_metrics(run_backtest(_frame([100.0 + k for k in range(200)]), _AlwaysLong()))
    assert m["cagr"] > 0.0
    assert m["sharpe"] > 0.0


def test_a_dip_produces_a_negative_drawdown() -> None:
    # Rise, fall, recover: the fall must show up as a peak-to-trough drawdown.
    closes = (
        [100.0 + i for i in range(20)]
        + [120.0 - 2.0 * i for i in range(20)]
        + [82.0 + i for i in range(20)]
    )
    m = compute_metrics(run_backtest(_frame(closes), _AlwaysLong()))
    assert m["max_drawdown"] < 0.0
