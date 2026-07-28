"""Tests for the sma_cross strategy: crossover behaviour and no use of bar t."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from lab.engine import MarketView, OHLCVFrame
from lab.pipeline import run_backtest_from_config
from lab.results import read_run
from lab.strategies import available, get_strategy
from lab.strategies.sma_cross import SmaCross


def _frame(closes: list[float]) -> OHLCVFrame:
    n = len(closes)
    base = datetime(2024, 1, 1, tzinfo=UTC)
    ts = np.array([base + timedelta(hours=k) for k in range(n)], dtype=object)
    c = np.array(closes, dtype=float)
    return OHLCVFrame(
        timestamps=ts,
        open=c,
        high=c + 1.0,
        low=c - 1.0,
        close=c,
        volume=np.full(n, 1_000.0),
        interval=timedelta(hours=1),
    )


# --------------------------------------------------------------------------- #
# Crossover behaviour on a hand-built rising-then-falling series              #
# --------------------------------------------------------------------------- #


def test_goes_long_then_flat_at_expected_bars() -> None:
    # Rises to a peak at index 4, then falls. With fast=2, slow=3 (windows ending
    # at t-1): the fast average leads the slow one while rising and lags once it
    # turns down.
    #   t:            0    1    2    3    4    5    6    7    8
    #   close:        1    2    3    4    5    4    3    2    1
    #   fast(t-2,t-1)  -    -    -  2.5  3.5  4.5  4.5  3.5  2.5
    #   slow(t-3,t-1)  -    -    -  2.0  3.0  4.0  4.33 4.0  3.0
    #   signal:        0    0    0    1    1    1    1    0    0
    frame = _frame([1, 2, 3, 4, 5, 4, 3, 2, 1])
    strat = SmaCross(fast=2, slow=3)
    signals = [strat.on_bar(MarketView(frame, t)).target_weight for t in range(len(frame))]

    assert signals == [0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0]


# --------------------------------------------------------------------------- #
# It never reads bar t                                                        #
# --------------------------------------------------------------------------- #


class _RecordingSeries:
    """Wraps a BoundedSeries and records every absolute bar index it is asked for."""

    def __init__(self, inner: Any, cursor: int, reads: set[int]) -> None:
        self._inner = inner
        self._cursor = cursor
        self._reads = reads

    def __len__(self) -> int:
        return len(self._inner)

    def __getitem__(self, key: int | slice) -> Any:
        n = self._cursor + 1
        if isinstance(key, slice):
            self._reads.update(range(*key.indices(n)))
        else:
            j = int(key)
            self._reads.add(j + n if j < 0 else j)
        return self._inner[key]

    def mean(self, *args: Any, **kwargs: Any) -> Any:
        # A whole-series aggregation would read the current bar too — record it.
        self._reads.update(range(self._cursor + 1))
        return self._inner.mean(*args, **kwargs)


class _RecordingView:
    """A MarketView whose channel reads are tracked, so tests can see what was read."""

    def __init__(self, frame: OHLCVFrame, cursor: int, reads: set[int]) -> None:
        self._view = MarketView(frame, cursor)
        self._reads = reads

    @property
    def i(self) -> int:
        return self._view.i

    def _rec(self, series: Any) -> _RecordingSeries:
        return _RecordingSeries(series, self._view.i, self._reads)

    @property
    def open(self) -> _RecordingSeries:
        return self._rec(self._view.open)

    @property
    def high(self) -> _RecordingSeries:
        return self._rec(self._view.high)

    @property
    def low(self) -> _RecordingSeries:
        return self._rec(self._view.low)

    @property
    def close(self) -> _RecordingSeries:
        return self._rec(self._view.close)

    @property
    def volume(self) -> _RecordingSeries:
        return self._rec(self._view.volume)


def test_never_reads_the_current_bar() -> None:
    frame = _frame([1, 2, 3, 4, 5, 4, 3, 2, 1])
    strat = SmaCross(fast=2, slow=3)
    for t in range(len(frame)):
        reads: set[int] = set()
        strat.on_bar(_RecordingView(frame, t, reads))  # type: ignore[arg-type]
        assert t not in reads, f"strategy read current bar {t}; reads={sorted(reads)}"


# --------------------------------------------------------------------------- #
# Same registry and pipeline as flat — no special-casing                      #
# --------------------------------------------------------------------------- #


def test_registered_and_built_from_params() -> None:
    assert "sma_cross" in available()
    strat = get_strategy("sma_cross", {"fast": 2, "slow": 3})
    assert isinstance(strat, SmaCross)
    assert (strat.fast, strat.slow) == (2, 3)


def _pipeline_project(root: Path) -> None:
    (root / "config" / "strategies").mkdir(parents=True)
    (root / "data" / "raw").mkdir(parents=True)
    (root / "config" / "base.yaml").write_text(
        "seed: 7\n"
        "data: {splits: data/splits.yaml, bar_interval: 1h}\n"
        "engine: {initial_cash: 100000}\n"
        "costs: {model: bps, fee_bps: 5, half_spread_bps: 5, slippage_bps: 5}\n"
        "results_dir: results\n",
        encoding="utf-8",
    )
    (root / "config" / "strategies" / "sma.yaml").write_text(
        "strategy: {name: sma_cross, params: {fast: 2, slow: 3}}\n"
        "data: {source: data/raw/data.csv}\n",
        encoding="utf-8",
    )
    (root / "data" / "splits.yaml").write_text(
        "train: {start: 2024-01-01T00:00:00Z, end: 2024-01-01T05:00:00Z}\n"
        "validate: {start: 2024-01-01T06:00:00Z, end: 2024-01-01T11:00:00Z}\n"
        "holdout: {start: 2024-01-01T12:00:00Z, end: 2024-01-01T17:00:00Z}\n",
        encoding="utf-8",
    )
    base = datetime(2024, 1, 1, tzinfo=UTC)
    lines = ["timestamp,open,high,low,close,volume"]
    for k in range(18):
        t = (base + timedelta(hours=k)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c = 100.0 + k
        lines.append(f"{t},{c - 0.2},{c + 0.5},{c - 0.5},{c},1000")
    (root / "data" / "raw" / "data.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_runs_through_the_same_pipeline_as_flat(tmp_path: Path) -> None:
    _pipeline_project(tmp_path)
    run = run_backtest_from_config("config/strategies/sma.yaml", "validate", root=tmp_path)
    config = read_run(run).config
    assert config["strategy"]["name"] == "sma_cross"
    assert config["strategy"]["params"] == {"fast": 2, "slow": 3}
