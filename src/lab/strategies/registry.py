"""A name -> strategy registry so configs can select a strategy by name."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ..engine import Strategy

_REGISTRY: dict[str, Callable[..., Strategy]] = {}


def register(name: str) -> Callable[[Callable[..., Strategy]], Callable[..., Strategy]]:
    """Class decorator that registers a strategy under ``name``."""

    def decorator(factory: Callable[..., Strategy]) -> Callable[..., Strategy]:
        if name in _REGISTRY:
            raise ValueError(f"strategy {name!r} is already registered")
        _REGISTRY[name] = factory
        return factory

    return decorator


def get_strategy(name: str, params: Mapping[str, Any] | None = None) -> Strategy:
    """Build the registered strategy ``name`` with ``params`` as constructor kwargs."""
    try:
        factory = _REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown strategy {name!r}; registered: {available()}") from None
    return factory(**dict(params or {}))


def available() -> list[str]:
    return sorted(_REGISTRY)
