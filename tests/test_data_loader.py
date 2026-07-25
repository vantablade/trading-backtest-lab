"""Tests for the raw CSV loader and its integrity checks.

Everything is written to ``tmp_path`` and read back, so ``data/raw/`` stays
immutable and empty. The loader is stdlib + numpy only, so these run under this
machine's Smart App Control policy (which blocks unsigned pandas/pyarrow DLLs).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lab.data import DataIntegrityError, LoadResult, load_csv_bars

HEADER = "timestamp,open,high,low,close,volume"
HOUR = timedelta(hours=1)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _good_rows(n: int = 5) -> list[str]:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    rows = []
    for k in range(n):
        t = base + timedelta(hours=k)
        close = 100.0 + k
        # low <= open, close <= high, volume >= 0
        rows.append(f"{_iso(t)},{close - 0.2},{close + 0.5},{close - 0.5},{close},{1000 + k}")
    return rows


def _write(tmp_path: Path, rows: list[str], header: str = HEADER) -> Path:
    p = tmp_path / "bars.csv"
    p.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return p


def _load(p: Path, **kwargs: object) -> LoadResult:
    """Load with the hourly interval these fixtures use, unless overridden."""
    kwargs.setdefault("interval", HOUR)
    return load_csv_bars(p, **kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Happy path                                                                  #
# --------------------------------------------------------------------------- #


def test_load_valid_csv(tmp_path: Path) -> None:
    result = _load(_write(tmp_path, _good_rows(5)))
    frame, report = result.frame, result.report

    assert len(frame) == 5
    assert frame.close[0] == 100.0
    assert frame.close[-1] == 104.0
    assert frame.timestamps[0] == datetime(2024, 1, 1, tzinfo=UTC)

    assert report.n_bars == 5
    assert report.bar_interval == HOUR
    assert report.n_gaps == 0
    assert len(report.sha256) == 64
    assert report.start == datetime(2024, 1, 1, tzinfo=UTC)
    assert report.end == datetime(2024, 1, 1, 4, tzinfo=UTC)


def test_extra_columns_are_ignored(tmp_path: Path) -> None:
    header = "symbol,timestamp,open,high,low,close,volume,note"
    rows = [f"BTCUSD,{r},x" for r in _good_rows(3)]
    result = _load(_write(tmp_path, rows, header=header))
    assert len(result.frame) == 3


def test_non_utc_offset_is_normalised(tmp_path: Path) -> None:
    # 02:00 at +02:00 is 00:00 UTC — same instant, canonical timezone.
    rows = [
        "2024-01-01T02:00:00+02:00,100,100.5,99.5,100,1000",
        "2024-01-01T03:00:00+02:00,100,100.5,99.5,100,1000",
    ]
    result = _load(_write(tmp_path, rows))
    assert result.frame.timestamps[0] == datetime(2024, 1, 1, 0, tzinfo=UTC)


def test_sha256_is_stable_and_content_sensitive(tmp_path: Path) -> None:
    p = _write(tmp_path, _good_rows(5))
    first = _load(p).report.sha256
    second = _load(p).report.sha256
    assert first == second

    changed = _load(_write(tmp_path, _good_rows(6))).report.sha256
    assert changed != first


# --------------------------------------------------------------------------- #
# Interval is declared and recorded, not inferred                             #
# --------------------------------------------------------------------------- #


def test_interval_declared_and_recorded(tmp_path: Path) -> None:
    result = load_csv_bars(_write(tmp_path, _good_rows(5)), interval=HOUR)
    assert result.frame.interval == HOUR
    assert result.report.bar_interval == HOUR


def test_declared_interval_mismatch_rejected(tmp_path: Path) -> None:
    # The data is hourly; declaring 30 minutes must fail rather than be trusted.
    with pytest.raises(DataIntegrityError, match="interval"):
        load_csv_bars(_write(tmp_path, _good_rows(5)), interval=timedelta(minutes=30))


# --------------------------------------------------------------------------- #
# Gaps are reported, not rejected                                             #
# --------------------------------------------------------------------------- #


def test_time_grid_gap_is_reported_not_fatal(tmp_path: Path) -> None:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    # Hours 0, 1, 3, 4 — hour 2 is missing.
    hours = [0, 1, 3, 4]
    rows = [
        f"{_iso(base + timedelta(hours=h))},{100 + h},{100.5 + h},{99.5 + h},{100 + h},1000"
        for h in hours
    ]
    result = _load(_write(tmp_path, rows))
    assert len(result.frame) == 4  # loads fine
    assert result.report.bar_interval == HOUR
    assert result.report.n_gaps == 1
    assert result.report.gap_after == (base + timedelta(hours=1),)


# --------------------------------------------------------------------------- #
# Blank-line handling: interior is fatal, trailing is tolerated               #
# --------------------------------------------------------------------------- #


def test_interior_blank_line_rejected(tmp_path: Path) -> None:
    good = _good_rows(3)
    p = tmp_path / "bars.csv"
    # HEADER=line1, good0=line2, blank=line3, good1=line4, good2=line5
    p.write_text("\n".join([HEADER, good[0], "", good[1], good[2]]) + "\n", encoding="utf-8")
    with pytest.raises(DataIntegrityError, match="line 3"):
        _load(p)


def test_trailing_blank_lines_tolerated(tmp_path: Path) -> None:
    good = _good_rows(3)
    p = tmp_path / "bars.csv"
    p.write_text("\n".join([HEADER, *good]) + "\n\n\n", encoding="utf-8")  # extra trailing blanks
    result = _load(p)
    assert len(result.frame) == 3


# --------------------------------------------------------------------------- #
# Numeric parsing is strict: no underscores, no inf/nan spellings             #
# --------------------------------------------------------------------------- #


def test_underscore_number_rejected(tmp_path: Path) -> None:
    rows = ["2024-01-01T00:00:00Z,1_000,1_000.5,999.5,1_000,1000"]
    with pytest.raises(DataIntegrityError, match="underscore"):
        _load(_write(tmp_path, rows))


@pytest.mark.parametrize(
    "value",
    ["inf", "Inf", "INF", "+inf", "-inf", "infinity", "Infinity", "nan", "NaN", "-nan"],
)
def test_inf_and_nan_spellings_rejected(tmp_path: Path, value: str) -> None:
    rows = [f"2024-01-01T00:00:00Z,100,{value},99.5,100,1000"]
    with pytest.raises(DataIntegrityError, match="finite"):
        _load(_write(tmp_path, rows))


def test_overflow_to_inf_rejected(tmp_path: Path) -> None:
    rows = ["2024-01-01T00:00:00Z,100,1e999,99.5,100,1000"]  # float('1e999') -> inf
    with pytest.raises(DataIntegrityError, match="finite"):
        _load(_write(tmp_path, rows))


def test_unparseable_number_rejected(tmp_path: Path) -> None:
    rows = ["2024-01-01T00:00:00Z,abc,100.5,99.5,100,1000"]
    with pytest.raises(DataIntegrityError, match="not a number"):
        _load(_write(tmp_path, rows))


# --------------------------------------------------------------------------- #
# Other fatal integrity violations                                            #
# --------------------------------------------------------------------------- #


def test_missing_column_raises(tmp_path: Path) -> None:
    header = "timestamp,open,high,low,close"  # no volume
    with pytest.raises(DataIntegrityError, match="missing required column"):
        _load(_write(tmp_path, _good_rows(3), header=header))


def test_empty_file_raises(tmp_path: Path) -> None:
    p = tmp_path / "empty.csv"
    p.write_text("", encoding="utf-8")
    with pytest.raises(DataIntegrityError, match="empty"):
        _load(p)


def test_header_only_raises(tmp_path: Path) -> None:
    with pytest.raises(DataIntegrityError, match="no data rows"):
        _load(_write(tmp_path, []))


def test_naive_timestamp_raises(tmp_path: Path) -> None:
    rows = ["2024-01-01T00:00:00,100,100.5,99.5,100,1000"]  # no Z / offset
    with pytest.raises(DataIntegrityError, match="naive"):
        _load(_write(tmp_path, rows))


def test_unparseable_timestamp_raises(tmp_path: Path) -> None:
    rows = ["not-a-timestamp,100,100.5,99.5,100,1000"]
    with pytest.raises(DataIntegrityError, match="ISO 8601"):
        _load(_write(tmp_path, rows))


def test_out_of_order_timestamp_raises(tmp_path: Path) -> None:
    rows = [
        "2024-01-01T01:00:00Z,100,100.5,99.5,100,1000",
        "2024-01-01T00:00:00Z,100,100.5,99.5,100,1000",  # earlier than previous
    ]
    with pytest.raises(DataIntegrityError, match="out of order"):
        _load(_write(tmp_path, rows))


def test_duplicate_timestamp_raises(tmp_path: Path) -> None:
    rows = [
        "2024-01-01T00:00:00Z,100,100.5,99.5,100,1000",
        "2024-01-01T00:00:00Z,100,100.5,99.5,100,1000",
    ]
    with pytest.raises(DataIntegrityError, match="duplicate"):
        _load(_write(tmp_path, rows))


def test_high_below_low_raises(tmp_path: Path) -> None:
    rows = ["2024-01-01T00:00:00Z,100,99,101,100,1000"]  # high 99 < low 101
    with pytest.raises(DataIntegrityError, match=r"low .* > high"):
        _load(_write(tmp_path, rows))


def test_close_outside_range_raises(tmp_path: Path) -> None:
    rows = ["2024-01-01T00:00:00Z,100,100.5,99.5,105,1000"]  # close 105 > high
    with pytest.raises(DataIntegrityError, match=r"close .* outside"):
        _load(_write(tmp_path, rows))


def test_negative_volume_raises(tmp_path: Path) -> None:
    rows = ["2024-01-01T00:00:00Z,100,100.5,99.5,100,-5"]
    with pytest.raises(DataIntegrityError, match="negative volume"):
        _load(_write(tmp_path, rows))
