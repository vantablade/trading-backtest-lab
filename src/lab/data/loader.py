"""Load immutable raw OHLCV bars from CSV into a validated ``OHLCVFrame``.

Raw data is never mutated. This reads the file's bytes, fingerprints them
(sha256, so a run can pin its exact data snapshot), parses and validates, and
returns the engine's :class:`~lab.engine.OHLCVFrame` together with an
:class:`~lab.data.integrity.IntegrityReport`.

CSV keeps the loader dependency-light (stdlib + numpy) and diff-able; a parquet
loader can slot in behind :class:`LoadResult` when pyarrow is available.

Expected CSV schema (header required, case-insensitive, extra columns ignored)::

    timestamp,open,high,low,close,volume

``timestamp`` must be ISO 8601 with an explicit UTC designator or offset
(e.g. ``2024-01-01T00:00:00Z`` or ``...+00:00``). Naive timestamps are rejected
(naive datetimes are a bug); non-UTC offsets are normalised to UTC — the same
instant, canonical timezone.

Timestamps are assumed to label each bar's *open* (:class:`BarLabel.OPEN`, the
harness convention). Declare ``label=BarLabel.CLOSE`` for close-labeled data; the
loader records it faithfully and the engine then rejects the frame.

The bar ``interval`` is **required** and declared, not inferred. It is checked
against the data's modal spacing by the frame; a disagreement is a
:class:`DataIntegrityError`. Nothing here silently fills, drops, or coerces
data: interior blank lines and non-plain numbers (underscores, ``inf``/``nan``
spellings) are errors, not something quietly swallowed.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from ..engine import BarLabel, IntervalMismatchError, OHLCVFrame
from .integrity import (
    DataIntegrityError,
    IntegrityReport,
    check_ohlc_consistency,
    find_gaps,
)

_REQUIRED = ("timestamp", "open", "high", "low", "close", "volume")
_ZERO = timedelta(0)
_NONFINITE_SPELLINGS = frozenset({"inf", "infinity", "nan"})


@dataclass(frozen=True)
class LoadResult:
    """A validated frame plus the integrity report produced while loading it."""

    frame: OHLCVFrame
    report: IntegrityReport


def load_csv_bars(
    path: str | Path,
    *,
    interval: timedelta,
    label: BarLabel = BarLabel.OPEN,
    max_gap_report: int = 50,
) -> LoadResult:
    """Read and validate a CSV of OHLCV bars.

    ``interval`` is the declared bar spacing; it is recorded on the frame and
    checked against the modal observed spacing (a disagreement raises). ``label``
    declares which edge of its interval each timestamp names (default: the
    harness convention, :class:`BarLabel.OPEN`).

    Raises :class:`DataIntegrityError` on any fatal problem: missing columns,
    unparseable or non-plain numbers, naive timestamps, out-of-order or duplicate
    bars, impossible OHLC relationships, interior blank lines, or an interval
    that disagrees with the data. Trailing blank lines are tolerated. Gaps in the
    time grid are reported in the result, not raised.
    """
    p = Path(path)
    raw = p.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()

    raw_rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    last_content = max((i for i, r in enumerate(raw_rows) if _has_content(r)), default=-1)
    if last_content == -1:
        raise DataIntegrityError(f"{p}: file is empty")
    for i in range(last_content):
        if not _has_content(raw_rows[i]):
            raise DataIntegrityError(
                f"{p}: line {i + 1} is blank; interior blank lines are not allowed "
                f"(trailing blank lines are fine)"
            )
    rows = raw_rows[: last_content + 1]

    header = [h.strip().lower() for h in rows[0]]
    missing = [name for name in _REQUIRED if name not in header]
    if missing:
        raise DataIntegrityError(f"{p}: missing required column(s): {', '.join(missing)}")
    col = {name: header.index(name) for name in _REQUIRED}

    data_rows = rows[1:]
    if not data_rows:
        raise DataIntegrityError(f"{p}: no data rows")

    n = len(data_rows)
    ncols = len(header)
    timestamps: np.ndarray = np.empty(n, dtype=object)
    op = np.empty(n, dtype=np.float64)
    hi = np.empty(n, dtype=np.float64)
    lo = np.empty(n, dtype=np.float64)
    cl = np.empty(n, dtype=np.float64)
    vol = np.empty(n, dtype=np.float64)

    for i, row in enumerate(data_rows):
        rownum = i + 2  # 1-based; header is line 1
        if len(row) < ncols:
            raise DataIntegrityError(f"row {rownum}: expected {ncols} columns, got {len(row)}")
        timestamps[i] = _parse_ts(row[col["timestamp"]], rownum)
        op[i] = _parse_float(row[col["open"]], rownum, "open")
        hi[i] = _parse_float(row[col["high"]], rownum, "high")
        lo[i] = _parse_float(row[col["low"]], rownum, "low")
        cl[i] = _parse_float(row[col["close"]], rownum, "close")
        vol[i] = _parse_float(row[col["volume"]], rownum, "volume")

    _check_monotonic(timestamps)
    check_ohlc_consistency(op, hi, lo, cl, vol)

    try:
        frame = OHLCVFrame(
            timestamps=timestamps,
            open=op,
            high=hi,
            low=lo,
            close=cl,
            volume=vol,
            interval=interval,
            label=label,
        )
    except IntervalMismatchError as exc:
        raise DataIntegrityError(str(exc)) from exc

    gaps = find_gaps(timestamps, interval)
    report = IntegrityReport(
        source=str(p),
        sha256=sha,
        n_bars=n,
        start=timestamps[0],
        end=timestamps[-1],
        bar_interval=interval,
        n_gaps=len(gaps),
        gap_after=tuple(gaps[:max_gap_report]),
    )
    return LoadResult(frame=frame, report=report)


def _has_content(row: list[str]) -> bool:
    return any(cell.strip() for cell in row)


def _parse_ts(value: str, rownum: int) -> datetime:
    try:
        dt = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise DataIntegrityError(
            f"row {rownum}: cannot parse timestamp {value!r} as ISO 8601"
        ) from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise DataIntegrityError(
            f"row {rownum}: timestamp {value!r} is naive; an explicit UTC offset "
            f"is required (naive datetimes are a bug)"
        )
    if dt.utcoffset() != _ZERO:
        dt = dt.astimezone(UTC)
    return dt


def _parse_float(value: str, rownum: int, column: str) -> float:
    s = value.strip()
    if "_" in s:
        raise DataIntegrityError(
            f"row {rownum}: column {column!r} value {value!r} contains an underscore; "
            f"write the number as plain digits"
        )
    if s.lower().lstrip("+-") in _NONFINITE_SPELLINGS:
        raise DataIntegrityError(
            f"row {rownum}: column {column!r} value {value!r} is not a finite number"
        )
    try:
        v = float(s)
    except ValueError as exc:
        raise DataIntegrityError(
            f"row {rownum}: column {column!r} value {value!r} is not a number"
        ) from exc
    if not math.isfinite(v):  # backstop, e.g. overflow like 1e999 -> inf
        raise DataIntegrityError(f"row {rownum}: column {column!r} value {value!r} is not finite")
    return v


def _check_monotonic(timestamps: np.ndarray) -> None:
    for i in range(1, len(timestamps)):
        if timestamps[i] == timestamps[i - 1]:
            raise DataIntegrityError(
                f"row {i + 2}: duplicate timestamp {timestamps[i].isoformat()}"
            )
        if timestamps[i] < timestamps[i - 1]:
            raise DataIntegrityError(
                f"row {i + 2}: timestamp {timestamps[i].isoformat()} is out of order "
                f"(before previous {timestamps[i - 1].isoformat()})"
            )
