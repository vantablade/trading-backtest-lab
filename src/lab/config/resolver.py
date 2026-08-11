"""Resolve ``base.yaml`` + a strategy config into one config, with split rules.

The resolved config is the merged result plus the split (name + resolved range)
and a content hash of everything above. The hash makes two runs provably the
same-or-not: same inputs -> same hash. The holdout split can only be resolved
with an explicit opt-in flag — never from a config value, never by default.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from .splits import Split, SplitRange, load_splits


class ConfigError(ValueError):
    """Raised for a malformed or incomplete run configuration."""


class HoldoutError(RuntimeError):
    """Raised when a run would touch the holdout split without explicit opt-in."""


_INTERVAL_RE = re.compile(r"(\d+)([smhd])")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_interval(text: object) -> timedelta:
    """Parse ``'1h'`` / ``'5m'`` / ``'1d'`` / ``'30s'`` into a timedelta."""
    match = _INTERVAL_RE.fullmatch(str(text).strip())
    if not match:
        raise ConfigError(f"bad bar_interval {text!r}; expected e.g. '1h', '5m', '1d', '30s'")
    return timedelta(seconds=int(match.group(1)) * _UNIT_SECONDS[match.group(2)])


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` onto ``base`` (override wins on leaves)."""
    result = dict(base)
    for key, value in override.items():
        existing = result.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            result[key] = deep_merge(existing, value)
        else:
            result[key] = value
    return result


def hash_config(merged: dict[str, Any]) -> str:
    """A deterministic content hash of a resolved config (excluding the hash)."""
    payload = {k: v for k, v in merged.items() if k != "config_hash"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResolvedConfig:
    """The merged config plus its split and content hash, with typed accessors."""

    merged: dict[str, Any]
    split: Split
    split_range: SplitRange
    root: Path

    @property
    def config_hash(self) -> str:
        return self.merged["config_hash"]

    def is_multi_asset(self) -> bool:
        """True when the config names several assets (``data.sources``)."""
        return "sources" in self.merged["data"]

    def data_source(self) -> Path:
        data = self.merged["data"]
        if "source" not in data:
            raise ConfigError("data.source is required (set it in the strategy config)")
        return self.root / data["source"]

    def data_sources(self) -> dict[str, Path]:
        """Symbol -> path for a multi-asset config (``data.sources``)."""
        sources = self.merged["data"].get("sources")
        if not sources:
            raise ConfigError("data.sources is required for a multi-asset strategy")
        return {symbol: self.root / path for symbol, path in sources.items()}

    def bar_interval(self) -> timedelta:
        return parse_interval(self.merged["data"]["bar_interval"])

    def initial_cash(self) -> Decimal:
        return Decimal(str(self.merged["engine"]["initial_cash"]))

    def results_dir(self) -> Path:
        return self.root / self.merged["results_dir"]

    def strategy_name(self) -> str:
        return str(self.merged["strategy"]["name"])

    def strategy_params(self) -> dict[str, Any]:
        return dict(self.merged["strategy"].get("params") or {})

    def costs_config(self) -> dict[str, Any]:
        return dict(self.merged["costs"])


def resolve_config(
    strategy_path: str | Path,
    split: str | Split,
    *,
    root: str | Path,
    base_path: str | Path | None = None,
    allow_holdout: bool = False,
) -> ResolvedConfig:
    """Merge base + strategy config for ``split`` and stamp it with a hash.

    ``allow_holdout`` (set only by the ``--allow-holdout`` CLI flag, never from a
    config file) is required to resolve the holdout split; otherwise it raises.
    """
    root = Path(root)
    split = Split(split)
    if split is Split.HOLDOUT and not allow_holdout:
        raise HoldoutError(
            "Refusing to load the holdout split. The holdout is sacred (CLAUDE.md "
            "rule 3): load it exactly once, at the end of the project, by explicit "
            "human instruction. Pass --allow-holdout to override deliberately."
        )

    base_file = Path(base_path) if base_path is not None else root / "config" / "base.yaml"
    strategy_file = root / Path(strategy_path)
    base = yaml.safe_load(base_file.read_text(encoding="utf-8")) or {}
    strategy = yaml.safe_load(strategy_file.read_text(encoding="utf-8")) or {}
    if "split" in base or "split" in strategy:
        raise ConfigError("`split` may not be set in a config file; it comes from --split only")

    merged = deep_merge(base, strategy)
    splits = load_splits(root / merged["data"]["splits"])
    split_range = splits.range_for(split)
    merged["split"] = {
        "name": split.value,
        "start": split_range.start.isoformat(),
        "end": split_range.end.isoformat(),
    }
    merged["config_hash"] = hash_config(merged)
    return ResolvedConfig(merged=merged, split=split, split_range=split_range, root=root)
