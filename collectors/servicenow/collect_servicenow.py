#!/usr/bin/env python3
"""
ServiceNow Value-Stream Collector (v2)
=======================================
Fetches change requests from the ServiceNow Table API and computes
org-level value-stream metrics.  Best-effort maps changes to
repositories and enriches ``data/raw/{repo}.json`` with a
``servicenow`` section.

Writes org-level summary to ``data/meta/servicenow_value_stream.json``.

Uses ``collectors.common`` for all HTTP and utility functions.

Environment variables
---------------------
Required:
    SERVICENOW_INSTANCE  — e.g. ``dev12345.service-now.com``
    SERVICENOW_USER      — basic-auth username
    SERVICENOW_PASSWORD  — basic-auth password

Optional:
    SERVICENOW_CHANGE_TABLE  — table name (default ``change_request``)
    SERVICENOW_QUERY         — additional encoded query filter
    LOOKBACK_DAYS            — days to look back (default 30)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from collectors.common import (
    collector_error,
    hours_between,
    is_configured,
    make_get,
    parse_iso8601,
    require_env,
    utc_now,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

COLLECTOR_VERSION = "2.0.0"

logger = logging.getLogger("servicenow-collector")

RAW_DATA_DIR: Path = Path(__file__).resolve().parents[2] / "data" / "raw"
META_DIR: Path = Path(__file__).resolve().parents[2] / "data" / "meta"

# ServiceNow fields to retrieve
_FIELDS = [
    "number",
    "sys_created_on",
    "opened_at",
    "work_start",
    "work_end",
    "closed_at",
    "state",
    "short_description",
    "type",
    "category",
    "risk",
    "close_code",
    "priority",
]


def _load_config() -> Dict[str, Any]:
    env = require_env(["SERVICENOW_INSTANCE", "SERVICENOW_USER", "SERVICENOW_PASSWORD"])
    user = env["SERVICENOW_USER"]
    pw = env["SERVICENOW_PASSWORD"]
    basic = base64.b64encode(f"{user}:{pw}".encode()).decode()
    lookback = int(os.environ.get("LOOKBACK_DAYS", "30"))
    return {
        "instance": env["SERVICENOW_INSTANCE"].strip().rstrip("/"),
        "auth_header": f"Basic {basic}",
        "table": os.environ.get("SERVICENOW_CHANGE_TABLE", "change_request").strip(),
        "extra_query": os.environ.get("SERVICENOW_QUERY", "").strip(),
        "lookback_days": lookback,
        "log_level": os.environ.get("LOG_LEVEL", "INFO").upper(),
    }


# ---------------------------------------------------------------------------
# HTTP wrapper
# ---------------------------------------------------------------------------


def snow_get(
    path: str,
    cfg: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
) -> tuple[Any, bool, Optional[str]]:
    """GET against ServiceNow REST API.

    Returns ``(json_body, accessible, error_reason)``.
    """
    url = f"https://{cfg['instance']}/{path.lstrip('/')}"
    body, err, status, _ = make_get(
        url,
        headers={
            "Authorization": cfg["auth_header"],
            "Accept": "application/json",
        },
        params=params,
        source="servicenow",
    )
    if err:
        reason = err.message or f"HTTP {err.status_code}"
        accessible = status not in (401, 403)
        return None, accessible, reason
    return body, True, None


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------


def _snow_datetime(dt_str: str) -> str:
    """Convert a ``datetime`` to ServiceNow query format."""
    return dt_str.replace("T", " ").split("+")[0].split(".")[0]


def fetch_changes(cfg: Dict[str, Any]) -> tuple[List[Dict], bool]:
    """Fetch recent change requests.

    Returns ``(changes, accessible)``.
    """
    now = utc_now()
    since = now - timedelta(days=cfg["lookback_days"])
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")

    query = f"sys_created_on>={since_str}"
    if cfg["extra_query"]:
        query = f"{query}^{cfg['extra_query']}"

    all_changes: List[Dict] = []
    offset = 0
    limit = 500
    accessible = True

    while True:
        body, ok, reason = snow_get(
            f"api/now/table/{cfg['table']}",
            cfg,
            {
                "sysparm_query": query,
                "sysparm_fields": ",".join(_FIELDS),
                "sysparm_limit": str(limit),
                "sysparm_offset": str(offset),
            },
        )
        if not ok:
            accessible = False
            break
        if body is None:
            break

        results = body.get("result", [])
        if not results:
            break

        all_changes.extend(results)
        if len(results) < limit:
            break
        offset += limit

    return all_changes, accessible


# ---------------------------------------------------------------------------
# Org-level value-stream metrics
# ---------------------------------------------------------------------------


def _safe_avg(values: List[float]) -> Optional[float]:
    return round(sum(values) / len(values), 2) if values else None


def compute_org_metrics(changes: List[Dict]) -> Dict[str, Any]:
    """Compute org-level value-stream metrics from change requests."""
    total = len(changes)

    # Lead time: opened → closed
    lead_times: List[float] = []
    for c in changes:
        h = hours_between(c.get("opened_at"), c.get("closed_at"))
        if h is not None and h >= 0:
            lead_times.append(h)

    # Implementation time: work_start → work_end
    impl_times: List[float] = []
    for c in changes:
        h = hours_between(c.get("work_start"), c.get("work_end"))
        if h is not None and h >= 0:
            impl_times.append(h)

    # Success / failure
    successful = sum(
        1
        for c in changes
        if (c.get("close_code") or "").lower() in ("successful", "success")
    )
    failed = sum(
        1
        for c in changes
        if (c.get("close_code") or "").lower() in ("unsuccessful", "failed", "failure")
    )

    # Emergency changes (type == "emergency" or priority 1)
    emergency = sum(
        1
        for c in changes
        if (c.get("type") or "").lower() == "emergency"
        or str(c.get("priority", "")).strip() == "1"
    )
    emergency_pct = round(emergency / total * 100, 2) if total else 0.0

    # Breakdowns
    by_type = _count_field(changes, "type")
    by_risk = _count_field(changes, "risk")
    by_state = _count_field(changes, "state")

    return {
        "total_changes": total,
        "successful": successful,
        "failed": failed,
        "change_success_rate": round(successful / total, 4) if total else 0.0,
        "change_failure_rate": round(failed / total, 4) if total else 0.0,
        "avg_lead_time_hours": _safe_avg(lead_times),
        "avg_implementation_time_hours": _safe_avg(impl_times),
        "emergency_count": emergency,
        "emergency_pct": emergency_pct,
        "by_type": by_type,
        "by_risk": by_risk,
        "by_state": by_state,
    }


def _count_field(items: List[Dict], field: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in items:
        val = (item.get(field) or "unknown").strip() or "unknown"
        counts[val] = counts.get(val, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Repo mapping (best-effort from short_description)
# ---------------------------------------------------------------------------


def map_changes_to_repos(
    changes: List[Dict],
    known_repos: Set[str],
) -> Dict[str, List[Dict]]:
    """Best-effort map changes to repos by scanning ``short_description``.

    Returns ``{repo_name_lower: [change, ...]}``.
    """
    mapped: Dict[str, List[Dict]] = {}

    for change in changes:
        desc = (change.get("short_description") or "").lower()
        if not desc:
            continue

        for repo in known_repos:
            # Match repo name as a word boundary
            if re.search(rf"\b{re.escape(repo)}\b", desc):
                mapped.setdefault(repo, []).append(change)
                break  # first match wins

    return mapped


def compute_repo_metrics(changes: List[Dict]) -> Dict[str, Any]:
    """Compute per-repo change metrics."""
    total = len(changes)
    lead_times: List[float] = []
    impl_times: List[float] = []
    for c in changes:
        h = hours_between(c.get("opened_at"), c.get("closed_at"))
        if h is not None and h >= 0:
            lead_times.append(h)
        h2 = hours_between(c.get("work_start"), c.get("work_end"))
        if h2 is not None and h2 >= 0:
            impl_times.append(h2)

    successful = sum(
        1 for c in changes
        if (c.get("close_code") or "").lower() in ("successful", "success")
    )
    failed = sum(
        1 for c in changes
        if (c.get("close_code") or "").lower() in ("unsuccessful", "failed", "failure")
    )

    return {
        "total_changes": total,
        "successful": successful,
        "failed": failed,
        "change_success_rate": round(successful / total, 4) if total else 0.0,
        "change_failure_rate": round(failed / total, 4) if total else 0.0,
        "avg_lead_time_hours": _safe_avg(lead_times),
        "avg_implementation_time_hours": _safe_avg(impl_times),
    }


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def load_raw_repos() -> Dict[str, tuple[Path, Dict]]:
    """Load ``data/raw/*.json`` → ``{name_lower: (path, data)}``."""
    result: Dict[str, tuple[Path, Dict]] = {}
    if not RAW_DATA_DIR.exists():
        return result
    for p in sorted(RAW_DATA_DIR.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            meta = data.get("repo_metadata") or data
            name = (meta.get("repo") or p.stem).lower()
            result[name] = (p, data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skip %s: %s", p.name, exc)
    return result


NR = "N/R"


def _disabled_servicenow_section() -> Dict[str, Any]:
    """Return a stub section when ServiceNow creds are not configured."""
    return {
        "available": False,
        "integration_status": "disabled",
        "collector_version": COLLECTOR_VERSION,
        "total_changes": NR,
        "successful": NR,
        "failed": NR,
        "change_success_rate": NR,
        "change_failure_rate": NR,
        "avg_lead_time_hours": NR,
        "avg_implementation_time_hours": NR,
        "emergency_count": NR,
        "emergency_pct": NR,
        "by_type": {},
        "by_risk": {},
        "by_state": {},
    }


def _disabled_org_summary() -> Dict[str, Any]:
    """Org-level summary stub when ServiceNow is disabled."""
    return {
        "source": "servicenow",
        "integration_status": "disabled",
        "collector_version": COLLECTOR_VERSION,
        "accessible": False,
        "total_changes": NR,
        "successful": NR,
        "failed": NR,
        "change_success_rate": NR,
        "change_failure_rate": NR,
        "avg_lead_time_hours": NR,
        "avg_implementation_time_hours": NR,
        "emergency_count": NR,
        "emergency_pct": NR,
        "by_type": {},
        "by_risk": {},
        "by_state": {},
    }


def main() -> None:
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )

    # ── Graceful degradation: check creds before anything ──
    snow_instance = os.environ.get("SERVICENOW_INSTANCE", "").strip() or os.environ.get("SNOW_INSTANCE", "").strip()
    snow_user = os.environ.get("SERVICENOW_USER", "").strip() or os.environ.get("SNOW_USER", "").strip()
    snow_pw = os.environ.get("SERVICENOW_PASSWORD", "").strip() or os.environ.get("SNOW_PASSWORD", "").strip()

    if not is_configured(snow_instance, snow_user, snow_pw):
        logger.info(
            "ServiceNow credentials not configured — writing N/R stubs "
            "(integration_status=disabled)"
        )
        now = utc_now()
        org_stub = _disabled_org_summary()
        org_stub["collected_at"] = now.isoformat()

        META_DIR.mkdir(parents=True, exist_ok=True)
        meta_path = META_DIR / "servicenow_value_stream.json"
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(org_stub, fh, indent=2, default=str)
        logger.info("Wrote disabled org summary → %s", meta_path)

        # Stamp every raw repo with a disabled section
        repos = load_raw_repos()
        for repo_name in repos:
            path, raw = repos[repo_name]
            raw["servicenow"] = {
                **_disabled_servicenow_section(),
                "collected_at": now.isoformat(),
            }
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(raw, fh, indent=2, default=str)

        logger.info("ServiceNow disabled — %d repos stamped with N/R", len(repos))
        return

    # ── Credentials present → normal collection ──
    cfg = _load_config()

    logging.basicConfig(
        level=getattr(logging, cfg["log_level"], logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )

    logger.info(
        "ServiceNow collector starting — instance=%s, table=%s, lookback=%d days",
        cfg["instance"],
        cfg["table"],
        cfg["lookback_days"],
    )

    # 1. Fetch change requests
    changes, accessible = fetch_changes(cfg)
    if not accessible:
        logger.error("ServiceNow API not accessible — aborting")
        return
    if not changes:
        logger.warning("No change requests found")

    logger.info("Fetched %d change requests", len(changes))

    # 2. Compute org-level metrics
    now = utc_now()
    org_metrics = compute_org_metrics(changes)
    org_summary = {
        "source": "servicenow",
        "integration_status": "enabled",
        "collected_at": now.isoformat(),
        "collector_version": COLLECTOR_VERSION,
        "instance": cfg["instance"],
        "table": cfg["table"],
        "lookback_days": cfg["lookback_days"],
        "accessible": accessible,
        **org_metrics,
    }

    # 3. Write org-level summary to data/meta/
    META_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = META_DIR / "servicenow_value_stream.json"
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(org_summary, fh, indent=2, default=str)
    logger.info("Wrote org summary → %s", meta_path)

    # 4. Best-effort map changes to repos & enrich raw JSONs
    repos = load_raw_repos()
    if not repos:
        logger.info("No raw repo files — skipping per-repo enrichment")
        return

    mapping = map_changes_to_repos(changes, set(repos.keys()))
    logger.info(
        "Mapped %d changes to %d repos (of %d known)",
        sum(len(v) for v in mapping.values()),
        len(mapping),
        len(repos),
    )

    enriched = 0
    for repo_name, repo_changes in mapping.items():
        if repo_name not in repos:
            continue
        path, raw = repos[repo_name]

        repo_metrics = compute_repo_metrics(repo_changes)
        raw["servicenow"] = {
            "available": True,
            "integration_status": "enabled",
            "collected_at": now.isoformat(),
            "collector_version": COLLECTOR_VERSION,
            **repo_metrics,
        }

        with open(path, "w", encoding="utf-8") as fh:
            json.dump(raw, fh, indent=2, default=str)
        enriched += 1

        logger.info(
            "  ✓ %s — %d changes, avg lead=%.1fh",
            repo_name,
            repo_metrics["total_changes"],
            repo_metrics["avg_lead_time_hours"] or 0,
        )

    # Mark unmapped repos
    for repo_name in repos:
        if repo_name not in mapping:
            path, raw = repos[repo_name]
            if "servicenow" not in raw:
                raw["servicenow"] = {
                    "available": False,
                    "integration_status": "enabled",
                    "collected_at": now.isoformat(),
                    "collector_version": COLLECTOR_VERSION,
                    "error": "No matching change requests found",
                }
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(raw, fh, indent=2, default=str)

    logger.info(
        "ServiceNow collection complete — %d/%d repos enriched, org summary at %s",
        enriched,
        len(repos),
        meta_path,
    )


if __name__ == "__main__":
    main()
