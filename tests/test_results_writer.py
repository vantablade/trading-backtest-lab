"""Tests for the results writer: numbering, atomicity, provenance, round-trip."""

from __future__ import annotations

import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from lab.engine import BacktestResult, OHLCVFrame, Signal, run_backtest
from lab.metrics import compute_metrics
from lab.results import DataSourceRef, git_provenance, read_run, write_run

ARTIFACTS = ("trades.parquet", "equity.parquet", "metrics.json", "config.yaml", "manifest.json")


class _Long:
    def on_bar(self, view: Any) -> Signal:
        return Signal(1.0)


def _frame(n: int = 6) -> OHLCVFrame:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    ts = np.array([base + timedelta(hours=k) for k in range(n)], dtype=object)
    close = np.linspace(100.0, 105.0, n)
    return OHLCVFrame(
        timestamps=ts,
        open=close - 0.2,
        high=close + 0.5,
        low=close - 0.5,
        close=close,
        volume=np.full(n, 1_000.0),
        interval=timedelta(hours=1),
    )


def _result() -> BacktestResult:
    return run_backtest(_frame(), _Long())


def _config() -> dict[str, Any]:
    return {
        "strategy": {"name": "long", "params": {}},
        "costs": {"fee_bps": 5, "half_spread_bps": 5, "slippage_bps": 5},
        "engine": {"initial_cash": 100000},
        "seed": 7,
    }


def _sources() -> list[DataSourceRef]:
    return [DataSourceRef(path="data/raw/SYN.csv", sha256="a" * 64)]


# --------------------------------------------------------------------------- #
# Numbering                                                                   #
# --------------------------------------------------------------------------- #


def test_first_run_is_run_0001_with_all_artifacts(tmp_path: Path) -> None:
    run = write_run(tmp_path / "results", result=_result(), config=_config(), repo_dir=tmp_path)
    assert run.name == "run_0001"
    for name in ARTIFACTS:
        assert (run / name).is_file()


def test_numbering_increments_and_respects_existing(tmp_path: Path) -> None:
    results = tmp_path / "results"
    r1 = write_run(results, result=_result(), config=_config(), repo_dir=tmp_path)
    r2 = write_run(results, result=_result(), config=_config(), repo_dir=tmp_path)
    assert (r1.name, r2.name) == ("run_0001", "run_0002")

    (results / "run_0007").mkdir()  # a gap; next number is max+1
    r3 = write_run(results, result=_result(), config=_config(), repo_dir=tmp_path)
    assert r3.name == "run_0008"


def test_concurrent_writes_get_distinct_numbers(tmp_path: Path) -> None:
    results = tmp_path / "results"

    def one(_: int) -> str:
        return write_run(results, result=_result(), config=_config(), repo_dir=tmp_path).name

    with ThreadPoolExecutor(max_workers=8) as ex:
        names = list(ex.map(one, range(8)))

    assert set(names) == {f"run_{i:04d}" for i in range(1, 9)}  # distinct, no clobber
    for name in names:
        assert (results / name / "manifest.json").is_file()  # each is complete


# --------------------------------------------------------------------------- #
# Atomicity                                                                   #
# --------------------------------------------------------------------------- #


def test_publish_is_a_single_atomic_rename_from_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str]] = []
    real_rename = os.rename

    def spy(src: Any, dst: Any) -> None:
        calls.append((str(src), str(dst)))
        real_rename(src, dst)

    monkeypatch.setattr(os, "rename", spy)
    run = write_run(tmp_path / "results", result=_result(), config=_config(), repo_dir=tmp_path)

    publish = [c for c in calls if Path(c[1]).name.startswith("run_")]
    assert len(publish) == 1  # the run appears via exactly one rename
    src, dst = publish[0]
    assert Path(src).name.startswith(".tmp-run-")  # staged in a temp dir first
    assert Path(dst) == run


def test_failed_write_leaves_no_run_and_no_temp(tmp_path: Path) -> None:
    results = tmp_path / "results"
    bad_config = {"x": object()}  # not YAML-serialisable -> write fails mid-way
    with pytest.raises(yaml.YAMLError):
        write_run(results, result=_result(), config=bad_config, repo_dir=tmp_path)

    assert list(results.glob("run_*")) == []  # no half-written run
    assert list(results.glob(".tmp-run-*")) == []  # staged dir cleaned up


# --------------------------------------------------------------------------- #
# Round-trip read-back                                                        #
# --------------------------------------------------------------------------- #


def test_round_trip_read_back(tmp_path: Path) -> None:
    result = _result()
    config = _config()
    run = write_run(
        tmp_path / "results",
        result=result,
        config=config,
        sources=_sources(),
        repo_dir=tmp_path,
    )
    arts = read_run(run)

    assert len(arts.trades) == len(result.fills)
    for row, fill in zip(arts.trades, result.fills, strict=True):
        assert row["timestamp"] == fill.timestamp
        assert row["side"] == ("buy" if fill.units > 0 else "sell")
        assert row["price"] == float(fill.price)
        assert row["size"] == float(abs(fill.units))
        assert row["fees"] == float(fill.costs.fees)
        assert row["slippage"] == float(fill.costs.spread + fill.costs.slippage)
        assert row["realised_pnl"] == float(fill.realised_pnl)
        assert row["position_after"] == float(fill.position_after)

    assert len(arts.equity) == len(result.equity_curve)
    for row, point in zip(arts.equity, result.equity_curve, strict=True):
        assert row["timestamp"] == point.timestamp
        assert row["equity"] == float(point.equity)
        assert row["position"] == float(point.position)
        assert row["exposure"] == point.exposure

    assert arts.metrics == compute_metrics(result)
    assert arts.config == config


def test_manifest_records_data_and_code_provenance(tmp_path: Path) -> None:
    result = _result()
    run = write_run(
        tmp_path / "results",
        result=result,
        config=_config(),
        sources=_sources(),
        repo_dir=tmp_path,  # not a git repo -> null provenance
    )
    manifest = read_run(run).manifest

    assert manifest["data"]["sources"] == [{"path": "data/raw/SYN.csv", "sha256": "a" * 64}]
    assert manifest["data"]["bar_label"] == "open"
    assert manifest["data"]["interval"] == "1:00:00"
    assert manifest["data"]["n_bars"] == len(result.frame)
    assert manifest["data"]["start"] == result.frame.timestamps[0].isoformat()
    assert manifest["data"]["end"] == result.frame.timestamps[-1].isoformat()
    assert manifest["code"] == {"commit": None, "dirty": None}


# --------------------------------------------------------------------------- #
# Git provenance                                                              #
# --------------------------------------------------------------------------- #


def test_git_provenance_non_repo(tmp_path: Path) -> None:
    assert git_provenance(tmp_path) == {"commit": None, "dirty": None}


def test_git_provenance_reports_commit_and_dirty(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git not available")
    repo = tmp_path / "repo"
    repo.mkdir()

    def g(*args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)

    g("init")
    g("config", "user.email", "t@example.com")
    g("config", "user.name", "Test")
    (repo / "a.txt").write_text("hello", encoding="utf-8")
    g("add", "a.txt")
    g("commit", "-m", "initial")

    prov = git_provenance(repo)
    assert prov["commit"] is not None
    assert len(str(prov["commit"])) == 40
    assert prov["dirty"] is False

    (repo / "b.txt").write_text("untracked", encoding="utf-8")
    assert git_provenance(repo)["dirty"] is True
