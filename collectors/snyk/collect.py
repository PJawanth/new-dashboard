#!/usr/bin/env python3
"""
Snyk Metrics Collector

Fetches vulnerability and dependency scanning data from the Snyk API.
Stores per-project JSON files in data/raw/snyk_{project}.json.

Required environment variables:
    SNYK_TOKEN — Snyk API token
    SNYK_ORG   — Snyk organisation ID
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

SNYK_TOKEN: str = os.environ.get("SNYK_TOKEN", "")
SNYK_ORG: str = os.environ.get("SNYK_ORG", "")
SNYK_API: str = "https://api.snyk.io/rest"

RAW_DATA_DIR: Path = Path(__file__).resolve().parents[2] / "data" / "raw"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("snyk-collector")

_session = requests.Session()


def _auth() -> Dict[str, str]:
    if SNYK_TOKEN:
        return {"Authorization": f"token {SNYK_TOKEN}"}
    return {}


def snyk_get(path: str, params: Optional[Dict] = None) -> Any:
    """Issue a GET against the Snyk REST API."""
    url = f"{SNYK_API}/{path.lstrip('/')}"
    try:
        resp = _session.get(url, headers={**_auth(), "Content-Type": "application/vnd.api+json"}, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.warning("Snyk API error for %s: %s", path, exc)
        return None


def list_projects() -> List[Dict]:
    """List all projects in the Snyk organisation."""
    data = snyk_get(f"orgs/{SNYK_ORG}/projects", {"version": "2024-06-21", "limit": 100})
    if data and "data" in data:
        return data["data"]
    return []


def fetch_issues(project_id: str) -> List[Dict]:
    """Fetch open issues for a Snyk project."""
    data = snyk_get(
        f"orgs/{SNYK_ORG}/issues",
        {"version": "2024-06-21", "scan_item.id": project_id, "scan_item.type": "project", "limit": 100},
    )
    if data and "data" in data:
        return data["data"]
    return []


def collect_project(project: Dict) -> Dict[str, Any]:
    """Collect vulnerability data for a single Snyk project."""
    pid = project["id"]
    name = project.get("attributes", {}).get("name", pid)
    logger.info("Collecting Snyk → %s", name)

    issues = fetch_issues(pid)
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for issue in issues:
        sev = issue.get("attributes", {}).get("effective_severity_level", "medium").lower()
        if sev in severity_counts:
            severity_counts[sev] += 1

    return {
        "source": "snyk",
        "project_id": pid,
        "name": name,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "total_issues": len(issues),
        "severity": severity_counts,
        "project_type": project.get("attributes", {}).get("type", ""),
    }


def persist(data: Dict) -> None:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = data["name"].replace("/", "_").replace("\\", "_").replace(":", "_")
    path = RAW_DATA_DIR / f"snyk_{safe_name}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)
    logger.info("Saved → %s", path)


def main() -> None:
    if not SNYK_TOKEN or not SNYK_ORG:
        logger.error("SNYK_TOKEN and SNYK_ORG are required.")
        sys.exit(1)

    projects = list_projects()
    if not projects:
        logger.warning("No Snyk projects found.")
        return

    logger.info("Found %d Snyk projects", len(projects))
    for proj in projects:
        try:
            metrics = collect_project(proj)
            persist(metrics)
        except Exception:
            logger.exception("Failed to collect %s", proj.get("id"))

    logger.info("Snyk collection complete")


if __name__ == "__main__":
    main()
