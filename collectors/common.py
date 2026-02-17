"""
collectors.common
=================
Production-grade shared utilities for **all** collectors.

Provides:
    • ``require_env``          — fail-fast env-var loader
    • ``utc_now``, ``parse_iso8601`` — timezone-safe helpers
    • ``make_get``             — single HTTP GET with timeout & error wrapping
    • ``get_paginated``        — multi-page HTTP GET via Link / offset
    • ``parse_rate_limit``     — extract rate-limit metadata from response
    • ``CollectorError``       — consistent error dict structure

Dependency-light: only ``requests`` + stdlib.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests
from dateutil.parser import isoparse

__all__ = [
    "require_env",
    "is_configured",
    "utc_now",
    "parse_iso8601",
    "make_get",
    "get_paginated",
    "parse_rate_limit",
    "CollectorError",
    "collector_error",
]

logger = logging.getLogger("collectors.common")

# ---------------------------------------------------------------------------
# 1. Environment helpers
# ---------------------------------------------------------------------------


def require_env(varnames: Sequence[str]) -> Dict[str, str]:
    """Return a dict of ``{name: value}`` for every requested env var.

    Exits the process with a clear message if any variable is missing.
    """
    values: Dict[str, str] = {}
    missing: List[str] = []
    for name in varnames:
        val = os.environ.get(name, "").strip()
        if not val:
            missing.append(name)
        else:
            values[name] = val
    if missing:
        logger.error(
            "Missing required environment variable(s): %s",
            ", ".join(missing),
        )
        sys.exit(1)
    return values


def is_configured(*values: Optional[str]) -> bool:
    """Return ``True`` only if **every** value is a non-blank string.

    Use before calling any optional integration API::

        if not is_configured(os.environ.get("JIRA_URL"), os.environ.get("JIRA_TOKEN")):
            return disabled_stub()
    """
    return all(v is not None and str(v).strip() != "" for v in values)


# ---------------------------------------------------------------------------
# 2. Date / time helpers
# ---------------------------------------------------------------------------


def utc_now() -> datetime:
    """Return the current UTC time as an aware ``datetime``."""
    return datetime.now(timezone.utc)


def parse_iso8601(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 string into an aware ``datetime``, or *None*."""
    if not value:
        return None
    try:
        dt = isoparse(value)
        # ensure timezone-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def hours_between(start: Optional[str], end: Optional[str]) -> Optional[float]:
    """Return elapsed hours between two ISO-8601 timestamps, or *None*."""
    s, e = parse_iso8601(start), parse_iso8601(end)
    if s and e:
        return round((e - s).total_seconds() / 3600, 2)
    return None


# ---------------------------------------------------------------------------
# 3. Consistent error structure
# ---------------------------------------------------------------------------


@dataclass
class CollectorError:
    """Uniform error object returned by HTTP helpers."""

    source: str = ""
    url: str = ""
    status_code: Optional[int] = None
    message: str = ""
    retryable: bool = False
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "url": self.url,
            "status_code": self.status_code,
            "message": self.message,
            "retryable": self.retryable,
            "context": self.context,
        }


def collector_error(
    *,
    source: str = "",
    url: str = "",
    status_code: Optional[int] = None,
    message: str = "",
    retryable: bool = False,
    **extra: Any,
) -> CollectorError:
    """Convenience factory for ``CollectorError``."""
    return CollectorError(
        source=source,
        url=url,
        status_code=status_code,
        message=message,
        retryable=retryable,
        context=extra,
    )


# ---------------------------------------------------------------------------
# 4. Rate-limit parsing
# ---------------------------------------------------------------------------


@dataclass
class RateLimitInfo:
    """Parsed rate-limit metadata from HTTP response headers."""

    remaining: int = -1
    limit: int = -1
    reset_epoch: int = 0
    retry_after: Optional[int] = None

    @property
    def exhausted(self) -> bool:
        return self.remaining == 0

    @property
    def seconds_until_reset(self) -> int:
        return max(self.reset_epoch - int(time.time()), 0)


def parse_rate_limit(headers: requests.structures.CaseInsensitiveDict) -> RateLimitInfo:
    """Extract rate-limit metadata from response headers (GitHub / GitLab style)."""
    def _int(key: str, default: int = -1) -> int:
        try:
            return int(headers.get(key, default))
        except (ValueError, TypeError):
            return default

    return RateLimitInfo(
        remaining=_int("X-RateLimit-Remaining"),
        limit=_int("X-RateLimit-Limit"),
        reset_epoch=_int("X-RateLimit-Reset", 0),
        retry_after=_int("Retry-After") if "Retry-After" in headers else None,
    )


def _handle_rate_limit(rl: RateLimitInfo) -> None:
    """Sleep until the rate-limit window resets when exhausted."""
    if not rl.exhausted:
        return
    wait = rl.seconds_until_reset + 2
    if rl.retry_after and rl.retry_after > 0:
        wait = rl.retry_after + 1
    logger.warning("Rate-limit exhausted — sleeping %d s", wait)
    time.sleep(wait)


# ---------------------------------------------------------------------------
# 5. HTTP GET with retry, timeout & error wrapping
# ---------------------------------------------------------------------------

_default_session: Optional[requests.Session] = None


def _session() -> requests.Session:
    global _default_session
    if _default_session is None:
        _default_session = requests.Session()
        _default_session.headers.update({"User-Agent": "eng-intel-dashboard/1.0"})
    return _default_session


