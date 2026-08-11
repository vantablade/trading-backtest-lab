"""Summary metrics for a completed backtest, from its per-bar equity curve.

Everything here is net of costs (the equity curve already includes them) and
reported as float — this is a vectorised/reporting context, not the Decimal
accounting path (CLAUDE.md).

Annualisation uses the *observed* number of bars per calendar year, derived from
the equity curve's own timestamps — about 252 for daily equity data, because
weekends and holidays are not bars. It deliberately does NOT assume 365: that
would over-annualise daily data by a factor of ~sqrt(365/252).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

import numpy as np

from ..engine import BacktestResult, PanelBacktestResult

_YEAR_SECONDS = 365.25 * 24 * 3600


def compute_metrics(result: BacktestResult | PanelBacktestResult) -> dict[str, float | int]:
    """Summary statistics from a run's equity curve and fills.

    Works for both single-asset and panel results: it needs only ``equity_curve``
    (points with ``timestamp`` and ``equity``), ``fills``, and ``initial_cash``.
    """
    curve = result.equity_curve
    initial = float(result.initial_cash)
    equities = np.array([float(p.equity) for p in curve], dtype=float)
    final = float(equities[-1]) if equities.size else initial

    years = _years_elapsed(curve)
    returns = equities[1:] / equities[:-1] - 1.0 if equities.size > 1 else np.empty(0)

    return {
        "n_bars": len(curve),
        "n_trades": len(result.fills),
        "initial_equity": initial,
        "final_equity": final,
        "total_return": (final / initial - 1.0) if initial else 0.0,
        "cagr": _cagr(initial, final, years),
        "sharpe": _annualized_sharpe(returns, years),
        "max_drawdown": _max_drawdown(equities),
        "total_costs": float(sum((f.costs.total for f in result.fills), Decimal(0))),
        "realised_pnl": float(sum((f.realised_pnl for f in result.fills), Decimal(0))),
    }


def _years_elapsed(curve: Sequence[Any]) -> float:
    if len(curve) < 2:
        return 0.0
    return (curve[-1].timestamp - curve[0].timestamp).total_seconds() / _YEAR_SECONDS


def _annualized_sharpe(returns: np.ndarray, years: float) -> float:
    """Mean/stdev of per-bar returns, scaled by sqrt(observed bars per year)."""
    if returns.size < 2 or years <= 0:
        return 0.0
    sd = float(returns.std(ddof=1))
    if sd == 0.0:
        return 0.0  # no variance (e.g. always flat) -> undefined; report 0
    bars_per_year = returns.size / years  # ~252 for daily equity data
    return float(returns.mean() / sd * math.sqrt(bars_per_year))


def _max_drawdown(equities: np.ndarray) -> float:
    """Worst peak-to-trough decline of the equity curve, as a negative fraction."""
    if equities.size == 0:
        return 0.0
    running_max = np.maximum.accumulate(equities)
    return float((equities / running_max - 1.0).min())


def _cagr(initial: float, final: float, years: float) -> float:
    if years <= 0 or initial <= 0 or final <= 0:
        return 0.0
    try:
        cagr = (final / initial) ** (1.0 / years) - 1.0
    except (OverflowError, ValueError):
        return 0.0
    return cagr if math.isfinite(cagr) else 0.0
