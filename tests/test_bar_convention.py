"""The bar-labeling convention is explicit, enforced, and consistent.

Convention (documented in ``engine/bars.py`` and ``engine/loop.py``): bars are
labeled by their OPEN timestamp, so bar ``t`` covers ``[t, t+interval)`` and a
trade executed at bar ``t``'s open uses only bars ``0..t-1``. The engine assumes
this and must reject any frame carrying a different convention.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from lab.data import load_csv_bars
from lab.engine import (
    BarConventionError,
    BarLabel,
    MarketView,
    OHLCVFrame,
    Signal,
    run_backtest,
)


def _frame(label: BarLabel = BarLabel.OPEN, n: int = 8) -> OHLCVFrame:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    ts = np.array([base + timedelta(hours=k) for k in range(n)], dtype=object)
    close = np.linspace(100.0, 100.0 + (n - 1), n)
    return OHLCVFrame(
        timestamps=ts,
        open=close - 0.5,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=np.full(n, 1_000.0),
        interval=timedelta(hours=1),
        label=label,
    )


class _Flat:
    def on_bar(self, view: MarketView) -> Signal:
        return Signal(0.0)


def _write_csv(tmp_path: Path, n: int = 4) -> Path:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    lines = ["timestamp,open,high,low,close,volume"]
    for k in range(n):
        t = (base + timedelta(hours=k)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c = 100.0 + k
        lines.append(f"{t},{c - 0.2},{c + 0.5},{c - 0.5},{c},{1000 + k}")
    p = tmp_path / "bars.csv"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# The convention is explicit and defaults to the harness choice.              #
# --------------------------------------------------------------------------- #


def test_default_frame_label_is_open(frame: OHLCVFrame) -> None:
    assert frame.label is BarLabel.OPEN


def test_label_must_be_a_barlabel() -> None:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    ts = np.array([base + timedelta(hours=k) for k in range(3)], dtype=object)
    z = np.arange(3, dtype=float)
    with pytest.raises(TypeError, match="label must be a BarLabel"):
        OHLCVFrame(
            timestamps=ts,
            open=z,
            high=z + 1,
            low=z - 1,
            close=z,
            volume=z + 10,
            interval=timedelta(hours=1),
            label="open",  # type: ignore[arg-type]
        )


# --------------------------------------------------------------------------- #
# The engine accepts the assumed convention and rejects the opposite one.     #
# --------------------------------------------------------------------------- #


def test_open_labeled_frame_is_accepted() -> None:
    result = run_backtest(_frame(BarLabel.OPEN), _Flat())
    assert result.fills == []


def test_close_labeled_frame_is_rejected() -> None:
    with pytest.raises(BarConventionError, match="open-labeled"):
        run_backtest(_frame(BarLabel.CLOSE), _Flat())


# --------------------------------------------------------------------------- #
# Data and engine agree: the loader records the convention, the engine honours #
# it. A CLOSE-labeled load is faithfully tagged and then refused by the engine.#
# --------------------------------------------------------------------------- #


def test_loader_defaults_to_open(tmp_path: Path) -> None:
    result = load_csv_bars(_write_csv(tmp_path), interval=timedelta(hours=1))
    assert result.frame.label is BarLabel.OPEN


def test_loader_records_close_label_and_engine_rejects_it(tmp_path: Path) -> None:
    result = load_csv_bars(_write_csv(tmp_path), interval=timedelta(hours=1), label=BarLabel.CLOSE)
    assert result.frame.label is BarLabel.CLOSE  # recorded faithfully, not coerced
    with pytest.raises(BarConventionError, match="open-labeled"):
        run_backtest(result.frame, _Flat())