# Return type alias — (json | None, error | None, status_code, response_headers)
GetResult = Tuple[
    Optional[Any],
    Optional[CollectorError],
    int,
    Dict[str, str],
]


def make_get(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
    retries: int = 3,
    source: str = "",
) -> GetResult:
    """Perform a single HTTP GET with automatic retry and rate-limit handling.

    Returns ``(json_body, error, status_code, response_headers)``.
    On success ``error`` is *None*; on failure ``json_body`` is *None*.
    """
    last_err: Optional[CollectorError] = None
    resp_headers: Dict[str, str] = {}

    for attempt in range(1, retries + 1):
        try:
            resp = _session().get(
                url,
                headers=headers or {},
                params=params,
                timeout=timeout,
            )
            resp_headers = dict(resp.headers)

            rl = parse_rate_limit(resp.headers)
            _handle_rate_limit(rl)

            if resp.status_code == 404:
                return (
                    None,
                    collector_error(
                        source=source,
                        url=url,
                        status_code=404,
                        message="Not found",
                        retryable=False,
                    ),
                    404,
                    resp_headers,
                )

            if resp.status_code == 403 and rl.exhausted:
                # retry after rate-limit sleep (already handled above)
                continue

            if resp.status_code >= 500:
                last_err = collector_error(
                    source=source,
                    url=url,
                    status_code=resp.status_code,
                    message=f"Server error {resp.status_code}",
                    retryable=True,
                )
                if attempt < retries:
                    time.sleep(2 ** attempt)
                    continue
                return (None, last_err, resp.status_code, resp_headers)

            if resp.status_code >= 400:
                return (
                    None,
                    collector_error(
                        source=source,
                        url=url,
                        status_code=resp.status_code,
                        message=resp.text[:300],
                        retryable=False,
                    ),
                    resp.status_code,
                    resp_headers,
                )

            # 2xx — success
            try:
                body = resp.json()
            except ValueError:
                body = resp.text
            return (body, None, resp.status_code, resp_headers)

        except requests.ConnectionError as exc:
            last_err = collector_error(
                source=source, url=url, message=str(exc), retryable=True
            )
        except requests.Timeout as exc:
            last_err = collector_error(
                source=source, url=url, message=f"Timeout ({timeout}s)", retryable=True
            )
        except requests.RequestException as exc:
            last_err = collector_error(
                source=source, url=url, message=str(exc), retryable=False
            )

        if attempt < retries:
            logger.warning(
                "Attempt %d/%d failed for %s: %s",
                attempt,
                retries,
                url,
                last_err.message if last_err else "unknown",
            )
            time.sleep(2 ** attempt)

    return (None, last_err, 0, resp_headers)


# ---------------------------------------------------------------------------
# 6. Paginated GET (Link-header + offset support)
# ---------------------------------------------------------------------------

# Return type — (items, truncated, error, meta)
PaginatedResult = Tuple[
    List[Any],
    bool,
    Optional[CollectorError],
    Dict[str, Any],
]


def get_paginated(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    per_page: int = 100,
    max_pages: int = 5,
    source: str = "",
    timeout: int = 30,
    # If the JSON response wraps items in a key (e.g. {"workflow_runs": [...]}),
    # pass that key here so items are extracted automatically.
    items_key: Optional[str] = None,
) -> PaginatedResult:
    """Fetch all items across paginated API responses.

    Supports GitHub-style ``Link`` header pagination and generic
    ``page`` / ``per_page`` query-param pagination.

    Returns ``(items, truncated, error, meta)`` where *truncated* is
    *True* when ``max_pages`` was reached before exhausting all pages.
    """
    params = dict(params or {})
    params["per_page"] = str(per_page)

    items: List[Any] = []
    current_url: Optional[str] = url
    page = 0
    truncated = False
    meta: Dict[str, Any] = {"pages_fetched": 0, "total_items": 0}

    while current_url and page < max_pages:
        page += 1
        body, err, status, resp_headers = make_get(
            current_url,
            headers=headers,
            params=params if page == 1 else None,   # params are in the URL after page 1
            timeout=timeout,
            source=source,
        )

        if err:
            # 404 is non-fatal for paginated endpoints — just stop
            if err.status_code == 404:
                break
            return (items, False, err, meta)

        if body is None:
            break

        # Extract items from response
        if isinstance(body, list):
            items.extend(body)
        elif isinstance(body, dict):
            if items_key and items_key in body:
                items.extend(body[items_key])
            else:
                # try common wrapper keys
                for key in ("items", "results", "data", "values"):
                    if key in body and isinstance(body[key], list):
                        items.extend(body[key])
                        break
                else:
                    items.append(body)

        # Follow ``Link: <...>; rel="next"`` header
        link_header = resp_headers.get("Link", resp_headers.get("link", ""))
        current_url = _parse_next_link(link_header)

    meta["pages_fetched"] = page
    meta["total_items"] = len(items)
    truncated = page >= max_pages and current_url is not None

    return (items, truncated, None, meta)


def _parse_next_link(link_header: str) -> Optional[str]:
    """Extract the ``next`` URL from a ``Link`` header value."""
    if not link_header:
        return None
    for part in link_header.split(","):
        if 'rel="next"' in part:
            # <https://api.example.com/items?page=2>; rel="next"
            url = part.split(";")[0].strip().strip("<>")
            return url
    return None
