# lab

A research lab for systematic trading strategies. The deliverable is an
evaluation harness honest enough that its results can be trusted, plus a
strategy that survives it. Read [CLAUDE.md](CLAUDE.md) before touching anything.

## Status

Scaffolded. The engine (`src/lab/engine/`) and its adversarial no-lookahead
tests (`tests/test_no_lookahead.py`) are in place. **No strategy has been
written yet** — that is deliberate. The harness comes first.

## Layout

See the repo map in [CLAUDE.md](CLAUDE.md). In short: strategies emit signals,
`risk/` sizes them, the `engine/` turns sizes into fills, `costs/` are always
on, `metrics/` scores the result.

## Running

    uv run pytest                 # includes the adversarial lookahead tests
    uv run ruff check src tests
    uv run mypy                   # strict, on src/lab

The `lab` CLI (`uv run lab ...`) is stubbed until a strategy exists.
