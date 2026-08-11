"""One-off: convert Stooq daily bars for the 9 SPDR US sector ETFs to the loader schema.

For each ticker it reads ``C:/Users/maksi/Downloads/<ticker>_us_d.csv`` (Stooq:
``Date,Open,High,Low,Close,Volume``; dates ``YYYY-MM-DD``), writes
``data/raw/<ticker>_1d.csv`` (``timestamp,open,high,low,close,volume``; ISO 8601
midnight UTC; sorted ascending), and loads it through
``load_csv_bars(interval=1 day)`` printing its IntegrityReport. Numeric values are
copied verbatim — nothing is dropped, filled, or rounded.

Run from the project root:  uv run python scripts/prepare_sector_etfs.py
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path

from lab.data import load_csv_bars

TICKERS = ["xlb", "xle", "xlf", "xli", "xlk", "xlp", "xlu", "xlv", "xly"]
SRC_DIR = Path(r"C:\Users\maksi\Downloads")
DST_DIR = Path("data/raw")
OUT_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


def _convert(src: Path, dst: Path) -> int:
    with src.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header = {name.strip().lower(): name for name in reader.fieldnames or []}
        missing = [c for c in ("date", "open", "high", "low", "close", "volume") if c not in header]
        if missing:
            raise SystemExit(f"{src.name}: missing column(s) {missing}; found {reader.fieldnames}")

        rows: list[dict[str, str]] = []
        for line_no, row in enumerate(reader, start=2):
            raw_date = row[header["date"]].strip()
            try:
                dt = datetime.strptime(raw_date, "%Y-%m-%d")
            except ValueError as exc:
                raise SystemExit(
                    f"{src.name} line {line_no}: bad date {raw_date!r}: {exc}"
                ) from exc
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

    rows.sort(key=lambda r: r["timestamp"])
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    missing: list[str] = []
    for ticker in TICKERS:
        src = SRC_DIR / f"{ticker}_us_d.csv"
        dst = DST_DIR / f"{ticker}_1d.csv"
        if not src.exists():
            missing.append(src.name)
            print(f"[{ticker.upper():4}] MISSING {src} - download from Stooq first.")
            continue
        n = _convert(src, dst)
        report = load_csv_bars(dst, interval=timedelta(days=1)).report
        print(f"[{ticker.upper():4}] {n:5} rows -> {dst}")
        print(f"        {report.summary()}")

    print()
    if missing:
        print(f"{len(missing)} file(s) not found in {SRC_DIR}: {', '.join(missing)}")
        print("Download them, then re-run this script.")
    else:
        print(f"All {len(TICKERS)} sector ETFs prepared and loaded cleanly.")


if __name__ == "__main__":
    main()
