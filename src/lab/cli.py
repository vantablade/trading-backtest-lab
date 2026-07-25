"""Minimal ``lab`` CLI stub.

Wired as a console script so ``uv run lab`` resolves, but the subcommands are
not implemented until a strategy exists. See CLAUDE.md "Running things".
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lab", description="Systematic trading research lab.")
    sub = parser.add_subparsers(dest="command")

    bt = sub.add_parser("backtest", help="Run a backtest for a strategy config.")
    bt.add_argument("--config", required=True)
    bt.add_argument("--split", default="validate")

    rp = sub.add_parser("report", help="Report metrics for a completed run.")
    rp.add_argument("--run", required=True)

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0

    print(
        f"`lab {args.command}` is not implemented yet: the engine is scaffolded "
        f"and its no-lookahead tests pass, but no strategy has been written."
    )
    return 1
