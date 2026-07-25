"""Structural no-lookahead enforcement (CLAUDE.md rule 2).

A strategy sees bar ``t`` and everything before it — never ``t+1``, never a
statistic computed over the whole frame, never a slice that reaches past the
present. That guarantee is enforced here, not by convention:

* :class:`BoundedSeries` wraps a full price channel but exposes only bars
  ``0..cursor``. Any read that resolves at or beyond ``cursor + 1`` raises
  :class:`LookaheadError`. Aggregations (``mean``, ``max`` …), materialisation
  (``to_numpy``, ``np.asarray``) and iteration all operate on the visible
  window only, so there is no escape hatch to the future.
* :class:`MarketView` hands a strategy the bounded channels for a single bar.
  A fresh view is built for each bar, so a stashed old view stays frozen at its
  own cursor.

The full underlying data is deliberately kept private. Enforcement covers the
public data API a strategy is meant to use; reaching into ``view._frame`` by
hand is cheating and out of scope — as it is in any Python sandbox.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import numpy.typing as npt

from .bars import OHLCVFrame


class LookaheadError(RuntimeError):
    """Raised when strategy code tries to read a bar at or beyond the present."""


class BoundedSeries:
    """A price channel exposing only bars up to and including ``cursor``.

    Negative indices are relative to the current bar (``[-1]`` is now,
    ``[-2]`` the previous bar). Any positive index, or any slice bound, that
    reaches past the current bar raises :class:`LookaheadError`. Indices before
    the start of history raise :class:`IndexError`, as ordinary sequences do.
    """

    __slots__ = ("_cursor", "_full", "_name")

    def __init__(self, full: npt.NDArray[Any], cursor: int, name: str) -> None:
        self._full = full
        self._cursor = cursor
        self._name = name

    def _visible(self) -> npt.NDArray[Any]:
        return self._full[: self._cursor + 1]

    def __len__(self) -> int:
        return self._cursor + 1

    def _resolve_int(self, i: int) -> int:
        n_vis = self._cursor + 1
        j = i + n_vis if i < 0 else i
        if j < 0:
            raise IndexError(f"{self._name}[{i}]: before the start of available history")
        if j > self._cursor:
            raise LookaheadError(
                f"{self._name}[{i}] reads bar {j} at/beyond the current bar "
                f"{self._cursor}; future data is not available at decision time"
            )
        return j

    def _check_slice(self, sl: slice) -> None:
        n_vis = self._cursor + 1
        if sl.start is not None:
            start = sl.start + n_vis if sl.start < 0 else sl.start
            if start > self._cursor:
                raise LookaheadError(
                    f"{self._name}[{sl.start}:...] starts beyond the current bar "
                    f"{self._cursor}; future data is not available at decision time"
                )
        if sl.stop is not None:
            stop = sl.stop + n_vis if sl.stop < 0 else sl.stop
            if stop > n_vis:
                raise LookaheadError(
                    f"{self._name}[...:{sl.stop}] stops beyond the current bar "
                    f"{self._cursor}; future data is not available at decision time"
                )

    def __getitem__(self, key: int | slice) -> Any:
        if isinstance(key, slice):
            self._check_slice(key)
            return self._visible()[key]
        if isinstance(key, (int, np.integer)):
            return self._full[self._resolve_int(int(key))]
        raise TypeError(f"{self._name} indices must be int or slice, not {type(key)!r}")

    # --- aggregation / materialisation: all bounded to the visible window ---
    #
    # These accept numpy's reduction kwargs (axis, out, keepdims, ...) and
    # delegate to the visible slice, so both ``view.close.mean()`` and
    # ``np.mean(view.close)`` stay bounded — numpy dispatches its free
    # functions to these methods.

    def mean(self, *args: Any, **kwargs: Any) -> Any:
        return self._visible().mean(*args, **kwargs)

    def std(self, *args: Any, **kwargs: Any) -> Any:
        return self._visible().std(*args, **kwargs)

    def sum(self, *args: Any, **kwargs: Any) -> Any:
        return self._visible().sum(*args, **kwargs)

    def max(self, *args: Any, **kwargs: Any) -> Any:
        return self._visible().max(*args, **kwargs)

    def min(self, *args: Any, **kwargs: Any) -> Any:
        return self._visible().min(*args, **kwargs)

    def to_numpy(self) -> npt.NDArray[Any]:
        # A copy, so callers cannot reach the future through ``arr.base``.
        return np.array(self._visible())

    @property
    def values(self) -> npt.NDArray[Any]:
        return self.to_numpy()

    def __array__(self, dtype: Any = None) -> npt.NDArray[Any]:
        # Bounds np.asarray / np.mean / np.max(view.channel) to the visible window.
        return np.array(self._visible(), dtype=dtype)

    def __iter__(self) -> Any:
        return iter(self._visible())

    def __repr__(self) -> str:
        return f"BoundedSeries({self._name!r}, up to bar {self._cursor})"


class MarketView:
    """Everything a strategy is allowed to know at a single bar.

    A strategy receives a fresh view per bar and returns a signal from it. The
    channels are :class:`BoundedSeries`, so the strategy physically cannot read
    past the current bar through the public API.
    """

    __slots__ = ("_cursor", "_frame")

    def __init__(self, frame: OHLCVFrame, cursor: int) -> None:
        if not 0 <= cursor < len(frame):
            raise IndexError(f"cursor {cursor} out of range for {len(frame)} bars")
        self._frame = frame
        self._cursor = cursor

    @property
    def i(self) -> int:
        """Integer position of the current bar (elapsed time, not remaining)."""
        return self._cursor

    @property
    def now(self) -> datetime:
        """Timestamp of the current bar (timezone-aware UTC)."""
        return self._frame.timestamps[self._cursor]

    @property
    def open(self) -> BoundedSeries:
        return BoundedSeries(self._frame.open, self._cursor, "open")

    @property
    def high(self) -> BoundedSeries:
        return BoundedSeries(self._frame.high, self._cursor, "high")

    @property
    def low(self) -> BoundedSeries:
        return BoundedSeries(self._frame.low, self._cursor, "low")

    @property
    def close(self) -> BoundedSeries:
        return BoundedSeries(self._frame.close, self._cursor, "close")

    @property
    def volume(self) -> BoundedSeries:
        return BoundedSeries(self._frame.volume, self._cursor, "volume")

    @property
    def timestamps(self) -> BoundedSeries:
        return BoundedSeries(self._frame.timestamps, self._cursor, "timestamps")

    def __len__(self) -> int:
        return self._cursor + 1

    def __repr__(self) -> str:
        return f"MarketView(bar {self._cursor}, now={self.now.isoformat()})"
