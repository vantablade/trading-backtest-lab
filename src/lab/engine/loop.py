"""The backtest event loop.

**Bar-labeling convention.** The engine assumes :class:`BarLabel.OPEN`: a bar's
timestamp names its open, and bar ``t`` covers ``[t, t+interval)``. Its close is
only known at ``t+interval``. The loop is built around this: a trade executed at
bar ``t``'s open uses only bars ``0..t-1`` — the bars that have fully closed by
wall-clock time ``t``. A frame carrying any other convention is rejected up front
by :func:`run_backtest` (see ``REQUIRED_BAR_LABEL``).

Two no-lookahead properties are enforced structurally here:

1. On bar ``t`` the strategy is handed a :class:`MarketView` that can only read
   bars ``0..t`` (see ``market_view``).
2. The signal it returns is *not* executed on bar ``t``. It is held and filled
   at bar ``t+1``'s open. Equivalently: the trade filled at bar ``t``'s open was
   decided from bars ``0..t-1`` only. A signal emitted on the final bar has no
   next bar to fill at, and so never executes — which is correct, not a bug.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from ..costs.base import CostModel
from ..costs.simple import default_cost_model
from .bars import BarConventionError, BarLabel, OHLCVFrame
from .market_view import MarketView
from .portfolio import Fill, Portfolio
from .signals import Signal, Strategy

#: The only bar-labeling convention the engine's execution model is valid for.
REQUIRED_BAR_LABEL = BarLabel.OPEN


@dataclass(frozen=True)
class BacktestResult:
    """The outcome of a run: the fills and the final book.

    ``interval`` is copied from the frame so downstream metrics (annualisation,
    turnover per unit time) never have to re-derive the bar spacing.
    """

    frame: OHLCVFrame
    interval: timedelta
    fills: list[Fill]
    final_cash: Decimal
    final_position: Decimal


def run_backtest(
    frame: OHLCVFrame,
    strategy: Strategy,
    *,
    cost_model: CostModel | None = None,
    initial_cash: Decimal = Decimal(100_000),
) -> BacktestResult:
    """Run ``strategy`` over ``frame`` with one-bar-deferred execution.

    Rejects any frame whose bar-labeling convention is not the one the engine's
    execution model is valid for (:data:`REQUIRED_BAR_LABEL`); see the module
    docstring. Costs are always on: if ``cost_model`` is omitted, a pessimistic
    default is used so a gross-of-cost run cannot happen by accident (rule 4).
    """
    if frame.label is not REQUIRED_BAR_LABEL:
        raise BarConventionError(
            f"engine requires open-labeled bars ({REQUIRED_BAR_LABEL}: timestamp "
            f"names the bar's open, bar t spans [t, t+interval)), but got "
            f"{frame.label}. The execution model fills at bar t's open using only "
            f"bars 0..t-1, which is causal only for open-labeled bars. Relabel or "
            f"resample the data to open-labeled bars before backtesting."
        )

    cm = cost_model if cost_model is not None else default_cost_model()
    portfolio = Portfolio(cash=initial_cash, cost_model=cm)

    pending: Signal | None = None
    for t in range(len(frame)):
        # Execute the previous bar's decision at THIS bar's open. Never same-bar.
        if pending is not None:
            portfolio.set_target_weight(
                pending.target_weight,
                float(frame.open[t]),
                frame.timestamps[t],
            )

        view = MarketView(frame, t)
        signal = strategy.on_bar(view)
        if not isinstance(signal, Signal):
            raise TypeError(f"strategy.on_bar must return a Signal, got {type(signal)!r}")
        pending = signal
        # The signal from the final bar is intentionally left unexecuted:
        # there is no future bar to fill it at.

    return BacktestResult(
        frame=frame,
        interval=frame.interval,
        fills=portfolio.fills,
        final_cash=portfolio.cash,
        final_position=portfolio.position,
    )
