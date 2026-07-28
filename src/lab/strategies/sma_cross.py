"""The ``sma_cross`` strategy: long when a fast SMA leads a slow SMA.

Signal logic only. Both moving averages are computed from closes strictly before
the current bar (bars up to ``t-1``); bar ``t``'s own OHLC is never read, so the
decision is causal by construction. It registers by name like every other
strategy — the pipeline treats it exactly as it treats ``flat``.
"""

from __future__ import annotations

from ..engine import MarketView, Signal
from .registry import register


@register("sma_cross")
class SmaCross:
    """Long (1.0) when the fast SMA is above the slow SMA, else flat (0.0).

    ``fast`` and ``slow`` are window lengths in bars, from config; ``fast`` must
    be shorter than ``slow``.
    """

    def __init__(self, fast: int, slow: int) -> None:
        if not 0 < fast < slow:
            raise ValueError(f"sma_cross requires 0 < fast < slow, got fast={fast}, slow={slow}")
        self.fast = fast
        self.slow = slow

    def on_bar(self, view: MarketView) -> Signal:
        t = view.i
        if t < self.slow:
            return Signal(0.0)  # not enough closed bars before bar t
        # Slice stop is exclusive, so these read closes [t-window, t-1] — never bar t.
        fast_sma = view.close[t - self.fast : t].mean()
        slow_sma = view.close[t - self.slow : t].mean()
        return Signal(1.0 if fast_sma > slow_sma else 0.0)
