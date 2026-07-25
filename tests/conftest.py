"""Shared fixtures for the test suite."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from lab.engine import OHLCVFrame


def utc_hours(n: int, start: datetime | None = None) -> np.ndarray:
    """An object array of ``n`` hourly, timezone-aware UTC timestamps."""
    base = start or datetime(2024, 1, 1, tzinfo=UTC)
    return np.array([base + timedelta(hours=k) for k in range(n)], dtype=object)


def make_frame(n: int = 64) -> OHLCVFrame:
    """A synthetic frame with a strictly increasing close.

    Strictly increasing matters for the no-lookahead tests: the global maximum
    is always the *last* bar, so any visible-window statistic must be strictly
    smaller than the full-frame statistic. If a bounded read ever leaked the
    future, that inequality would break.
    """
    close = np.linspace(100.0, 100.0 + (n - 1), n)
    open_ = close - 0.5
    high = close + 1.0
    low = close - 1.0
    volume = np.full(n, 1_000.0)
    return OHLCVFrame(
        timestamps=utc_hours(n),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        interval=timedelta(hours=1),
    )


@pytest.fixture
def frame() -> OHLCVFrame:
    return make_frame()


@pytest.fixture
def frame_factory():
    return make_frame
