"""Portfolio accounting and order simulation.

Money lives in :class:`~decimal.Decimal` on this accounting path (CLAUDE.md
conventions). Every fill goes through the injected :class:`CostModel`, so a
trade can never be recorded gross of costs.

The weight-to-size mapping here is a deliberate placeholder: it treats the
strategy's target weight as a target fraction of current equity. Real position
sizing, exposure limits, and kill switches belong in ``lab.risk`` and will
replace this. The engine's job is only to turn a size into an honest fill.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from ..costs.base import CostModel


@dataclass(frozen=True)
class Fill:
    """A single executed trade."""

    timestamp: datetime
    price: Decimal
    units: Decimal  # signed: positive bought, negative sold
    cost: Decimal
    target_weight: float


@dataclass
class Portfolio:
    """Cash, a single position, and the fills that got us there."""

    cash: Decimal
    cost_model: CostModel
    position: Decimal = Decimal(0)
    fills: list[Fill] = field(default_factory=list)

    def equity(self, price: Decimal) -> Decimal:
        return self.cash + self.position * price

    def set_target_weight(self, target_weight: float, price: float, timestamp: datetime) -> None:
        """Rebalance toward ``target_weight`` of equity at ``price``.

        A no-op trade (delta of zero) records nothing. Otherwise the trade is
        charged the cost model's cost and appended to ``fills``.
        """
        price_d = Decimal(str(price))
        equity = self.equity(price_d)
        target_units = (Decimal(str(target_weight)) * equity) / price_d
        delta = target_units - self.position
        if delta == 0:
            return

        notional = delta * price_d
        cost = self.cost_model.cost(notional, side=1 if delta > 0 else -1)
        self.cash -= notional + cost
        self.position = target_units
        self.fills.append(
            Fill(
                timestamp=timestamp,
                price=price_d,
                units=delta,
                cost=cost,
                target_weight=float(target_weight),
            )
        )
