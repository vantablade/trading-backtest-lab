# honest-backtest-lab

An evaluation harness for testing systematic trading hypotheses — built to be
honest enough to disprove its own ideas.

This is **not** a trading bot and not a money-making system. It is the thing you
need *before* one: a backtester rigorous enough that a negative result can be
trusted. Its job is to take a trading idea, subject it to realistic conditions,
and say plainly whether the idea survives. Usually it won't — and that is the
point.

## Why its results can be trusted

A backtest is only as valuable as it is honest. Five properties are built in
structurally, not left to the researcher's discipline:

- **No lookahead, enforced by construction.** A strategy sees bar `t` and
  everything before it — never the future. The market view hands out price
  series bounded at the current bar; any attempt to read ahead raises
  `LookaheadError`. The same guard applies, unchanged, to every asset inside a
  multi-asset panel. Adversarial and recording-view tests prove that strategies
  — including the cross-sectional ranker — never touch the current bar.
- **The holdout is sacred.** The final slice of history is sealed. A plain run
  cannot reach it: loading the holdout requires an explicit `--allow-holdout`
  flag, and the config resolver refuses otherwise. Nothing is ever tuned
  against it.
- **Costs are always on, and pessimistic.** Every fill pays fees, spread, and
  slippage. There is no gross-of-cost headline number — costs bite in every
  result the harness reports.
- **Benchmarks that reproduce known facts.** A strategy is scored against the
  right benchmark (buy-and-hold the asset, or an equal-weight basket), not
  against cash. Those benchmarks reproduce known market history — buy-and-hold
  SPY over 2005–2017 comes out at a Sharpe of ~0.48 with a ~57% drawdown through
  2008 — which is how we know the accounting and annualisation are correct.
- **Predictions are pre-registered.** Before every run, the hypothesis and a
  specific prediction — including a leak tripwire — are written into the lab
  notebook. Results are read against what was predicted, not rationalised after
  the fact. If a result looks too good, the tripwire says *suspect a bug before
  believing the edge*.

## Architecture

A backtest flows through four layers, each with a single job:

1. **Loader** (`src/lab/data`) — reads raw CSV bars, fingerprints the file
   (sha256), and validates hard: timezone-aware UTC timestamps, strictly
   increasing, sane OHLC, a declared bar interval checked against the data.
   Calendar gaps (weekends, holidays) are *reported, not filled*; malformed
   numbers are errors, not silently coerced.
2. **Config resolver** (`src/lab/config`) — merges a base config with a strategy
   config, enforces the train / validate / holdout split boundary, and stamps
   the result with a content hash so two runs are provably identical-or-not.
3. **Engine** (`src/lab/engine`) — an event-driven loop. A strategy emits a
   target signal; the portfolio turns it into fills at the *next* bar's open
   (never same-bar), trading only when the target changes. A parallel panel
   engine does the same across many aligned assets at once.
4. **Results writer** (`src/lab/results`) — writes each run atomically to
   `results/run_NNNN/`: trades and equity as parquet, a metrics summary, the
   fully-resolved config, and a manifest pinning the data by checksum and the
   code by git commit. A run is reproducible from its directory alone.

## Running a backtest

    uv run lab backtest --config config/strategies/<name>.yaml --split train

Raw data lives under `data/raw/` and is not committed — it is yours to supply;
the `scripts/` folder shows how the SPY and sector-ETF datasets were prepared
from source. `uv run pytest` exercises the whole harness, including the
no-lookahead guarantees.

## Findings

Two genuinely-motivated, pre-registered strategies have been put through the
harness. **Both were killed against their proper benchmarks:**

- **`sma_cross` — a 20/50 moving-average crossover on SPY (train).** Sharpe 0.32
  vs buy-and-hold's 0.48: lower risk-adjusted return *and* lower raw return. Its
  only edge was a shallower drawdown — crash-avoidance, not alpha — bought at
  less than half the market's compounding.
- **`xsec_momentum` — rank 9 sector ETFs, hold the top 3, rebalance monthly
  (train).** Sharpe 0.39 vs an equal-weight-basket benchmark's 0.51:
  underperformed on both risk-adjusted and raw terms, net of monthly rebalancing
  costs, with no crash protection.

Neither was a bug. In both cases the Sharpe was far *below* the leak tripwire,
the no-lookahead guarantees held, and survivorship was structurally absent —
honest misses, which is exactly what a trustworthy backtester should be willing
to report. Finding that an idea doesn't work, in backtest, is the cheapest place
to find it.

The complete lab notebook — every run's hypothesis, pre-registered prediction,
result, and verdict — is in **[experiments.md](experiments.md)**.
