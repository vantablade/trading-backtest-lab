"""Metrics layer: performance statistics and regime breakdowns.

Metrics are computed from a run's outputs (fills and equity curve), never from
raw price data, and are always net of costs (CLAUDE.md rule 4). The set is thin
for now and will grow.
"""

from .summary import compute_metrics

__all__ = ["compute_metrics"]
