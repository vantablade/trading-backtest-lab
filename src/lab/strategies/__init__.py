"""Strategy signal logic ONLY. No sizing, no execution, no costs.

Intentionally empty. The harness (engine + adversarial no-lookahead tests) is
built and trusted first; a strategy that emits a target signal from a
``lab.engine.MarketView`` comes only after that. A strategy sees bar ``t`` and
everything before it — never ``t+1``. The engine enforces that structurally.
"""
