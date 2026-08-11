"""The engine: event loop, market view, portfolio, order simulation.

The market view is where no-lookahead is enforced structurally (CLAUDE.md
rule 2). Any change to this package must keep ``tests/test_no_lookahead.py``
green.
"""

from .bars import BarConventionError, BarLabel, IntervalMismatchError, OHLCVFrame
from .loop import REQUIRED_BAR_LABEL, BacktestResult, EquityPoint, run_backtest
from .market_view import BoundedSeries, LookaheadError, MarketView
from .multi_portfolio import MultiAssetPortfolio
from .panel import Panel, PanelView, align_panel
from .panel_loop import PanelBacktestResult, PanelEquityPoint, PanelStrategy, run_panel_backtest
from .portfolio import Fill, Portfolio
from .signals import Signal, Strategy

__all__ = [
    "REQUIRED_BAR_LABEL",
    "BacktestResult",
    "BarConventionError",
    "BarLabel",
    "BoundedSeries",
    "EquityPoint",
    "Fill",
    "IntervalMismatchError",
    "LookaheadError",
    "MarketView",
    "MultiAssetPortfolio",
    "OHLCVFrame",
    "Panel",
    "PanelBacktestResult",
    "PanelEquityPoint",
    "PanelStrategy",
    "PanelView",
    "Portfolio",
    "Signal",
    "Strategy",
    "align_panel",
    "run_backtest",
    "run_panel_backtest",
]
