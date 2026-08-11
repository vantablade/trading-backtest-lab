"""End-to-end: a multi-asset strategy runs through the same pipeline as the rest."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from lab.pipeline import run_backtest_from_config
from lab.results import read_run

BASE_YAML = (
    "seed: 7\n"
    "data: {splits: data/splits.yaml, bar_interval: 1h}\n"
    "engine: {initial_cash: 100000}\n"
    "costs: {model: bps, fee_bps: 5, half_spread_bps: 5, slippage_bps: 5}\n"
    "results_dir: results\n"
)
MOM_YAML = (
    "strategy: {name: xsec_momentum, params: {lookback: 5, hold_top: 1, rebalance: monthly}}\n"
    "data:\n"
    "  bar_interval: 1d\n"
    "  sources: {AAA: data/raw/aaa.csv, BBB: data/raw/bbb.csv, CCC: data/raw/ccc.csv}\n"
)
SPLITS_YAML = (
    "train: {start: 2024-01-01T00:00:00Z, end: 2024-02-29T23:59:59Z}\n"
    "validate: {start: 2024-03-01T00:00:00Z, end: 2024-05-31T23:59:59Z}\n"
    "holdout: {start: 2024-06-01T00:00:00Z, end: 2024-12-31T23:59:59Z}\n"
)


def _write_series(path: Path, factor: float, n: int = 180) -> None:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    lines = ["timestamp,open,high,low,close,volume"]
    for k in range(n):
        t = (base + timedelta(days=k)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c = 100.0 * factor**k
        lines.append(f"{t},{c:.4f},{c + 1:.4f},{c - 1:.4f},{c:.4f},1000000")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _project(root: Path) -> None:
    (root / "config" / "strategies").mkdir(parents=True)
    (root / "data" / "raw").mkdir(parents=True)
    (root / "config" / "base.yaml").write_text(BASE_YAML, encoding="utf-8")
    (root / "config" / "strategies" / "mom.yaml").write_text(MOM_YAML, encoding="utf-8")
    (root / "data" / "splits.yaml").write_text(SPLITS_YAML, encoding="utf-8")
    _write_series(root / "data" / "raw" / "aaa.csv", 1.003)  # strongest trend
    _write_series(root / "data" / "raw" / "bbb.csv", 1.001)
    _write_series(root / "data" / "raw" / "ccc.csv", 0.999)


def test_xsec_momentum_runs_through_the_pipeline(tmp_path: Path) -> None:
    _project(tmp_path)
    run = run_backtest_from_config("config/strategies/mom.yaml", "validate", root=tmp_path)
    arts = read_run(run)

    assert arts.config["strategy"]["name"] == "xsec_momentum"
    assert "sources" in arts.config["data"]

    # trades carry a per-asset symbol column
    assert arts.trades, "expected at least one trade"
    assert all("symbol" in row for row in arts.trades)
    assert {row["symbol"] for row in arts.trades} <= {"AAA", "BBB", "CCC"}

    # equity curve has total exposure; manifest pins every source
    assert all("gross_exposure" in row for row in arts.equity)
    assert len(arts.manifest["data"]["sources"]) == 3
    assert arts.manifest["data"]["n_symbols"] == 3
