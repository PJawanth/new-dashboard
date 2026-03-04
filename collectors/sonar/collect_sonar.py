#!/usr/bin/env python3
"""
SonarQube / SonarCloud Metrics Collector (v2)
==============================================
For each repo already collected in ``data/raw/*.json``, derives a Sonar
project key and fetches code-quality measures from the SonarQube/SonarCloud
REST API.  Enriches the raw repo JSON with a ``sonar`` section and
populates normalised ``quality`` fields for the aggregator.

Uses ``collectors.common`` for all HTTP and utility functions.

Environment variables
---------------------
Required:
    SONAR_HOST_URL   — SonarQube/SonarCloud base URL
    SONAR_TOKEN      — user / project token (used via HTTP Basic)

Optional:
    SONAR_ORG           — SonarCloud organisation key (omit for self-hosted)
    SONAR_BRANCH_MAIN   — main branch to query (default ``main``)
    SONAR_BRANCH_DEV    — dev branch to query  (default ``dev``)
    LOOKBACK_DAYS       — (unused directly, inherited from raw data)
"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from collectors.common import (
    collector_error,
    make_get,
    require_env,
    utc_now,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

COLLECTOR_VERSION = "2.0.0"

logger = logging.getLogger("sonar-collector")

RAW_DATA_DIR: Path = Path(__file__).resolve().parents[2] / "data" / "raw"

# Sonar Web API uses HTTP Basic Auth with token as username, empty password.
# common.make_get only supports header-based auth, so we build the header.


def _load_config() -> Dict[str, Any]:
    # Accept either SONAR_HOST_URL or SONAR_URL for flexibility
    host = os.environ.get("SONAR_HOST_URL", "").strip() or os.environ.get("SONAR_URL", "").strip()
    if not host:
        raise SystemExit("Missing required environment variable: SONAR_HOST_URL (or SONAR_URL)")
    env = require_env(["SONAR_TOKEN"])
    token = env["SONAR_TOKEN"]
    basic = base64.b64encode(f"{token}:".encode()).decode()
    return {
        "host": host.rstrip("/"),
        "token": token,
        "auth_header": f"Basic {basic}",
        "org": os.environ.get("SONAR_ORG", "").strip() or None,
        "branch_main": os.environ.get("SONAR_BRANCH_MAIN", "main").strip(),
        "branch_dev": os.environ.get("SONAR_BRANCH_DEV", "dev").strip(),
        "log_level": os.environ.get("LOG_LEVEL", "INFO").upper(),
    }


# ---------------------------------------------------------------------------
# HTTP wrapper
# ---------------------------------------------------------------------------


def sonar_get(
    path: str,
    cfg: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
) -> tuple[Any, bool, Optional[str]]:
    """GET against the Sonar Web API.

    Returns ``(json_body, accessible, error_reason)``.
    """
    url = f"{cfg['host']}/api/{path.lstrip('/')}"
    body, err, status, _ = make_get(
        url,
        headers={"Authorization": cfg["auth_header"]},
        params=params,
        source="sonar",
    )
    if err:
        reason = err.message or f"HTTP {err.status_code}"
        accessible = status not in (401, 403, 404)
        return None, accessible, reason
    return body, True, None


# ---------------------------------------------------------------------------
# Project key derivation
# ---------------------------------------------------------------------------


def derive_project_key(
    repo_name: str,
    full_name: str,
    raw: Dict[str, Any],
    org: Optional[str],
) -> List[str]:
    """Return candidate Sonar project keys in priority order.

    1. Explicit ``sonar.project_key`` in the raw JSON.
    2. ``{org}_{repo}``  (SonarCloud convention).
    3. ``{repo}``        (self-hosted fallback).
    """
    candidates: List[str] = []

    # 1. Explicit key from raw JSON
    explicit = (raw.get("sonar") or {}).get("project_key")
    if explicit:
        candidates.append(explicit)

    # 2. org_repo (replace / with _ for SonarCloud convention)
    if org:
        candidates.append(f"{org}_{repo_name}")

    owner = full_name.split("/")[0] if "/" in full_name else None
    if owner and owner != org:
        candidates.append(f"{owner}_{repo_name}")

    # 3. bare repo name
    candidates.append(repo_name)

    # deduplicate while preserving order
    seen: set[str] = set()
    unique: List[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


# ---------------------------------------------------------------------------
# Measures fetching
# ---------------------------------------------------------------------------

METRIC_KEYS = [
    "coverage",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "duplicated_lines_density",
    "sqale_index",
    "sqale_debt_ratio",
    "reliability_rating",
    "security_rating",
    "sqale_rating",
    "ncloc",
    "alert_status",
    "new_coverage",
    "new_bugs",
    "new_code_smells",
]


def fetch_measures(
    project_key: str,
    branch: str,
    cfg: Dict[str, Any],
) -> tuple[Optional[Dict[str, Any]], bool, Optional[str]]:
    """Fetch quality measures for a project on a given branch.

    Returns ``(measures_dict, accessible, error_reason)``.
    """
    params: Dict[str, Any] = {
        "component": project_key,
        "metricKeys": ",".join(METRIC_KEYS),
    }
    if branch:
        params["branch"] = branch

    body, accessible, reason = sonar_get("measures/component", cfg, params)
    if not accessible or body is None:
        return None, accessible, reason

    if "component" not in body:
        return None, True, "No component in response"

    measures: Dict[str, Any] = {}
    for m in body["component"].get("measures", []):
        key = m.get("metric", "")
        val = m.get("value")
        # try numeric conversion
        if val is not None:
            try:
                val = float(val)
                if val == int(val):
                    val = int(val)
            except (ValueError, TypeError):
                pass
        measures[key] = val
    return measures, True, None


def fetch_quality_gate(
    project_key: str,
    branch: str,
    cfg: Dict[str, Any],
) -> tuple[Optional[str], bool]:
    """Fetch quality gate status.  Returns ``(status, accessible)``."""
    params: Dict[str, Any] = {"projectKey": project_key}
    if branch:
        params["branch"] = branch

    body, accessible, _ = sonar_get("qualitygates/project_status", cfg, params)
    if not accessible or body is None:
        return None, accessible

    status = (body.get("projectStatus") or {}).get("status")
    return status, True


# ---------------------------------------------------------------------------
# Per-repo collection
# ---------------------------------------------------------------------------

MINUTES_PER_DAY = 480  # 8-hour work-day


def collect_for_repo(
    repo_name: str,
    full_name: str,
    raw: Dict[str, Any],
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Try candidate keys until a Sonar project is found.

    Returns a ``sonar`` section dict for the raw JSON.
    """
    candidates = derive_project_key(repo_name, full_name, raw, cfg["org"])
    now = utc_now().isoformat()

    for key in candidates:
        measures, accessible, reason = fetch_measures(
            key, cfg["branch_main"], cfg
        )
        if measures is not None:
            # success — also try dev branch
            dev_measures, _, _ = fetch_measures(key, cfg["branch_dev"], cfg)
            gate_status, _ = fetch_quality_gate(key, cfg["branch_main"], cfg)

            sqale_index = measures.get("sqale_index")
            tech_debt_days = (
                round(sqale_index / MINUTES_PER_DAY, 2)
                if sqale_index is not None
                else None
            )

            return {
                "available": True,
                "project_key": key,
                "collected_at": now,
                "collector_version": COLLECTOR_VERSION,
                "gate_status": gate_status,
                "branches": {
                    cfg["branch_main"]: measures,
                    cfg["branch_dev"]: dev_measures,
                },
                "measures": measures,  # main-branch snapshot for quick access
                "tech_debt_days": tech_debt_days,
            }

    # none of the candidate keys matched
    return {
        "available": False,
        "project_key": candidates[0] if candidates else repo_name,
        "collected_at": now,
        "collector_version": COLLECTOR_VERSION,
        "error": f"Project not found (tried: {', '.join(candidates)})",
    }


