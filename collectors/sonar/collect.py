#!/usr/bin/env python3
"""
SonarQube Metrics Collector

Fetches code quality and technical debt metrics from the SonarQube API.
Stores per-project JSON files in data/raw/sonar_{project}.json.

Required environment variables:
    SONAR_URL   — SonarQube server URL (e.g. https://sonar.example.com)
    SONAR_TOKEN — authentication token
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

SONAR_URL: str = os.environ.get("SONAR_URL", "")
SONAR_TOKEN: str = os.environ.get("SONAR_TOKEN", "")

RAW_DATA_DIR: Path = Path(__file__).resolve().parents[2] / "data" / "raw"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("sonar-collector")

_session = requests.Session()


def _auth() -> Dict[str, str]:
    if SONAR_TOKEN:
        return {"Authorization": f"Bearer {SONAR_TOKEN}"}
    return {}


def sonar_get(path: str, params: Optional[Dict] = None) -> Any:
    """Issue a GET against the SonarQube API."""
    url = f"{SONAR_URL.rstrip('/')}/api/{path.lstrip('/')}"
    try:
        resp = _session.get(url, headers=_auth(), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.warning("SonarQube API error for %s: %s", path, exc)
        return None


def list_projects() -> List[Dict]:
    """Return all projects from SonarQube."""
    data = sonar_get("projects/search", {"ps": 500})
    if data and "components" in data:
        return data["components"]
    return []


def fetch_measures(project_key: str) -> Dict[str, Any]:
    """Fetch quality metrics for a single project."""
    metric_keys = ",".join([
        "bugs", "vulnerabilities", "code_smells",
        "coverage", "duplicated_lines_density",
        "sqale_index", "sqale_debt_ratio",
        "reliability_rating", "security_rating",
        "ncloc", "alert_status",
    ])
    data = sonar_get(
        "measures/component",
        {"component": project_key, "metricKeys": metric_keys},
    )
    if not data or "component" not in data:
        return {}
    measures = {}
    for m in data["component"].get("measures", []):
        measures[m["metric"]] = m.get("value")
    return measures


def collect_project(project: Dict) -> Dict[str, Any]:
    """Collect metrics for a single SonarQube project."""
    key = project["key"]
    logger.info("Collecting SonarQube → %s", key)
    measures = fetch_measures(key)
    return {
        "source": "sonarqube",
        "project_key": key,
        "name": project.get("name", key),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "measures": measures,
    }


def persist(data: Dict) -> None:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = data["project_key"].replace("/", "_").replace("\\", "_")
    path = RAW_DATA_DIR / f"sonar_{safe_name}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)
    logger.info("Saved → %s", path)


def main() -> None:
    if not SONAR_URL or not SONAR_TOKEN:
        logger.error("SONAR_URL and SONAR_TOKEN are required.")
        sys.exit(1)

    projects = list_projects()
    if not projects:
        logger.warning("No SonarQube projects found.")
        return

    logger.info("Found %d SonarQube projects", len(projects))
    for proj in projects:
        try:
            metrics = collect_project(proj)
            persist(metrics)
        except Exception:
            logger.exception("Failed to collect %s", proj.get("key"))

    logger.info("SonarQube collection complete")


if __name__ == "__main__":
    main()
