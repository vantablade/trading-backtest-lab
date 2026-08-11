"""A name -> strategy registry so configs can select a strategy by name."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ..engine import PanelStrategy, Strategy

AnyStrategy = Strategy | PanelStrategy  # single-asset or cross-sectional
_REGISTRY: dict[str, Callable[..., AnyStrategy]] = {}


def register(name: str) -> Callable[[Callable[..., AnyStrategy]], Callable[..., AnyStrategy]]:
    """Class decorator that registers a strategy under ``name``."""

    def decorator(factory: Callable[..., AnyStrategy]) -> Callable[..., AnyStrategy]:
        if name in _REGISTRY:
            raise ValueError(f"strategy {name!r} is already registered")
        _REGISTRY[name] = factory
        return factory

    return decorator


def get_strategy(name: str, params: Mapping[str, Any] | None = None) -> AnyStrategy:
    """Build the registered strategy ``name`` with ``params`` as constructor kwargs."""
    try:
        factory = _REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown strategy {name!r}; registered: {available()}") from None
    return factory(**dict(params or {}))


def available() -> list[str]:
    return sorted(_REGISTRY)
