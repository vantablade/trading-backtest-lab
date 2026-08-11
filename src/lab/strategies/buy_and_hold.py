"""The ``buy_and_hold`` benchmark: hold the asset for the whole run.

It targets full long exposure on every bar. Because the executor trades only on
target-weight changes, that means a single entry held to the end — the return of
holding the asset over the split, net of one entry's costs. Every real strategy
should be scored against this, not against cash (``flat``).
"""

from __future__ import annotations

from ..engine import MarketView, Signal
from .registry import register


@register("buy_and_hold")
class BuyAndHold:
    """Always fully long (target weight 1.0)."""

    def on_bar(self, view: MarketView) -> Signal:
        return Signal(1.0)
