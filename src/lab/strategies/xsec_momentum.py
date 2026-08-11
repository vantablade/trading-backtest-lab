"""Cross-sectional momentum over a panel of assets.

On each rebalance date, rank the panel's assets by their trailing ``lookback``-bar
return — computed from closes up to ``t-1`` only, never bar ``t`` — hold the top
``hold_top`` equal-weight until the next rebalance, and stay flat until there is
enough history. Signal logic only; params come from config and are not tuned.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..engine import PanelView
from .registry import register


@register("xsec_momentum")
class XSectionalMomentum:
    """Rank by trailing return, hold the top ``hold_top`` equal-weight, rebalance monthly."""

    def __init__(self, lookback: int, hold_top: int, rebalance: str = "monthly") -> None:
        if lookback < 1:
            raise ValueError(f"lookback must be >= 1, got {lookback}")
        if hold_top < 1:
            raise ValueError(f"hold_top must be >= 1, got {hold_top}")
        if rebalance != "monthly":
            raise ValueError(f"only 'monthly' rebalance is implemented, got {rebalance!r}")
        self.lookback = lookback
        self.hold_top = hold_top
        self.rebalance = rebalance
        self._last_month: tuple[int, int] | None = None
        self._weights: dict[str, float] = {}

    def on_bar(self, view: PanelView) -> Mapping[str, float]:
        t = view.i
        if t <= self.lookback:
            return {}  # need closes at t-1 and t-1-lookback (>= 0) to rank
        month = (view.now.year, view.now.month)
        if month != self._last_month:  # first bar of a new month -> rebalance
            self._last_month = month
            self._weights = self._select(view)
        return self._weights  # unchanged between rebalances -> executor holds

    def _select(self, view: PanelView) -> dict[str, float]:
        t = view.i
        returns: dict[str, float] = {}
        for symbol in view.symbols:
            closes = view.view(symbol).close
            recent = closes[t - 1]  # bar t-1 (never t)
            base = closes[t - 1 - self.lookback]  # bar t-1-lookback
            returns[symbol] = float(recent / base - 1.0)
        winners = sorted(returns, key=lambda s: returns[s], reverse=True)[: self.hold_top]
        weight = 1.0 / self.hold_top
        return {symbol: weight for symbol in winners}
