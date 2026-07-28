"""Config layer: merge base + strategy YAML, enforce split rules, hash the result."""

from .resolver import (
    ConfigError,
    HoldoutError,
    ResolvedConfig,
    deep_merge,
    hash_config,
    parse_interval,
    resolve_config,
)
from .splits import Split, SplitRange, Splits, load_splits

__all__ = [
    "ConfigError",
    "HoldoutError",
    "ResolvedConfig",
    "Split",
    "SplitRange",
    "Splits",
    "deep_merge",
    "hash_config",
    "load_splits",
    "parse_interval",
    "resolve_config",
]
