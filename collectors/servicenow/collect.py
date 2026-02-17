#!/usr/bin/env python3
"""
ServiceNow Change Management Collector

Fetches change requests from the ServiceNow Table API to track change
management compliance, lead times, and failure rates.
Stores data in data/raw/servicenow_changes.json.

Required environment variables:
    SNOW_INSTANCE — ServiceNow instance (e.g. dev12345.service-now.com)
    SNOW_USER     — basic-auth username
    SNOW_PASSWORD — basic-auth password
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

SNOW_INSTANCE: str = os.environ.get("SNOW_INSTANCE", "")
SNOW_USER: str = os.environ.get("SNOW_USER", "")
SNOW_PASSWORD: str = os.environ.get("SNOW_PASSWORD", "")
LOOKBACK_DAYS: int = int(os.environ.get("LOOKBACK_DAYS", "30"))

RAW_DATA_DIR: Path = Path(__file__).resolve().parents[2] / "data" / "raw"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("servicenow-collector")

_session = requests.Session()


def snow_get(table: str, params: Optional[Dict] = None) -> List[Dict]:
    """Query a ServiceNow table."""
    url = f"https://{SNOW_INSTANCE}/api/now/table/{table}"
    try:
        resp = _session.get(
            url,
            auth=(SNOW_USER, SNOW_PASSWORD),
            headers={"Accept": "application/json"},
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("result", [])
    except requests.RequestException as exc:
        logger.warning("ServiceNow API error for %s: %s", table, exc)
        return []


def fetch_changes() -> List[Dict]:
    """Fetch recent change requests."""
    since = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    return snow_get("change_request", {
        "sysparm_query": f"sys_created_on>={since}",
        "sysparm_fields": "number,short_description,state,type,risk,category,sys_created_on,closed_at,close_code",
        "sysparm_limit": "500",
    })


def compute_metrics(changes: List[Dict]) -> Dict[str, Any]:
    """Derive change management metrics."""
    total = len(changes)
    successful = sum(1 for c in changes if c.get("close_code") == "successful")
    failed = sum(1 for c in changes if c.get("close_code") in ("unsuccessful", "failed"))

    return {
        "total_changes": total,
        "successful": successful,
        "failed": failed,
        "change_success_rate": round(successful / total, 4) if total else 0,
        "change_failure_rate": round(failed / total, 4) if total else 0,
        "by_type": _count_field(changes, "type"),
        "by_risk": _count_field(changes, "risk"),
        "by_category": _count_field(changes, "category"),
    }


def _count_field(items: List[Dict], field: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in items:
        val = item.get(field, "unknown") or "unknown"
        counts[val] = counts.get(val, 0) + 1
    return counts


def main() -> None:
    if not SNOW_INSTANCE or not SNOW_USER or not SNOW_PASSWORD:
        logger.error("SNOW_INSTANCE, SNOW_USER, and SNOW_PASSWORD are required.")
        sys.exit(1)

    logger.info("Fetching change requests from %s (last %d days)", SNOW_INSTANCE, LOOKBACK_DAYS)
    changes = fetch_changes()
    if not changes:
        logger.warning("No change requests found.")
        return

    metrics = compute_metrics(changes)
    payload = {
        "source": "servicenow",
        "instance": SNOW_INSTANCE,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": LOOKBACK_DAYS,
        "metrics": metrics,
        "changes": changes,
    }

    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DATA_DIR / "servicenow_changes.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    logger.info("Saved → %s (%d changes)", path, len(changes))


if __name__ == "__main__":
    main()
