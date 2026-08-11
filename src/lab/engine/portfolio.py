"""Portfolio accounting and order simulation.

Money lives in :class:`~decimal.Decimal` on this accounting path (CLAUDE.md
conventions). Every fill goes through the injected :class:`CostModel`, so a
trade can never be recorded gross of costs. Each fill records everything the
results writer needs — cost breakdown, realised PnL, and the position after —
so the writer serialises rather than re-derives accounting.

Realised PnL uses average-cost basis: increasing a position moves the average
entry price; reducing, closing, or flipping it realises PnL on the closed
portion (gross of costs, which are reported separately).

Execution is on *signal transitions*, not every bar: a trade happens only when
the target weight changes from the one currently held. A signal held constant
(e.g. long) is entered once and held — no per-bar rebalancing churn. The
weight-to-size mapping is a deliberate placeholder; real sizing belongs in
``lab.risk``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from ..costs.base import CostBreakdown, CostModel


@dataclass(frozen=True)
class Fill:
    """A single executed trade and its consequences."""

    timestamp: datetime
    price: Decimal
    units: Decimal  # signed: positive bought, negative sold
    costs: CostBreakdown
    realised_pnl: Decimal  # on the portion closed by this fill, gross of costs
    position_after: Decimal
    symbol: str = ""  # set by multi-asset runs; single-asset leaves it blank


@dataclass
class Portfolio:
    """Cash, a single position with an average entry price, and its fills."""

    cash: Decimal
    cost_model: CostModel
    position: Decimal = Decimal(0)
    avg_price: Decimal = Decimal(0)
    fills: list[Fill] = field(default_factory=list)
    # The target weight currently held. Starts at 0 (flat/cash). A trade fires
    # only when a new target differs from this — see set_target_weight.
    _target_weight: Decimal = field(default=Decimal(0), init=False)

    def equity(self, price: Decimal) -> Decimal:
        return self.cash + self.position * price

    def set_target_weight(self, target_weight: float, price: float, timestamp: datetime) -> None:
        """Move to ``target_weight`` of equity at ``price``, only on a change.

        If the target weight equals the one already held, nothing happens — the
        existing position is held, with no rebalancing trade. Otherwise the trade
        to the new target is charged the cost model's cost, its realised PnL and
        resulting position are computed, and a :class:`Fill` is appended.
        """
        weight = Decimal(str(target_weight))
        if weight == self._target_weight:
            return  # signal unchanged: hold, do not churn
        self._target_weight = weight

        price_d = Decimal(str(price))
        equity = self.equity(price_d)
        target_units = (weight * equity) / price_d
        delta = target_units - self.position
        if delta == 0:
            return

        costs = self.cost_model.charge(delta * price_d, side=1 if delta > 0 else -1)
        realised = self._apply(delta, price_d)
        self.cash -= delta * price_d + costs.total
        self.fills.append(
            Fill(
                timestamp=timestamp,
                price=price_d,
                units=delta,
                costs=costs,
                realised_pnl=realised,
                position_after=self.position,
            )
        )

    def _apply(self, delta: Decimal, price: Decimal) -> Decimal:
        """Update position and average price for ``delta`` at ``price``; return realised PnL."""
        pos = self.position
        if pos == 0 or (pos > 0) == (delta > 0):
            # Opening or adding in the same direction: weighted-average the entry.
            new_pos = pos + delta
            self.avg_price = price if pos == 0 else (self.avg_price * pos + price * delta) / new_pos
            self.position = new_pos
            return Decimal(0)

        # Opposite direction: realise PnL on the closed portion.
        closing = min(abs(delta), abs(pos))
        direction = Decimal(1) if pos > 0 else Decimal(-1)
        realised = (price - self.avg_price) * closing * direction
        new_pos = pos + delta
        if new_pos == 0:
            self.avg_price = Decimal(0)
        elif (new_pos > 0) != (pos > 0):
            self.avg_price = price  # flipped through zero; residual opens at this price
        # else: partial close, average price of the remainder is unchanged
        self.position = new_pos
        return realised
