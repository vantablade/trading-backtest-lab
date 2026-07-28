"""End-to-end tests for the backtest pipeline and the `lab backtest` CLI."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from lab.cli import main
from lab.config import HoldoutError, hash_config
from lab.pipeline import run_backtest_from_config
from lab.results import read_run

BASE: dict[str, Any] = {
    "seed": 7,
    "data": {"splits": "data/splits.yaml", "bar_interval": "1h"},
    "engine": {"initial_cash": 100000},
    "costs": {"model": "bps", "fee_bps": 5, "half_spread_bps": 5, "slippage_bps": 5},
    "results_dir": "results",
}
STRATEGY: dict[str, Any] = {
    "strategy": {"name": "flat", "params": {}},
    "data": {"source": "data/raw/data.csv"},
}
SPLITS: dict[str, Any] = {
    "train": {"start": "2024-01-01T00:00:00Z", "end": "2024-01-01T05:00:00Z"},
    "validate": {"start": "2024-01-01T06:00:00Z", "end": "2024-01-01T11:00:00Z"},
    "holdout": {"start": "2024-01-01T12:00:00Z", "end": "2024-01-01T17:00:00Z"},
}
STRATEGY_REL = "config/strategies/flat.yaml"


def _project(root: Path) -> None:
    (root / "config" / "strategies").mkdir(parents=True, exist_ok=True)
    (root / "data" / "raw").mkdir(parents=True, exist_ok=True)
    (root / "config" / "base.yaml").write_text(yaml.safe_dump(BASE), encoding="utf-8")
    (root / "config" / "strategies" / "flat.yaml").write_text(
        yaml.safe_dump(STRATEGY), encoding="utf-8"
    )
    (root / "data" / "splits.yaml").write_text(yaml.safe_dump(SPLITS), encoding="utf-8")

    base = datetime(2024, 1, 1, tzinfo=UTC)
    lines = ["timestamp,open,high,low,close,volume"]
    for k in range(18):  # 00:00 .. 17:00, six bars per split
        t = (base + timedelta(hours=k)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c = 100.0 + k
        lines.append(f"{t},{c - 0.2},{c + 0.5},{c - 0.5},{c},1000")
    (root / "data" / "raw" / "data.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Pipeline                                                                    #
# --------------------------------------------------------------------------- #


def test_pipeline_runs_and_records_split_and_hash(tmp_path: Path) -> None:
    _project(tmp_path)
    run = run_backtest_from_config(STRATEGY_REL, "validate", root=tmp_path)
    assert run.name == "run_0001"

    arts = read_run(run)
    assert arts.config["split"]["name"] == "validate"
    assert arts.config["config_hash"].startswith("sha256:")
    # The written config's hash is self-consistent (recompute matches).
    assert hash_config(arts.config) == arts.config["config_hash"]


def test_pipeline_enforces_the_split_boundary(tmp_path: Path) -> None:
    _project(tmp_path)
    run = run_backtest_from_config(STRATEGY_REL, "validate", root=tmp_path)
    data = read_run(run).manifest["data"]
    # Only the validate window was run — no train or holdout bars leaked in.
    assert data["n_bars"] == 6
    assert data["start"] == "2024-01-01T06:00:00+00:00"
    assert data["end"] == "2024-01-01T11:00:00+00:00"


def test_pipeline_refuses_holdout_without_flag(tmp_path: Path) -> None:
    _project(tmp_path)
    with pytest.raises(HoldoutError):
        run_backtest_from_config(STRATEGY_REL, "holdout", root=tmp_path)
    assert list((tmp_path / "results").glob("run_*")) == []  # nothing written


def test_pipeline_runs_holdout_with_flag(tmp_path: Path) -> None:
    _project(tmp_path)
    run = run_backtest_from_config(STRATEGY_REL, "holdout", root=tmp_path, allow_holdout=True)
    assert read_run(run).manifest["data"]["start"] == "2024-01-01T12:00:00+00:00"


def test_identical_configs_hash_equal_different_split_differs(tmp_path: Path) -> None:
    _project(tmp_path)
    r1 = run_backtest_from_config(STRATEGY_REL, "validate", root=tmp_path)
    r2 = run_backtest_from_config(STRATEGY_REL, "validate", root=tmp_path)
    r3 = run_backtest_from_config(STRATEGY_REL, "train", root=tmp_path)
    h1 = read_run(r1).config["config_hash"]
    h2 = read_run(r2).config["config_hash"]
    h3 = read_run(r3).config["config_hash"]
    assert h1 == h2
    assert h1 != h3


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def test_cli_backtest_validate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = main(["backtest", "--config", STRATEGY_REL, "--split", "validate"])
    assert rc == 0
    assert (tmp_path / "results" / "run_0001" / "manifest.json").is_file()


def test_cli_refuses_holdout_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = main(["backtest", "--config", STRATEGY_REL, "--split", "holdout"])
    assert rc == 2
    assert "holdout" in capsys.readouterr().err.lower()
    assert list((tmp_path / "results").glob("run_*")) == []


def test_cli_allows_holdout_with_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = main(["backtest", "--config", STRATEGY_REL, "--split", "holdout", "--allow-holdout"])
    assert rc == 0
    assert (tmp_path / "results" / "run_0001" / "config.yaml").is_file()


def test_cli_split_is_required(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):  # argparse errors out when --split is missing
        main(["backtest", "--config", STRATEGY_REL])
