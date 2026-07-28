"""Thin summary metrics for a completed backtest.

Deliberately minimal — this set will grow (Sharpe, drawdown, hit rate, regime
breakdowns). Everything here is net of costs (the equity curve already includes
them) and reported as float: this is a vectorised/reporting context, not the
Decimal accounting path (CLAUDE.md conventions).
"""

from __future__ import annotations

from decimal import Decimal

from ..engine import BacktestResult


def compute_metrics(result: BacktestResult) -> dict[str, float | int]:
    """Summary statistics computed from a run's fills and equity curve."""
    initial = float(result.initial_cash)
    final = float(result.equity_curve[-1].equity) if result.equity_curve else initial
    total_costs = float(sum((f.costs.total for f in result.fills), Decimal(0)))
    realised_pnl = float(sum((f.realised_pnl for f in result.fills), Decimal(0)))
    return {
        "n_bars": len(result.frame),
        "n_trades": len(result.fills),
        "initial_equity": initial,
        "final_equity": final,
        "total_return": (final / initial - 1.0) if initial else 0.0,
        "total_costs": total_costs,
        "realised_pnl": realised_pnl,
    }
