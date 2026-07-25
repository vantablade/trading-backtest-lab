"""The contract between a strategy and the engine.

A strategy emits a *target signal* and nothing else — no size, no order, no
cost. Turning a weight into a size is the risk layer's job; turning a size into
a fill is the engine's. Keeping these apart is what makes the refinement loop
work (CLAUDE.md, "separation of concerns is load-bearing").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .market_view import MarketView


@dataclass(frozen=True)
class Signal:
    """A desired exposure for the next bar, in ``[-1, 1]``.

    ``+1`` is fully long, ``-1`` fully short, ``0`` flat. This is a *target*,
    not an order: the risk layer decides how much of it to take.
    """

    target_weight: float

    def __post_init__(self) -> None:
        if not -1.0 <= self.target_weight <= 1.0:
            raise ValueError(f"target_weight must be in [-1, 1], got {self.target_weight}")


@runtime_checkable
class Strategy(Protocol):
    """Anything that maps the visible market to a target signal."""

    def on_bar(self, view: MarketView) -> Signal: ...
