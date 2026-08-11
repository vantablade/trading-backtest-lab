"""Multi-asset portfolio accounting for panel backtests.

The single-asset :class:`~lab.engine.portfolio.Portfolio` generalised to N
positions. Same discipline: money is Decimal, every fill goes through the cost
model, average-cost realised PnL, and — critically — it trades **only when the
target weight vector changes**, so a held allocation is not re-balanced every
bar (the churn fix, one dimension up). Each fill carries its ``symbol``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from ..costs.base import CostModel
from .portfolio import Fill

_GROSS_TOLERANCE = Decimal("1.000000001")


@dataclass
class MultiAssetPortfolio:
    """Cash and a position per symbol, rebalanced only on target-vector change."""

    cash: Decimal
    cost_model: CostModel
    positions: dict[str, Decimal] = field(default_factory=dict)
    avg_prices: dict[str, Decimal] = field(default_factory=dict)
    fills: list[Fill] = field(default_factory=list)
    _target_weights: dict[str, Decimal] = field(default_factory=dict, init=False)

    def equity(self, prices: Mapping[str, Decimal]) -> Decimal:
        total = self.cash
        for symbol, position in self.positions.items():
            total += position * prices[symbol]
        return total

    def set_target_weights(
        self,
        weights: Mapping[str, float],
        prices: Mapping[str, float],
        timestamp: datetime,
    ) -> None:
        """Rebalance to ``weights`` (symbol -> fraction of equity) at ``prices``.

        Symbols absent from ``weights`` are targeted at 0. If the resulting
        vector equals the one currently held, nothing trades. Gross exposure
        (sum of absolute weights) may not exceed 1.
        """
        symbols = list(prices)
        target = {s: Decimal(str(weights.get(s, 0.0))) for s in symbols}
        if target == self._target_weights:
            return  # allocation unchanged: hold, do not churn

        gross = sum((abs(w) for w in target.values()), Decimal(0))
        if gross > _GROSS_TOLERANCE:
            raise ValueError(f"gross target weight {gross} exceeds 1.0")
        self._target_weights = target

        price_d = {s: Decimal(str(prices[s])) for s in symbols}
        equity = self.equity(price_d)
        for symbol in symbols:
            target_units = (target[symbol] * equity) / price_d[symbol]
            delta = target_units - self.positions.get(symbol, Decimal(0))
            if delta == 0:
                continue
            costs = self.cost_model.charge(delta * price_d[symbol], side=1 if delta > 0 else -1)
            realised = self._apply(symbol, delta, price_d[symbol])
            self.cash -= delta * price_d[symbol] + costs.total
            self.fills.append(
                Fill(
                    timestamp=timestamp,
                    price=price_d[symbol],
                    units=delta,
                    costs=costs,
                    realised_pnl=realised,
                    position_after=self.positions[symbol],
                    symbol=symbol,
                )
            )

    def _apply(self, symbol: str, delta: Decimal, price: Decimal) -> Decimal:
        """Update one symbol's position/avg price for ``delta``; return realised PnL."""
        pos = self.positions.get(symbol, Decimal(0))
        avg = self.avg_prices.get(symbol, Decimal(0))
        if pos == 0 or (pos > 0) == (delta > 0):
            new_pos = pos + delta
            self.avg_prices[symbol] = price if pos == 0 else (avg * pos + price * delta) / new_pos
            self.positions[symbol] = new_pos
            return Decimal(0)

        closing = min(abs(delta), abs(pos))
        direction = Decimal(1) if pos > 0 else Decimal(-1)
        realised = (price - avg) * closing * direction
        new_pos = pos + delta
        if new_pos == 0:
            self.avg_prices[symbol] = Decimal(0)
        elif (new_pos > 0) != (pos > 0):
            self.avg_prices[symbol] = price
        self.positions[symbol] = new_pos
        return realised
