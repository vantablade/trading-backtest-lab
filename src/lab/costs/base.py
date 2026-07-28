"""The cost-model interface the engine executes every fill through."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class CostBreakdown:
    """The components of a trade's cost, so they can be reported separately.

    All components are non-negative :class:`~decimal.Decimal` amounts in account
    currency. ``spread`` is the half-spread paid to cross; ``slippage`` is market
    impact beyond the quoted spread. Reporting keeps ``fees`` separate and folds
    ``spread + slippage`` into a single execution-cost column.
    """

    fees: Decimal
    spread: Decimal
    slippage: Decimal

    @property
    def total(self) -> Decimal:
        return self.fees + self.spread + self.slippage


@runtime_checkable
class CostModel(Protocol):
    """Maps a traded notional to the cost charged for that trade.

    ``notional`` is signed (positive to buy, negative to sell); ``side`` is
    +1 for a buy and -1 for a sell, provided for models with asymmetric costs.
    Implementations must return a :class:`CostBreakdown` with non-negative parts.
    """

    def charge(self, notional: Decimal, *, side: int) -> CostBreakdown: ...
