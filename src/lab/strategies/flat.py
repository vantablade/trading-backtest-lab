"""The ``flat`` null control.

This is **not** a trading strategy — it never takes a position, has no thesis,
and makes no trades. It exists so the harness pipeline (load -> run -> write) can
run end-to-end before any real strategy exists, and as a zero-signal control to
compare future strategies against. Signal logic only, per CLAUDE.md.
"""

from __future__ import annotations

from ..engine import MarketView, Signal
from .registry import register


@register("flat")
class Flat:
    """Always flat: target weight 0 on every bar."""

    def on_bar(self, view: MarketView) -> Signal:
        return Signal(0.0)
