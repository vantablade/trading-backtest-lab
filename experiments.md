# Experiments — lab notebook

Append-only. Read this at the start of every session (CLAUDE.md). One entry per
backtest run, using the protocol in CLAUDE.md.

## run_0001 — sma_cross on train
**Hypothesis:** None. This is a plumbing test, not an edge. A moving-average
crossover on a liquid asset is one of the most picked-over patterns in
existence; any edge it once had is long arbitraged out. I expect no real alpha.
**Change:** First evaluated run of a position-taking strategy through the full
pipeline (fast/slow SMA cross).
**Prediction:** After costs, roughly break-even to modestly negative — the
strategy churns in and out and pays fees/slippage for the privilege, landing
at or below the `flat` baseline. Sharpe near zero or negative. Specifically
NOT a clean upward equity curve or a Sharpe above ~1; if I see that, I suspect
a leak before I believe the edge.
**Result:** <fill after run>
**Verdict:** <fill after run>
**Notes:** <fill after run>
