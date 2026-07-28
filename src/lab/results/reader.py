"""Read a run directory back — the inverse of :func:`lab.results.write_run`.

Everything comes from the directory alone, so a persisted run is self-contained.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import yaml


@dataclass(frozen=True)
class RunArtifacts:
    """Everything written for a run, read back."""

    path: Path
    trades: list[dict[str, Any]]
    equity: list[dict[str, Any]]
    metrics: dict[str, Any]
    config: dict[str, Any]
    manifest: dict[str, Any]


def read_run(run_dir: str | Path) -> RunArtifacts:
    """Load all artifacts from ``run_dir`` (e.g. ``results/run_0001``)."""
    path = Path(run_dir)
    return RunArtifacts(
        path=path,
        trades=pq.read_table(path / "trades.parquet").to_pylist(),
        equity=pq.read_table(path / "equity.parquet").to_pylist(),
        metrics=json.loads((path / "metrics.json").read_text(encoding="utf-8")),
        config=yaml.safe_load((path / "config.yaml").read_text(encoding="utf-8")),
        manifest=json.loads((path / "manifest.json").read_text(encoding="utf-8")),
    )
