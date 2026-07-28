"""The full backtest pipeline: resolve config -> load -> slice to split -> run -> write.

This is the top-level orchestrator behind ``lab backtest``. It ties the layers
together but contains no strategy, sizing, or cost logic of its own.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from .config import ConfigError, resolve_config
from .costs import BpsCost, CostModel
from .data import load_csv_bars
from .engine import run_backtest
from .results import DataSourceRef, write_run
from .strategies import get_strategy


def run_backtest_from_config(
    strategy_path: str | Path,
    split: str,
    *,
    root: str | Path | None = None,
    allow_holdout: bool = False,
) -> Path:
    """Run the backtest described by ``strategy_path`` on ``split`` and write it.

    Returns the created ``results/run_NNNN/`` directory. Loading the holdout
    split requires ``allow_holdout=True`` (the ``--allow-holdout`` CLI flag).
    """
    root = Path(root) if root is not None else Path.cwd()
    config = resolve_config(strategy_path, split, root=root, allow_holdout=allow_holdout)

    loaded = load_csv_bars(config.data_source(), interval=config.bar_interval())
    frame = loaded.frame.between(config.split_range.start, config.split_range.end)

    result = run_backtest(
        frame,
        get_strategy(config.strategy_name(), config.strategy_params()),
        cost_model=_cost_model(config.costs_config()),
        initial_cash=config.initial_cash(),
    )

    return write_run(
        config.results_dir(),
        result=result,
        config=config.merged,
        sources=[DataSourceRef(path=str(config.data_source()), sha256=loaded.report.sha256)],
        repo_dir=root,
    )


def _cost_model(costs: dict[str, Any]) -> CostModel:
    model = costs.get("model", "bps")
    if model != "bps":
        raise ConfigError(f"unknown cost model {model!r}; only 'bps' is implemented")
    return BpsCost(
        fee_bps=Decimal(str(costs["fee_bps"])),
        half_spread_bps=Decimal(str(costs["half_spread_bps"])),
        slippage_bps=Decimal(str(costs["slippage_bps"])),
    )
