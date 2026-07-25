"""lab — an honest evaluation harness for systematic trading research.

The package is deliberately split so that no single layer can quietly cheat:

    data/       loads and checks bars
    engine/     event loop, market view, portfolio, order simulation
    costs/      fee / spread / slippage models — always on
    strategies/ signal logic ONLY (empty until the harness is trusted)
    risk/       position sizing, exposure limits, kill switches
    metrics/    performance statistics and regime breakdowns

See CLAUDE.md for the rules this structure enforces.
"""

__version__ = "0.0.1"
