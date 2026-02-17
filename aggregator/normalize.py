"""
aggregator.normalize
=====================
Null-safe math helpers used throughout the aggregator and scoring
engine.  Every function gracefully handles ``None``, empty lists as
inputs so callers never need to pre-check.

All functions are pure and stateless.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Union

Number = Union[int, float]

NR_SENTINEL = "N/R"


def is_nr(value: Any) -> bool:
    """Return ``True`` if *value* is the "N/R" sentinel."""
    return value == NR_SENTINEL


# ---------------------------------------------------------------------------
# Null-safe accessors
# ---------------------------------------------------------------------------


def get(obj: Optional[Dict[str, Any]], *keys: str, default: Any = None) -> Any:
    """Deeply get a nested value from a dict, returning *default* on any miss.

    >>> get({"a": {"b": 3}}, "a", "b")
    3
    >>> get(None, "a", "b", default=0)
    0
    """
    current: Any = obj
    for k in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(k)
        if current is None:
            return default
    return current


def num(value: Any, default: Optional[Number] = None) -> Optional[Number]:
    """Coerce *value* to a number or return *default*.

    Returns *default* for ``None`` and the ``"N/R"`` sentinel so that
    N/R values are never silently converted to zero.

    >>> num("3.14")
    3.14
    >>> num(None, 0)
    0
    >>> num("N/R")
    """
    if value is None or is_nr(value):
        return default
    try:
        f = float(value)
        return int(f) if f == int(f) and isinstance(value, (int, str)) else f
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Safe math
# ---------------------------------------------------------------------------


def safe_avg(values: Sequence[Any], ndigits: int = 2) -> Optional[float]:
    """Average of non-None / non-N/R numeric values, or ``None``.

    Skips ``None`` and ``"N/R"`` sentinels so disabled integrations
    never pollute averages.

    >>> safe_avg([1, 2, None, 3])
    2.0
    >>> safe_avg(["N/R", None])
    """
    clean = [v for v in values if v is not None and not is_nr(v)]
    if not clean:
        return None
    return round(sum(clean) / len(clean), ndigits)


def safe_sum(values: Sequence[Any]) -> Optional[Number]:
    """Sum of non-None / non-N/R numeric values.

    >>> safe_sum([1, None, 3])
    4
    >>> safe_sum(["N/R", None])  # returns None
    """
    clean = [v for v in values if v is not None and not is_nr(v)]
    if not clean:
        return None
    return sum(clean)


def clamp(value: Optional[Number], lo: Number = 0, hi: Number = 100) -> Optional[float]:
    """Clamp *value* between *lo* and *hi*, or ``None`` if input is None.

    >>> clamp(120)
    100.0
    >>> clamp(-5)
    0.0
    """
    if value is None:
        return None
    return round(max(lo, min(hi, float(value))), 2)


def percent(part: Optional[Number], total: Optional[Number], ndigits: int = 2) -> Optional[float]:
    """``part / total * 100`` with null safety.

    >>> percent(3, 10)
    30.0
    >>> percent(None, 10)
    """
    if part is None or total is None or total == 0:
        return None
    return round(float(part) / float(total) * 100, ndigits)


def rate(part: Optional[Number], total: Optional[Number], ndigits: int = 4) -> Optional[float]:
    """``part / total`` ratio (0–1 scale) with null safety."""
    if part is None or total is None or total == 0:
        return None
    return round(float(part) / float(total), ndigits)


# ---------------------------------------------------------------------------
# Bucketing
# ---------------------------------------------------------------------------


def bucketize(
    value: Optional[Number],
    thresholds: Sequence[tuple[Number, str]],
    default: str = "Unknown",
) -> str:
    """Classify *value* into a named bucket.

    *thresholds* is a sequence of ``(upper_bound, label)`` **sorted
    ascending**.  The first bucket whose upper bound ≥ value wins.

    >>> bucketize(15, [(10, "Low"), (50, "Medium"), (100, "High")])
    'Medium'
    >>> bucketize(None, [(10, "Low")])
    'Unknown'
    """
    if value is None:
        return default
    for bound, label in thresholds:
        if value <= bound:
            return label
    # value exceeds all thresholds → last label or default
    return thresholds[-1][1] if thresholds else default


# ---------------------------------------------------------------------------
# Bool helpers
# ---------------------------------------------------------------------------


def bool_pct(values: Sequence[Any], ndigits: int = 2) -> Optional[float]:
    """Percentage of ``True`` among non-None / non-N/R booleans.

    >>> bool_pct([True, False, None, True])
    66.67
    >>> bool_pct(["N/R", None])
    """
    clean = [v for v in values if v is not None and not is_nr(v)]
    if not clean:
        return None
    return round(sum(1 for v in clean if v) / len(clean) * 100, ndigits)


# ---------------------------------------------------------------------------
# Collection helpers
# ---------------------------------------------------------------------------


def collect_values(
    dicts: Sequence[Dict[str, Any]],
    *keys: str,
    skip_none: bool = True,
    skip_nr: bool = True,
) -> List[Any]:
    """Pluck a nested key from each dict.

    Skips ``None`` (if *skip_none*) and ``"N/R"`` sentinels
    (if *skip_nr*) so disabled integrations never pollute
    aggregation.

    >>> collect_values([{"a": {"b": 1}}, {"a": {"b": 2}}], "a", "b")
    [1, 2]
    >>> collect_values([{"a": "N/R"}], "a")
    []
    """
    result: List[Any] = []
    for d in dicts:
        v = get(d, *keys)
        if skip_none and v is None:
            continue
        if skip_nr and is_nr(v):
            continue
        result.append(v)
    return result
