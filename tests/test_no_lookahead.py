"""Adversarial no-lookahead tests (CLAUDE.md rule 2).

These are the harness's conscience. The strategy classes below are deliberately
dishonest test doubles — they try to read the future in the ways a real
strategy would accidentally (or a p-hacker deliberately) do it. They live here,
not in ``lab.strategies``, precisely because they cheat. Every one of them must
be caught by the engine, structurally, with a :class:`LookaheadError`.

Any change to ``src/lab/engine/`` must keep every test in this file green.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest

from lab.engine import (
    LookaheadError,
    MarketView,
    OHLCVFrame,
    Signal,
    run_backtest,
)

# --------------------------------------------------------------------------- #
# The view exposes the present and the past honestly.                         #
# --------------------------------------------------------------------------- #


def test_current_and_past_access_is_allowed(frame: OHLCVFrame) -> None:
    k = 10
    view = MarketView(frame, k)
    assert view.i == k
    assert len(view.close) == k + 1
    assert view.close[-1] == frame.close[k]  # the current bar
    assert view.close[0] == frame.close[0]  # the first bar
    assert view.close[-2] == frame.close[k - 1]  # the previous bar
    assert view.now == frame.timestamps[k]


def test_bounded_window_slice_is_allowed(frame: OHLCVFrame) -> None:
    k = 10
    view = MarketView(frame, k)
    window = view.close[-3:]  # last three visible bars
    assert list(window) == list(frame.close[k - 2 : k + 1])
    assert list(view.close[:]) == list(frame.close[: k + 1])


# --------------------------------------------------------------------------- #
# Statistics and materialisation cannot see the future.                       #
# --------------------------------------------------------------------------- #


def test_visible_mean_is_not_full_frame_mean(frame: OHLCVFrame) -> None:
    k = 10
    view = MarketView(frame, k)
    assert view.close.mean() == pytest.approx(frame.close[: k + 1].mean())
    # Strictly increasing series => the visible mean is below the full mean.
    # A `df.mean()` over the whole frame is simply unreachable from the view.
    assert view.close.mean() < frame.close.mean()


def test_to_numpy_cannot_materialise_the_future(frame: OHLCVFrame) -> None:
    k = 10
    view = MarketView(frame, k)
    arr = view.close.to_numpy()
    assert len(arr) == k + 1
    assert arr.max() == frame.close[: k + 1].max()
    assert arr.max() < frame.close.max()  # the global max lives ahead
    # No escape via np.asarray / __array__ either.
    assert len(np.asarray(view.close)) == k + 1
    assert float(np.max(view.close)) < frame.close.max()


def test_index_before_history_raises_indexerror(frame: OHLCVFrame) -> None:
    view = MarketView(frame, 3)
    with pytest.raises(IndexError):
        _ = view.close[-99]


# --------------------------------------------------------------------------- #
# Adversarial strategies — each MUST fail with LookaheadError.                 #
# --------------------------------------------------------------------------- #


class PeekNextClose:
    """Reads tomorrow's close to decide today's trade — the classic cheat."""

    def on_bar(self, view: MarketView) -> Signal:
        tomorrow = view.close[view.i + 1]
        return Signal(1.0 if tomorrow > view.close[-1] else -1.0)


class PeekFutureSlice:
    """Grabs a window of bars that starts in the future."""

    def on_bar(self, view: MarketView) -> Signal:
        window = view.close[view.i + 1 : view.i + 6]
        return Signal(1.0 if float(np.mean(window)) > view.close[-1] else 0.0)


class PeekFutureHigh:
    """Peeks at tomorrow's high to set a 'perfect' exit."""

    def on_bar(self, view: MarketView) -> Signal:
        return Signal(1.0 if view.high[view.i + 1] > view.close[-1] else 0.0)


class PeekViaSliceStop:
    """Sneaks one future bar in through a slice stop just past the present."""

    def on_bar(self, view: MarketView) -> Signal:
        window = view.close[: view.i + 2]  # includes bar i+1
        return Signal(1.0 if window[-1] > window[-2] else 0.0)


@pytest.mark.parametrize(
    "strategy",
    [PeekNextClose(), PeekFutureSlice(), PeekFutureHigh(), PeekViaSliceStop()],
    ids=["next_close", "future_slice", "future_high", "slice_stop"],
)
def test_future_reads_raise_lookahead(frame: OHLCVFrame, strategy: object) -> None:
    with pytest.raises(LookaheadError):
        run_backtest(frame, strategy)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Engine-level no-lookahead: execution is deferred one bar.                    #
# --------------------------------------------------------------------------- #


class AlwaysLong:
    def on_bar(self, view: MarketView) -> Signal:
        return Signal(1.0)


def test_execution_is_delayed_one_bar(frame: OHLCVFrame) -> None:
    result = run_backtest(frame, AlwaysLong())
    assert result.fills, "expected at least one fill"
    # The decision made on bar 0 must fill at bar 1's open, never bar 0's.
    assert result.fills[0].timestamp == frame.timestamps[1]
    assert result.fills[0].price == Decimal(str(frame.open[1]))
    assert all(f.timestamp != frame.timestamps[0] for f in result.fills)


class LongOnlyOnBar:
    """Goes long on exactly one bar (which the test double is told the index of)."""

    def __init__(self, target_i: int) -> None:
        self.target_i = target_i

    def on_bar(self, view: MarketView) -> Signal:
        return Signal(1.0 if view.i == self.target_i else 0.0)


def test_signal_on_final_bar_never_fills(frame: OHLCVFrame) -> None:
    last = len(frame) - 1
    result = run_backtest(frame, LongOnlyOnBar(last))
    # The only non-flat decision is on the last bar; there is no next bar to
    # execute it at, so nothing ever fills.
    assert result.fills == []


# --------------------------------------------------------------------------- #
# The enforcement does not break an honest strategy.                          #
# --------------------------------------------------------------------------- #


class HonestMomentum:
    """Uses only the current bar and a trailing mean — all bounded, all legal."""

    def on_bar(self, view: MarketView) -> Signal:
        if len(view.close) < 3:
            return Signal(0.0)
        return Signal(1.0 if view.close[-1] > view.close.mean() else -1.0)


def test_honest_strategy_runs_to_completion(frame: OHLCVFrame) -> None:
    result = run_backtest(frame, HonestMomentum())
    assert isinstance(result.final_cash, Decimal)
    assert len(result.fills) >= 1


# --------------------------------------------------------------------------- #
# Frame construction rejects the ingredients of subtle lookahead.             #
# --------------------------------------------------------------------------- #


def test_frame_rejects_naive_timestamps() -> None:
    base = datetime(2024, 1, 1)  # tz-naive
    ts = np.array([base + timedelta(hours=k) for k in range(4)], dtype=object)
    z = np.arange(4, dtype=float)
    with pytest.raises(ValueError, match="timezone-aware"):
        OHLCVFrame(
            timestamps=ts,
            open=z,
            high=z + 1,
            low=z - 1,
            close=z,
            volume=z + 10,
            interval=timedelta(hours=1),
        )


def test_frame_rejects_non_monotonic_timestamps() -> None:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    ts = np.array(
        [base + timedelta(days=d) for d in (1, 0, 2, 3)],
        dtype=object,  # out of order
    )
    z = np.arange(4, dtype=float)
    with pytest.raises(ValueError, match="monotonic"):
        OHLCVFrame(
            timestamps=ts,
            open=z,
            high=z + 1,
            low=z - 1,
            close=z,
            volume=z + 10,
            interval=timedelta(days=1),
        )
