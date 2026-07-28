"""Write a backtest run to ``results/run_NNNN/``, atomically.

A run directory contains ``trades.parquet``, ``equity.parquet``, ``metrics.json``,
``config.yaml`` and ``manifest.json`` — enough to reproduce the run from the
directory alone (data pinned by checksum, config resolved, code pinned by commit).

Two robustness properties:

* **Atomic numbering.** The run number is claimed by trying to ``os.rename`` the
  staged directory onto ``run_NNNN``; if that name was taken concurrently the
  rename fails and the next number is tried. No two runs can claim the same name.
* **Atomic publish.** Everything is written into a hidden temp directory on the
  same filesystem and made visible by a single rename on success. A crash leaves
  only a ``.tmp-run-*`` directory, never a half-written ``run_NNNN`` that looks
  complete.

Money is Decimal on the accounting path but is serialised to float64 in the
parquet artifacts: these are analysis outputs (a vectorised context, where
CLAUDE.md permits float), not the accounting ledger.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from ..engine import BacktestResult
from ..metrics import compute_metrics
from .provenance import git_provenance

_RUN_RE = re.compile(r"run_(\d+)")
_TS = pa.timestamp("us", tz="UTC")
_F = pa.float64()

_TRADES_SCHEMA = pa.schema(
    [
        ("timestamp", _TS),
        ("side", pa.string()),
        ("price", _F),
        ("size", _F),
        ("fees", _F),
        ("slippage", _F),
        ("realised_pnl", _F),
        ("position_after", _F),
    ]
)
_EQUITY_SCHEMA = pa.schema(
    [
        ("timestamp", _TS),
        ("equity", _F),
        ("position", _F),
        ("exposure", _F),
    ]
)


@dataclass(frozen=True)
class DataSourceRef:
    """A raw data file that fed the run, pinned by content hash."""

    path: str
    sha256: str


def write_run(
    results_dir: str | Path,
    *,
    result: BacktestResult,
    config: Mapping[str, Any],
    sources: Sequence[DataSourceRef] = (),
    repo_dir: str | Path | None = None,
    metrics: Mapping[str, Any] | None = None,
) -> Path:
    """Write ``result`` to a fresh ``results_dir/run_NNNN/`` and return its path.

    ``config`` is the fully resolved run config (written verbatim to
    ``config.yaml``). ``sources`` pin the raw data by checksum. ``repo_dir`` is
    the repository whose commit is recorded (defaults to the current directory).
    ``metrics`` overrides the computed summary if given.
    """
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    staged = Path(tempfile.mkdtemp(prefix=".tmp-run-", dir=results_dir))
    try:
        _write_artifacts(
            staged,
            result=result,
            config=config,
            sources=sources,
            repo_dir=Path(repo_dir) if repo_dir is not None else Path.cwd(),
            metrics=metrics,
        )
    except BaseException:
        shutil.rmtree(staged, ignore_errors=True)
        raise

    for _ in range(10_000):
        target = results_dir / f"run_{_next_run_number(results_dir):04d}"
        try:
            os.rename(staged, target)
            return target
        except OSError:
            # The name was claimed concurrently (non-empty target); try the next.
            continue

    shutil.rmtree(staged, ignore_errors=True)
    raise RuntimeError("could not allocate a run number after many attempts")


def _next_run_number(results_dir: Path) -> int:
    highest = 0
    for entry in results_dir.iterdir():
        match = _RUN_RE.fullmatch(entry.name)
        if match and entry.is_dir():
            highest = max(highest, int(match.group(1)))
    return highest + 1


def _write_artifacts(
    directory: Path,
    *,
    result: BacktestResult,
    config: Mapping[str, Any],
    sources: Sequence[DataSourceRef],
    repo_dir: Path,
    metrics: Mapping[str, Any] | None,
) -> None:
    pq.write_table(_trades_table(result), directory / "trades.parquet")
    pq.write_table(_equity_table(result), directory / "equity.parquet")

    summary = dict(metrics) if metrics is not None else compute_metrics(result)
    (directory / "metrics.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    (directory / "config.yaml").write_text(
        yaml.safe_dump(dict(config), sort_keys=False), encoding="utf-8"
    )

    manifest = _build_manifest(result, sources, repo_dir)
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def _build_manifest(
    result: BacktestResult, sources: Sequence[DataSourceRef], repo_dir: Path
) -> dict[str, Any]:
    frame = result.frame
    return {
        "created_utc": datetime.now(UTC).isoformat(),
        "data": {
            "sources": [{"path": s.path, "sha256": s.sha256} for s in sources],
            "start": frame.timestamps[0].isoformat(),
            "end": frame.timestamps[-1].isoformat(),
            "interval": str(result.interval),
            "interval_seconds": result.interval.total_seconds(),
            "bar_label": frame.label.value,
            "n_bars": len(frame),
        },
        "code": git_provenance(repo_dir),
        "engine": {"initial_cash": str(result.initial_cash)},
    }


def _trades_table(result: BacktestResult) -> pa.Table:
    fills = result.fills
    columns = {
        "timestamp": [f.timestamp for f in fills],
        "side": ["buy" if f.units > 0 else "sell" for f in fills],
        "price": [float(f.price) for f in fills],
        "size": [float(abs(f.units)) for f in fills],
        "fees": [float(f.costs.fees) for f in fills],
        "slippage": [float(f.costs.spread + f.costs.slippage) for f in fills],
        "realised_pnl": [float(f.realised_pnl) for f in fills],
        "position_after": [float(f.position_after) for f in fills],
    }
    return _typed_table(_TRADES_SCHEMA, columns)


def _equity_table(result: BacktestResult) -> pa.Table:
    curve = result.equity_curve
    columns = {
        "timestamp": [p.timestamp for p in curve],
        "equity": [float(p.equity) for p in curve],
        "position": [float(p.position) for p in curve],
        "exposure": [p.exposure for p in curve],
    }
    return _typed_table(_EQUITY_SCHEMA, columns)


def _typed_table(schema: pa.Schema, columns: dict[str, list[Any]]) -> pa.Table:
    arrays = [pa.array(columns[field.name], type=field.type) for field in schema]
    return pa.Table.from_arrays(arrays, schema=schema)
