"""Cost models: fee, spread, slippage. Always on, pessimistic by default.

CLAUDE.md rule 4: costs are never optional and never optimistic. The engine
executes every fill through a ``CostModel``; if a caller does not supply one it
defaults to a pessimistic bps model, so a gross-of-cost number can never leak
out by accident.
"""

from .base import CostModel
from .simple import BpsCost, default_cost_model

__all__ = ["BpsCost", "CostModel", "default_cost_model"]
