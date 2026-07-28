"""Tests for the config resolver: merge, interval parsing, splits, hash, holdout."""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from lab.config import (
    ConfigError,
    HoldoutError,
    Split,
    deep_merge,
    hash_config,
    load_splits,
    parse_interval,
    resolve_config,
)

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


def _project(root: Path, *, strategy: dict[str, Any] | None = None) -> str:
    (root / "config" / "strategies").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "config" / "base.yaml").write_text(yaml.safe_dump(BASE), encoding="utf-8")
    (root / "config" / "strategies" / "flat.yaml").write_text(
        yaml.safe_dump(STRATEGY if strategy is None else strategy), encoding="utf-8"
    )
    (root / "data" / "splits.yaml").write_text(yaml.safe_dump(SPLITS), encoding="utf-8")
    return "config/strategies/flat.yaml"


# --------------------------------------------------------------------------- #
# Merge, interval parsing, splits                                             #
# --------------------------------------------------------------------------- #


def test_deep_merge_is_recursive() -> None:
    merged = deep_merge({"a": {"x": 1, "y": 2}, "b": 1}, {"a": {"y": 9}, "c": 3})
    assert merged == {"a": {"x": 1, "y": 9}, "b": 1, "c": 3}


def test_parse_interval_units() -> None:
    assert parse_interval("1h") == timedelta(hours=1)
    assert parse_interval("5m") == timedelta(minutes=5)
    assert parse_interval("1d") == timedelta(days=1)
    assert parse_interval("30s") == timedelta(seconds=30)


@pytest.mark.parametrize("bad", ["", "abc", "1x", "h", "1.5h", "1 h"])
def test_parse_interval_rejects_bad(bad: str) -> None:
    with pytest.raises(ConfigError):
        parse_interval(bad)


def test_load_splits_parses_utc(tmp_path: Path) -> None:
    p = tmp_path / "splits.yaml"
    p.write_text(
        "train:\n  start: 2024-01-01T00:00:00Z\n  end: 2024-01-01T05:00:00Z\n"
        "validate:\n  start: 2024-01-01T06:00:00Z\n  end: 2024-01-01T11:00:00Z\n"
        "holdout:\n  start: 2024-01-01T12:00:00Z\n  end: 2024-01-01T17:00:00Z\n",
        encoding="utf-8",
    )
    splits = load_splits(p)
    assert splits.validate.start == datetime(2024, 1, 1, 6, tzinfo=UTC)
    assert splits.validate.start.tzinfo is not None
    assert splits.holdout.end == datetime(2024, 1, 1, 17, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Resolution: merge + split + hash                                            #
# --------------------------------------------------------------------------- #


def test_resolve_merges_and_stamps_split_and_hash(tmp_path: Path) -> None:
    strat = _project(tmp_path)
    cfg = resolve_config(strat, "validate", root=tmp_path)
    m = cfg.merged

    assert m["strategy"]["name"] == "flat"  # from strategy
    assert m["data"]["source"] == "data/raw/data.csv"  # from strategy
    assert m["costs"]["fee_bps"] == 5  # from base
    assert m["seed"] == 7  # from base
    assert m["split"] == {
        "name": "validate",
        "start": "2024-01-01T06:00:00+00:00",
        "end": "2024-01-01T11:00:00+00:00",
    }
    assert m["config_hash"].startswith("sha256:")
    assert cfg.config_hash == m["config_hash"]
    assert hash_config(m) == m["config_hash"]  # recomputable, excludes itself


def test_split_may_not_be_set_in_config(tmp_path: Path) -> None:
    strat = _project(tmp_path, strategy={**STRATEGY, "split": "validate"})
    with pytest.raises(ConfigError, match="split"):
        resolve_config(strat, "validate", root=tmp_path)


def test_hash_is_stable_for_identical_inputs(tmp_path: Path) -> None:
    strat = _project(tmp_path)
    a = resolve_config(strat, "validate", root=tmp_path).config_hash
    b = resolve_config(strat, "validate", root=tmp_path).config_hash
    assert a == b


def test_hash_changes_with_split(tmp_path: Path) -> None:
    strat = _project(tmp_path)
    validate = resolve_config(strat, "validate", root=tmp_path).config_hash
    train = resolve_config(strat, "train", root=tmp_path).config_hash
    assert validate != train


def test_hash_changes_with_a_param(tmp_path: Path) -> None:
    strat = _project(tmp_path)
    before = resolve_config(strat, "validate", root=tmp_path).config_hash
    changed = copy.deepcopy(BASE)
    changed["costs"]["fee_bps"] = 10
    (tmp_path / "config" / "base.yaml").write_text(yaml.safe_dump(changed), encoding="utf-8")
    after = resolve_config(strat, "validate", root=tmp_path).config_hash
    assert before != after


# --------------------------------------------------------------------------- #
# Holdout is sacred                                                           #
# --------------------------------------------------------------------------- #


def test_holdout_requires_explicit_opt_in(tmp_path: Path) -> None:
    strat = _project(tmp_path)
    with pytest.raises(HoldoutError, match="holdout"):
        resolve_config(strat, "holdout", root=tmp_path)
    with pytest.raises(HoldoutError):
        resolve_config(strat, Split.HOLDOUT, root=tmp_path)  # enum form too


def test_holdout_resolves_with_flag(tmp_path: Path) -> None:
    strat = _project(tmp_path)
    cfg = resolve_config(strat, "holdout", root=tmp_path, allow_holdout=True)
    assert cfg.merged["split"]["name"] == "holdout"
    assert cfg.split is Split.HOLDOUT
