"""Equal-weight buy-and-hold over a panel — the cross-sectional benchmark.

Targets 1/N in every asset on every bar. Because the executor trades only on
target-vector change, that is a single equal-weight entry at the start, held to
the end with no rebalancing — the return of holding the whole basket. This is
what a cross-sectional strategy must beat, not cash and not SPY.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..engine import PanelView
from .registry import register


@register("equal_weight_buy_hold")
class EqualWeightBuyHold:
    """Hold every asset in the panel at equal weight, never rebalancing on signal."""

    def on_bar(self, view: PanelView) -> Mapping[str, float]:
        weight = 1.0 / len(view.symbols)
        return {symbol: weight for symbol in view.symbols}
