#!/usr/bin/env python3
"""
Logging Monitor Collector

Queries a centralised logging backend (e.g. Elasticsearch / OpenSearch)
for error-rate and availability signals.
Stores results in data/raw/logging_metrics.json.

Required environment variables:
    LOG_BACKEND_URL — base URL (e.g. https://es.example.com)
    LOG_BACKEND_TOKEN — bearer token (optional, depends on backend)
    LOG_INDEX_PATTERN — index/alias to query (default: app-logs-*)
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import requests

LOG_BACKEND_URL: str = os.environ.get("LOG_BACKEND_URL", "")
LOG_BACKEND_TOKEN: str = os.environ.get("LOG_BACKEND_TOKEN", "")
LOG_INDEX_PATTERN: str = os.environ.get("LOG_INDEX_PATTERN", "app-logs-*")
LOOKBACK_HOURS: int = int(os.environ.get("LOG_LOOKBACK_HOURS", "24"))

RAW_DATA_DIR: Path = Path(__file__).resolve().parents[2] / "data" / "raw"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("logging-collector")

_session = requests.Session()


def _auth() -> Dict[str, str]:
    if LOG_BACKEND_TOKEN:
        return {"Authorization": f"Bearer {LOG_BACKEND_TOKEN}"}
    return {}


def es_search(index: str, body: Dict) -> Optional[Dict]:
    """Execute a search against Elasticsearch / OpenSearch."""
    url = f"{LOG_BACKEND_URL.rstrip('/')}/{index}/_search"
    try:
        resp = _session.post(
            url,
            headers={**_auth(), "Content-Type": "application/json"},
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.warning("Log backend error: %s", exc)
        return None


def fetch_error_counts() -> Dict[str, Any]:
    """Aggregate error-level log counts over the lookback window."""
    since = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).isoformat()
    body = {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    {"range": {"@timestamp": {"gte": since}}},
                ]
            }
        },
        "aggs": {
            "by_level": {
                "terms": {"field": "level.keyword", "size": 10}
            },
            "by_service": {
                "terms": {"field": "service.keyword", "size": 50},
                "aggs": {
                    "errors": {
                        "filter": {"terms": {"level.keyword": ["ERROR", "CRITICAL", "FATAL"]}}
                    }
                }
            }
        }
    }
    result = es_search(LOG_INDEX_PATTERN, body)
    if not result:
        return {}

    aggs = result.get("aggregations", {})
    level_buckets = {b["key"]: b["doc_count"] for b in aggs.get("by_level", {}).get("buckets", [])}
    service_errors = {
        b["key"]: b["errors"]["doc_count"]
        for b in aggs.get("by_service", {}).get("buckets", [])
    }

    total = result.get("hits", {}).get("total", {})
    total_count = total.get("value", 0) if isinstance(total, dict) else total

    return {
        "total_logs": total_count,
        "by_level": level_buckets,
        "errors_by_service": service_errors,
        "error_count": sum(
            v for k, v in level_buckets.items() if k in ("ERROR", "CRITICAL", "FATAL")
        ),
    }


def main() -> None:
    if not LOG_BACKEND_URL:
        logger.error("LOG_BACKEND_URL is required.")
        sys.exit(1)

    logger.info("Querying %s (last %d hours, index=%s)", LOG_BACKEND_URL, LOOKBACK_HOURS, LOG_INDEX_PATTERN)
    metrics = fetch_error_counts()

    payload = {
        "source": "logging",
        "backend_url": LOG_BACKEND_URL,
        "index_pattern": LOG_INDEX_PATTERN,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "lookback_hours": LOOKBACK_HOURS,
        "metrics": metrics,
    }

    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DATA_DIR / "logging_metrics.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    logger.info("Saved → %s", path)


if __name__ == "__main__":
    main()
