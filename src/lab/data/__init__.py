"""Data layer: loaders and integrity checks.

Produces the immutable :class:`lab.engine.OHLCVFrame` the engine consumes, from
immutable inputs under ``data/raw/``. Loaders read but never write raw data,
fingerprint it for reproducibility, and fail loudly at the edge on any integrity
violation rather than let a backtest go silently wrong.

The engine core is numpy-only, so the CSV loader is too; a parquet loader can be
added behind :class:`LoadResult` when pyarrow is loadable.
"""

from .integrity import (
    DataIntegrityError,
    IntegrityReport,
    check_ohlc_consistency,
    find_gaps,
)
from .loader import LoadResult, load_csv_bars

__all__ = [
    "DataIntegrityError",
    "IntegrityReport",
    "LoadResult",
    "check_ohlc_consistency",
    "find_gaps",
    "load_csv_bars",
]
