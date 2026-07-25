# data/

- `raw/` — **immutable.** Never edit or regenerate in place. The only committed
  files here are `.gitkeep`; real datasets are loaded from here but not tracked
  (see `.gitignore`).
- `processed/` — derived, reproducible from `raw/` via a documented step.
- `splits.yaml` — train / validate / holdout date ranges. **The holdout is
  sacred** (see `CLAUDE.md`).

## Raw CSV schema

`lab.data.load_csv_bars` reads bars in this shape (header required,
case-insensitive, extra columns ignored):

    timestamp,open,high,low,close,volume
    2024-01-01T00:00:00Z,100.0,100.5,99.5,100.2,1000
    2024-01-01T01:00:00Z,100.2,100.9,100.1,100.7,1200

- `timestamp` — ISO 8601 with an explicit UTC designator (`Z`) or offset. Naive
  timestamps are rejected; non-UTC offsets are normalised to UTC.
- Bars must be strictly increasing in time, with no duplicates.
- Each bar must satisfy `low <= open, close <= high` and `volume >= 0`.

The loader returns the validated frame plus an `IntegrityReport` carrying a
sha256 of the raw bytes (so a run can pin its data snapshot), the inferred bar
interval, and any time-grid gaps. Gaps are reported, not rejected — real markets
have them.
