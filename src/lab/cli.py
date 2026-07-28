"""The ``lab`` CLI. ``backtest`` runs the full pipeline from a config file."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from .config import ConfigError, HoldoutError, Split
from .data import DataIntegrityError
from .pipeline import run_backtest_from_config


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lab", description="Systematic trading research lab.")
    sub = parser.add_subparsers(dest="command")

    bt = sub.add_parser("backtest", help="Run a backtest for a strategy config.")
    bt.add_argument("--config", required=True, help="Path to the strategy config YAML.")
    bt.add_argument(
        "--split",
        required=True,
        choices=[s.value for s in Split],
        help="Which data split to run on. A run must declare its split.",
    )
    bt.add_argument(
        "--allow-holdout",
        action="store_true",
        help="Explicit opt-in required to load the sacred holdout split.",
    )

    rp = sub.add_parser("report", help="Report metrics for a completed run.")
    rp.add_argument("--run", required=True)

    args = parser.parse_args(argv)

    if args.command == "backtest":
        return _backtest(args)
    if args.command == "report":
        print("`lab report` is not implemented yet.", file=sys.stderr)
        return 1

    parser.print_help()
    return 0


def _backtest(args: argparse.Namespace) -> int:
    try:
        run = run_backtest_from_config(args.config, args.split, allow_holdout=args.allow_holdout)
    except HoldoutError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (ConfigError, DataIntegrityError, FileNotFoundError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {run}")
    return 0
