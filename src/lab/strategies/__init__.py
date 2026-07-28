"""Strategy signal logic ONLY. No sizing, no execution, no costs.

A strategy emits a target signal from a :class:`lab.engine.MarketView` and sees
bar ``t`` and everything before it — never the future (the engine enforces that
structurally). Strategies register themselves by name so a config can select
one: ``flat`` (a runnable null control) and ``sma_cross`` (a fast/slow
moving-average crossover). New strategies just register the same way.
"""

from . import flat, sma_cross  # noqa: F401  (imports register the strategies)
from .registry import available, get_strategy, register

__all__ = ["available", "get_strategy", "register"]
