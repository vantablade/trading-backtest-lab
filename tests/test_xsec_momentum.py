"""Tests for xsec_momentum: ranking behaviour and no use of bar t in the ranking."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import numpy as np

from lab.engine import OHLCVFrame, Panel, align_panel, run_panel_backtest
from lab.strategies import available, get_strategy
from lab.strategies.xsec_momentum import XSectionalMomentum

BASE = datetime(2024, 1, 1, tzinfo=UTC)


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


# --------------------------------------------------------------------------- #
# Ranking behaviour                                                           #
# --------------------------------------------------------------------------- #


def test_holds_the_top_momentum_asset() -> None:
    # UP trends hardest, DOWN falls: with hold_top=1 only UP is ever held.
    n = 200
    panel = _panel(
        {
            "UP": [100.0 * 1.003**k for k in range(n)],
            "MID": [100.0 * 1.001**k for k in range(n)],
            "DOWN": [100.0 * 0.999**k for k in range(n)],
        }
    )
    strat = XSectionalMomentum(lookback=20, hold_top=1)
    result = run_panel_backtest(panel, strat, initial_cash=Decimal("100000"))
    held = {s for s, v in result.final_positions.items() if v != 0}
    assert held == {"UP"}


def test_holds_top_two() -> None:
    n = 200
    panel = _panel(
        {
            "UP": [100.0 * 1.003**k for k in range(n)],
            "MID": [100.0 * 1.001**k for k in range(n)],
            "DOWN": [100.0 * 0.999**k for k in range(n)],
        }
    )
    strat = XSectionalMomentum(lookback=20, hold_top=2)
    result = run_panel_backtest(panel, strat, initial_cash=Decimal("100000"))
    held = {s for s, v in result.final_positions.items() if v != 0}
    assert held == {"UP", "MID"}


def test_registered_and_built_from_params() -> None:
    assert "xsec_momentum" in available()
    assert "equal_weight_buy_hold" in available()
    strat = get_strategy("xsec_momentum", {"lookback": 126, "hold_top": 3, "rebalance": "monthly"})
    assert isinstance(strat, XSectionalMomentum)
    assert (strat.lookback, strat.hold_top) == (126, 3)


# --------------------------------------------------------------------------- #
# The ranking never reads the current bar (recording-view proof)              #
# --------------------------------------------------------------------------- #


class _RecordingSeries:
    """Wraps a BoundedSeries and records every absolute bar index it is asked for."""

    def __init__(self, inner: Any, cursor: int, reads: set[int]) -> None:
        self._inner = inner
        self._cursor = cursor
        self._reads = reads

    def __getitem__(self, key: int | slice) -> Any:
        n = self._cursor + 1
        if isinstance(key, slice):
            self._reads.update(range(*key.indices(n)))
        else:
            j = int(key)
            self._reads.add(j + n if j < 0 else j)
        return self._inner[key]

    def mean(self, *args: Any, **kwargs: Any) -> Any:
        self._reads.update(range(self._cursor + 1))
        return self._inner.mean(*args, **kwargs)


class _RecordingMarketView:
    def __init__(self, inner: Any, reads: set[int]) -> None:
        self._inner = inner
        self._reads = reads

    def _rec(self, series: Any) -> _RecordingSeries:
        return _RecordingSeries(series, self._inner.i, self._reads)

    @property
    def i(self) -> int:
        return self._inner.i

    @property
    def open(self) -> _RecordingSeries:
        return self._rec(self._inner.open)

    @property
    def high(self) -> _RecordingSeries:
        return self._rec(self._inner.high)

    @property
    def low(self) -> _RecordingSeries:
        return self._rec(self._inner.low)

    @property
    def close(self) -> _RecordingSeries:
        return self._rec(self._inner.close)

    @property
    def volume(self) -> _RecordingSeries:
        return self._rec(self._inner.volume)


class _RecordingPanelView:
    """A PanelView whose per-symbol reads are tracked."""

    def __init__(self, panel: Panel, cursor: int, reads: set[int]) -> None:
        from lab.engine import PanelView

        self._inner = PanelView(panel, cursor)
        self._reads = reads

    @property
    def i(self) -> int:
        return self._inner.i

    @property
    def now(self) -> datetime:
        return self._inner.now

    @property
    def symbols(self) -> tuple[str, ...]:
        return self._inner.symbols

    def view(self, symbol: str) -> _RecordingMarketView:
        return _RecordingMarketView(self._inner.view(symbol), self._reads)


def test_ranking_never_reads_the_current_bar() -> None:
    # ~3 months of daily bars so several monthly rebalances actually rank.
    n = 90
    panel = _panel(
        {
            "A": [100.0 + k for k in range(n)],
            "B": [100.0 + 0.5 * k for k in range(n)],
            "C": [100.0 - 0.3 * k for k in range(n)],
        }
    )
    strat = XSectionalMomentum(lookback=5, hold_top=1)
    all_reads: set[int] = set()
    for t in range(len(panel)):
        reads: set[int] = set()
        strat.on_bar(_RecordingPanelView(panel, t, reads))
        assert t not in reads, f"ranking read current bar {t}; reads={sorted(reads)}"
        all_reads |= reads
    assert all_reads, "expected the ranking to read some past bars (test not vacuous)"
