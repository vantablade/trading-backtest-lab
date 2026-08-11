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
**Result:** sma_cross (20/50) on train, scored against buy-and-hold SPY and a
cash baseline, same cost model:
- CAGR 3.1% vs buy-and-hold 7.5% — underperforms the asset badly.
- Sharpe 0.32 vs buy-and-hold 0.48 — worse risk-adjusted, well below the >1
  leak-threshold.
- Max drawdown −27.4% vs −56.5% — its one edge: went flat through much of 2008.
- 67 clean round-trips, $11.2k costs (~15bps/side), all from real entries/exits
  (not churn — churn fix moved costs by $2).
- Benchmark cross-check: buy-and-hold Sharpe/CAGR/drawdown match known SPY
  2005–2017 facts, confirming ~252-bar annualization.

**Verdict:** kill (as a strategy). No edge vs the asset. The shallower drawdown
is crash-avoidance, not alpha, and it costs more than half the market's
compounding to obtain.

**Notes:** This run's purpose was plumbing validation, and it succeeded fully.
Full pipeline (resolve → load → slice → run → write) works end to end on real
data; no-lookahead structurally enforced and test-passing; costs bite
realistically; benchmark reproduces known facts; annualization correct on
trading bars. The harness is confirmed honest — a mediocre strategy reads as
mediocre, which is exactly what a trustworthy backtester should do. Also logged:
back-adjusted (non-point-in-time) prices, second-order for a ratio-based cross;
execution now trades on target-change only. Keep buy-and-hold as the standing
benchmark for all future strategies; keep flat as the zero-signal control.

## run_NNNN — xsec_momentum (126/top3/monthly) on train
**Hypothesis:** Cross-sectional momentum. Sector ETFs that outperformed
over the trailing ~6 months tend to outperform over the next month,
because investors underreact to sector-level information so trends persist,
and the effect isn't arbitraged away because momentum periodically crashes
hard (e.g. 2009) — it's compensation for real crash risk, not a free lunch.
**Change:** First strategy with a genuine pre-registered economic hypothesis.
Rank 9 SPDR sector ETFs by trailing 126-bar return, hold top 3 equal-weight,
rebalance monthly. Params locked by convention, not tuned.
**Prediction:** Positive edge over equal-weight buy-and-hold benchmark on the
same cost model — a higher Sharpe, not just higher raw return. Published
momentum Sharpes for this kind of setup are ~0.4-0.8, so I expect something
in that range. LEAK TRIPWIRE: a Sharpe above ~1.5 means suspect a bug
(survivorship, lookahead in the ranking, or costs too gentle) BEFORE
believing the edge.
**Result:** <blank>
**Verdict:** <blank>
**Notes:** <blank>