def build_quality_section(sonar: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Derive normalised ``quality`` fields from Sonar measures."""
    if not sonar.get("available"):
        return None
    m = sonar.get("measures") or {}
    sqale = m.get("sqale_index")
    ncloc = m.get("ncloc")
    sqale_ratio = m.get("sqale_debt_ratio")
    return {
        "bugs": m.get("bugs"),
        "code_smells": m.get("code_smells"),
        "coverage_pct": m.get("coverage"),
        "duplication_pct": m.get("duplicated_lines_density"),
        "tech_debt_hours": round(sqale / 60, 2) if sqale is not None else None,
        "tech_debt_ratio": round(float(sqale_ratio), 2) if sqale_ratio is not None else None,
        "reliability_rating": str(int(m["reliability_rating"])) if m.get("reliability_rating") is not None else None,
        "security_rating": str(int(m["security_rating"])) if m.get("security_rating") is not None else None,
        "maintainability_rating": str(int(m["sqale_rating"])) if m.get("sqale_rating") is not None else None,
        "ncloc": int(ncloc) if ncloc is not None else None,
    }


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def load_raw_repos() -> List[Path]:
    """Return paths to all ``data/raw/*.json`` files."""
    if not RAW_DATA_DIR.exists():
        return []
    return sorted(RAW_DATA_DIR.glob("*.json"))


def main() -> None:
    cfg = _load_config()

    logging.basicConfig(
        level=getattr(logging, cfg["log_level"], logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )

    raw_files = load_raw_repos()
    if not raw_files:
        logger.warning("No raw repo files found in %s", RAW_DATA_DIR)
        return

    logger.info(
        "Sonar collector starting — %d repos, host=%s, org=%s",
        len(raw_files),
        cfg["host"],
        cfg["org"] or "(none)",
    )

    enriched = 0
    for path in raw_files:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skip %s: %s", path.name, exc)
            continue

        meta = raw.get("repo_metadata") or raw
        repo_name = meta.get("repo", path.stem)
        full_name = meta.get("full_name", repo_name)

        logger.info("Sonar → %s", full_name)
        sonar = collect_for_repo(repo_name, full_name, raw, cfg)
        raw["sonar"] = sonar

        # Populate normalised quality section
        quality = build_quality_section(sonar)
        if quality:
            raw["quality"] = quality

        # Write back
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(raw, fh, indent=2, default=str)
        enriched += 1

        if sonar.get("available"):
            logger.info("  ✓ %s (gate=%s)", sonar["project_key"], sonar.get("gate_status"))
        else:
            logger.info("  ✗ not found — %s", sonar.get("error", ""))

    logger.info("Sonar collection complete — %d/%d repos enriched", enriched, len(raw_files))


if __name__ == "__main__":
    main()
