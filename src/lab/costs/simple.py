"""A single pessimistic bps cost model — the engine's always-on default."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

_BPS = Decimal(10_000)


@dataclass(frozen=True)
class BpsCost:
    """Combined per-trade cost as basis points of absolute traded notional.

    Fee, half-spread, and slippage are all charged, always, on every trade
    (CLAUDE.md rule 4). Defaults are deliberately pessimistic; when unsure about
    a parameter, raise it rather than lower it.
    """

    fee_bps: Decimal = Decimal(5)
    half_spread_bps: Decimal = Decimal(5)
    slippage_bps: Decimal = Decimal(5)

    def cost(self, notional: Decimal, *, side: int) -> Decimal:
        total_bps = self.fee_bps + self.half_spread_bps + self.slippage_bps
        return abs(notional) * total_bps / _BPS


def default_cost_model() -> BpsCost:
    """The cost model the engine uses when a caller supplies none."""
    return BpsCost()
