"""The multi-asset (panel) backtest loop.

Mirrors the single-asset loop's discipline: a strategy decides on bar ``t`` from
a :class:`PanelView` (bounded per symbol), and the decision is executed at bar
``t+1``'s opens — never same-bar. A cross-sectional strategy returns a mapping
``symbol -> target weight``; the portfolio trades only when that vector changes.
Bars are open-labeled (:data:`BarLabel.OPEN`), rejected otherwise.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol, runtime_checkable

from ..costs.base import CostModel
from ..costs.simple import default_cost_model
from .bars import BarConventionError, BarLabel
from .multi_portfolio import MultiAssetPortfolio
from .panel import Panel, PanelView
from .portfolio import Fill


@runtime_checkable
class PanelStrategy(Protocol):
    """Maps the visible multi-asset market to target weights per symbol."""

    def on_bar(self, view: PanelView) -> Mapping[str, float]: ...


@dataclass(frozen=True)
class PanelEquityPoint:
    """One bar's total mark-to-market book, marked at the bar's closes."""

    timestamp: datetime
    equity: Decimal
    gross_exposure: float  # sum |position value| / equity


@dataclass(frozen=True)
class PanelBacktestResult:
    """Outcome of a panel run: per-asset fills, total equity curve, final book."""

    panel: Panel
    interval: timedelta
    initial_cash: Decimal
    fills: list[Fill]
    equity_curve: list[PanelEquityPoint]
    final_cash: Decimal
    final_positions: dict[str, Decimal]


def run_panel_backtest(
    panel: Panel,
    strategy: PanelStrategy,
    *,
    cost_model: CostModel | None = None,
    initial_cash: Decimal = Decimal(100_000),
) -> PanelBacktestResult:
    """Run a cross-sectional ``strategy`` over ``panel`` with one-bar-deferred fills."""
    if panel.label is not BarLabel.OPEN:
        raise BarConventionError(
            f"panel engine requires open-labeled bars (BarLabel.OPEN); got {panel.label}"
        )

    cm = cost_model if cost_model is not None else default_cost_model()
    portfolio = MultiAssetPortfolio(cash=initial_cash, cost_model=cm)
    symbols = panel.symbols

    equity_curve: list[PanelEquityPoint] = []
    pending: Mapping[str, float] | None = None
    for t in range(len(panel)):
        if pending is not None:
            opens = {s: float(panel.frames[s].open[t]) for s in symbols}
            portfolio.set_target_weights(pending, opens, panel.timestamps[t])

        weights = strategy.on_bar(PanelView(panel, t))
        if not isinstance(weights, Mapping):
            raise TypeError(f"panel strategy on_bar must return a mapping, got {type(weights)!r}")
        pending = weights

        closes = {s: Decimal(str(panel.frames[s].close[t])) for s in symbols}
        equity = portfolio.equity(closes)
        gross = sum(
            (abs(portfolio.positions.get(s, Decimal(0)) * closes[s]) for s in symbols), Decimal(0)
        )
        exposure = float(gross / equity) if equity != 0 else 0.0
        equity_curve.append(PanelEquityPoint(panel.timestamps[t], equity, exposure))

    return PanelBacktestResult(
        panel=panel,
        interval=panel.interval,
        initial_cash=initial_cash,
        fills=portfolio.fills,
        equity_curve=equity_curve,
        final_cash=portfolio.cash,
        final_positions=dict(portfolio.positions),
    )
