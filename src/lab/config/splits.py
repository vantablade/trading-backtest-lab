"""Train / validate / holdout date ranges, loaded from ``data/splits.yaml``.

Timestamps are interpreted as UTC (the file declares them with a ``Z`` suffix);
naive values are treated as UTC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml


class Split(StrEnum):
    """Which data split a run is on."""

    TRAIN = "train"
    VALIDATE = "validate"
    HOLDOUT = "holdout"


@dataclass(frozen=True)
class SplitRange:
    """An inclusive ``[start, end]`` UTC date range for one split."""

    start: datetime
    end: datetime


@dataclass(frozen=True)
class Splits:
    train: SplitRange
    validate: SplitRange
    holdout: SplitRange

    def range_for(self, split: Split) -> SplitRange:
        return {
            Split.TRAIN: self.train,
            Split.VALIDATE: self.validate,
            Split.HOLDOUT: self.holdout,
        }[split]


def load_splits(path: str | Path) -> Splits:
    """Read ``splits.yaml`` into typed, timezone-aware ranges."""
    raw: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    def rng(name: str) -> SplitRange:
        section = raw[name]
        return SplitRange(_to_utc(section["start"]), _to_utc(section["end"]))

    return Splits(train=rng("train"), validate=rng("validate"), holdout=rng("holdout"))


def _to_utc(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise ValueError(f"split timestamp must be a datetime or ISO 8601 string, got {value!r}")
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
