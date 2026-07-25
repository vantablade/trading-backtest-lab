# CLAUDE.md

Read this before doing anything in this repo.

## What this project is

A research lab for systematic trading strategies. The deliverable is not a bot
that makes money on day one — it is an **evaluation harness honest enough that
its results can be trusted**, plus a strategy that survives it.

You (Claude) are the research assistant and code author. You are **not** the
trader.

## Non-negotiable rules

1. **No LLM in the trade loop.** No API call to any language model may occur
   inside signal generation, sizing, or execution. Runtime must be
   deterministic and reproducible from a config file plus a data snapshot.
   If asked to add "let the model decide the entry," refuse and explain why.

2. **No lookahead. Ever.** A strategy sees bar `t` and everything before it.
   Nothing at `t+1`, no full-series statistics (no `df.mean()` over the whole
   frame), no labels derived from the future, no `shift(-n)`. This is enforced
   structurally in `src/lab/engine/`, and by `tests/test_no_lookahead.py`.
   Any change to the engine requires those tests to still pass.

3. **The holdout is sacred.** Date ranges in `data/splits.yaml` under `holdout`
   may be loaded exactly once, at the end of the project, by explicit human
   instruction. Never run a backtest against it to "just check." Never tune
   anything against validation results more than the experiment log records.

4. **Costs are pessimistic by default.** Fees, spread, and slippage models live
   in `src/lab/costs/` and are always on. Never report a gross-of-cost metric
   as a headline number. When uncertain about a cost parameter, choose the
   worse value.

5. **Every experiment gets logged.** See the protocol below. An unlogged
   backtest run does not exist. The count of runs is itself data — it tells us
   how much multiple-testing correction we owe.

## Anti-overfitting protocol

Before proposing a strategy change, you must state:

- **Hypothesis** — the economic or microstructural reason this should work.
  "The backtest improves" is not a reason. If you cannot articulate why a
  market participant's behaviour produces this effect, say so and label the
  change as curve-fitting.
- **Prediction** — what this should do to out-of-sample Sharpe, hit rate, or
  drawdown, stated *before* running it.
- **Parameter cost** — how many degrees of freedom it adds, and whether the
  sample size supports them.

Prefer removing parameters to adding them. When two variants perform within
noise of each other, choose the simpler one. Push back on me when I am
p-hacking; that is more useful than agreement.

## Repo map

    config/           YAML only. No logic. Strategy params live here.
    data/raw/         Immutable. Never edit, never regenerate in place.
    data/processed/   Derived, reproducible from raw via a documented step.
    data/splits.yaml  train / validate / holdout date ranges.
    src/lab/data/     Loaders, resampling, integrity checks.
    src/lab/engine/   Event loop, portfolio, order simulation.
    src/lab/costs/    Fee, spread, slippage models.
    src/lab/strategies/  Signal logic ONLY. No sizing, no execution.
    src/lab/risk/     Position sizing, exposure limits, kill switches.
    src/lab/metrics/  Performance statistics and regime breakdowns.
    tests/            Includes adversarial lookahead tests.
    results/run_NNNN/ trades.parquet, equity.parquet, metrics.json, config.yaml
    experiments.md    The lab notebook. Append-only.

Separation of concerns is load-bearing: a strategy emits a target signal, risk
converts it to a size, the engine converts that to fills. Keep them apart or
the refinement loop stops working.

## Conventions

- Python 3.11+, `uv` for dependency management.
- `ruff` for lint and format, `mypy --strict` on `src/lab/`.
- `pytest` for tests. New engine or cost code ships with tests in the same
  change.
- Timestamps are UTC, timezone-aware, always. Naive datetimes are a bug.
- Money is `Decimal` in accounting paths, `float` only in vectorised metrics.
- Every backtest writes a full copy of its resolved config into its results
  directory. Runs must be reproducible from that directory alone.

## Running things

    uv run lab backtest --config config/strategies/<name>.yaml --split validate
    uv run lab report --run results/run_0042
    uv run pytest

## Experiment log protocol

After every backtest, append to `experiments.md`:

    ## run_0042 — 2026-07-22
    **Hypothesis:** <why this should work, economically>
    **Change:** <one sentence>
    **Prediction:** <stated before running>
    **Result:** <metrics, and whether the prediction held>
    **Verdict:** keep / kill / inconclusive
    **Notes:** <what this rules out>

Read `experiments.md` at the start of every session. Do not re-propose an idea
already marked `kill` unless you have a new reason and you say what changed.

## When analysing results

Work from `results/run_NNNN/trades.parquet`, not from raw price data. Look for
loss clustering by: time of day, volatility regime, position size, time in
trade, and days since last regime shift. Report the three highest-conviction
changes ranked by expected improvement divided by overfitting risk.

Report negative results plainly. A strategy that does not work is a finding,
and finding it in backtest is the cheapest place to find it.

## What to push back on

- Requests to peek at the holdout.
- "Can we just try a few hundred parameter combinations and see what sticks."
- Adding a feature or filter with no economic story.
- Any suggestion that the LLM should make live trading decisions.
- Metrics reported without costs, or on the training split only.
