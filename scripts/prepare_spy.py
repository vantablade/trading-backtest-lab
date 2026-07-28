"""One-off: convert a Stooq daily SPY export to the loader's CSV schema.

Reads the Stooq file (``Date,Open,High,Low,Close,Volume``; dates ``YYYY-MM-DD``),
renames columns to ``timestamp,open,high,low,close,volume``, stamps each date as
ISO 8601 midnight UTC (``YYYY-MM-DDT00:00:00Z``), sorts ascending by timestamp,
and writes ``data/raw/spy_1d.csv``. Numeric values are copied verbatim — nothing
is dropped, filled, or rounded.

Run from the project root:  uv run python scripts/prepare_spy.py
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

SRC = Path(r"C:\Users\maksi\Downloads\spy_us_d.csv")
DST = Path("data/raw/spy_1d.csv")
OUT_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
SRC_FIELDS = {  # our field -> Stooq column name (matched case-insensitively)
    "timestamp": "date",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
}


def main() -> None:
    with SRC.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header = {name.strip().lower(): name for name in reader.fieldnames or []}
        missing = [want for want in SRC_FIELDS.values() if want not in header]
        if missing:
            raise SystemExit(f"source missing column(s) {missing}; found {reader.fieldnames}")

        rows: list[dict[str, str]] = []
        for line_no, row in enumerate(reader, start=2):  # header is line 1
            raw_date = row[header["date"]].strip()
            try:
                dt = datetime.strptime(raw_date, "%Y-%m-%d")
            except ValueError as exc:
                raise SystemExit(f"line {line_no}: cannot parse date {raw_date!r}: {exc}") from exc
            rows.append(
                {
                    "timestamp": dt.strftime("%Y-%m-%dT00:00:00Z"),
                    "open": row[header["open"]].strip(),
                    "high": row[header["high"]].strip(),
                    "low": row[header["low"]].strip(),
                    "close": row[header["close"]].strip(),
                    "volume": row[header["volume"]].strip(),
                }
            )

    rows.sort(key=lambda r: r["timestamp"])  # ISO 8601 sorts chronologically

    DST.parent.mkdir(parents=True, exist_ok=True)
    with DST.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {len(rows)} rows to {DST}")
    print(f"first: {rows[0]['timestamp']}  last: {rows[-1]['timestamp']}")


if __name__ == "__main__":
    main()
