"""The cost-model interface the engine executes every fill through."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable


@runtime_checkable
class CostModel(Protocol):
    """Maps a traded notional to the cost charged for that trade.

    ``notional`` is signed (positive to buy, negative to sell); ``side`` is
    +1 for a buy and -1 for a sell, provided for models with asymmetric costs.
    Implementations must return a non-negative :class:`~decimal.Decimal`.
    """

    def cost(self, notional: Decimal, *, side: int) -> Decimal: ...
