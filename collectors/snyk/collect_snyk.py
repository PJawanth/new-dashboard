#!/usr/bin/env python3
"""
Snyk Vulnerability Collector (v2)
==================================
Fetches projects and issues from the Snyk REST API, maps them to
repositories already collected in ``data/raw/*.json``, and enriches
each raw JSON with a ``snyk`` section.

Falls back to updating normalised ``security`` fields when the GitHub
security data is unavailable.

Uses ``collectors.common`` for all HTTP and utility functions.

Environment variables
---------------------
Required:
    SNYK_TOKEN   — Snyk API authentication token
    SNYK_ORG_ID  — Snyk organisation ID (UUID)

Optional:
    SNYK_API_BASE  — REST API base (default ``https://api.snyk.io/rest``)
    SNYK_API_VER   — API version header (default ``2024-06-21``)
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from collectors.common import (
    CollectorError,
    get_paginated,
    make_get,
    require_env,
    utc_now,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

COLLECTOR_VERSION = "2.0.0"

logger = logging.getLogger("snyk-collector")

RAW_DATA_DIR: Path = Path(__file__).resolve().parents[2] / "data" / "raw"


def _load_config() -> Dict[str, Any]:
    env = require_env(["SNYK_TOKEN", "SNYK_ORG_ID"])
    return {
        "token": env["SNYK_TOKEN"],
        "org_id": env["SNYK_ORG_ID"],
        "api_base": os.environ.get(
            "SNYK_API_BASE", "https://api.snyk.io/rest"
        ).strip().rstrip("/"),
        "api_version": os.environ.get("SNYK_API_VER", "2024-06-21").strip(),
        "log_level": os.environ.get("LOG_LEVEL", "INFO").upper(),
    }


# ---------------------------------------------------------------------------
# HTTP wrapper
# ---------------------------------------------------------------------------


def _snyk_headers(cfg: Dict[str, Any]) -> Dict[str, str]:
    return {
        "Authorization": f"token {cfg['token']}",
        "Content-Type": "application/vnd.api+json",
    }


def snyk_get(
    path: str,
    cfg: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
) -> tuple[Any, Optional[CollectorError], bool]:
    """Single Snyk REST API GET.

    Returns ``(json_body, error, accessible)``.
    """
    url = f"{cfg['api_base']}/{path.lstrip('/')}"
    params = dict(params or {})
    params.setdefault("version", cfg["api_version"])

    body, err, status, _ = make_get(
        url,
        headers=_snyk_headers(cfg),
        params=params,
        source="snyk",
    )
    accessible = status not in (401, 403, 404) if err else True
    return body, err, accessible


def snyk_paginated(
    path: str,
    cfg: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
    max_pages: int = 10,
) -> tuple[List[Any], bool, Optional[CollectorError], bool]:
    """Paginated Snyk REST API GET.

    Returns ``(items, truncated, error, accessible)``.
    """
    url = f"{cfg['api_base']}/{path.lstrip('/')}"
    params = dict(params or {})
    params.setdefault("version", cfg["api_version"])
    params.setdefault("limit", "100")

    items, truncated, err, meta = get_paginated(
        url,
        headers=_snyk_headers(cfg),
        params=params,
        per_page=100,
        max_pages=max_pages,
        source="snyk",
        items_key="data",
    )
    accessible = True
    if err and err.status_code in (401, 403, 404):
        accessible = False
    return items, truncated, err, accessible


# ---------------------------------------------------------------------------
# Project listing & repo mapping
# ---------------------------------------------------------------------------


def list_projects(cfg: Dict[str, Any]) -> tuple[List[Dict], bool]:
    """Fetch all Snyk projects for the organisation."""
    items, truncated, err, accessible = snyk_paginated(
        f"orgs/{cfg['org_id']}/projects", cfg
    )
    if not accessible:
        logger.error("Cannot access Snyk projects (403/401)")
        return [], False
    return items, accessible


def _normalise_repo_name(name: str) -> str:
    """Strip owner prefix and common suffixes to get a bare repo name."""
    # "owner/repo:path/to/manifest" → "repo"
    name = name.split(":")[0]  # drop manifest path
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    return name.lower().strip()


def map_projects_to_repos(
    projects: List[Dict],
    known_repos: Set[str],
) -> Dict[str, List[Dict]]:
    """Map Snyk projects to known repo names.

    Returns ``{repo_name_lower: [project, ...]}``.
    Logs unmapped projects.
    """
    mapped: Dict[str, List[Dict]] = {}
    unmapped: List[str] = []

    for proj in projects:
        attrs = proj.get("attributes", {})
        proj_name = attrs.get("name", proj.get("id", ""))

        # Try to extract repo from the project name or origin
        repo_name = _normalise_repo_name(proj_name)
        origin = attrs.get("origin", "")
        target_ref = (attrs.get("target_reference") or "").lower()

        # Also try matching from the target (SCM) info if present
        candidates = {repo_name}
        if origin:
            candidates.add(_normalise_repo_name(origin))

        matched = False
        for candidate in candidates:
            if candidate in known_repos:
                mapped.setdefault(candidate, []).append(proj)
                matched = True
                break

        if not matched:
            unmapped.append(proj_name)

    if unmapped:
        logger.info(
            "Unmapped Snyk projects (%d): %s",
            len(unmapped),
            ", ".join(unmapped[:20]) + ("..." if len(unmapped) > 20 else ""),
        )

    return mapped


# ---------------------------------------------------------------------------
# Issue fetching & severity computation
# ---------------------------------------------------------------------------


def fetch_issues(
    project_id: str, cfg: Dict[str, Any]
) -> tuple[List[Dict], bool]:
    """Fetch open issues for a single Snyk project."""
    items, truncated, err, accessible = snyk_paginated(
        f"orgs/{cfg['org_id']}/issues",
        cfg,
        {
            "scan_item.id": project_id,
            "scan_item.type": "project",
            "limit": "100",
        },
    )
    if not accessible:
        return [], False
    return items, accessible


def compute_severity(issues: List[Dict]) -> Dict[str, Any]:
    """Aggregate severity counts, fixable count, and license issues."""
    sev = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    fixable = 0
    license_issues = 0

    for issue in issues:
        attrs = issue.get("attributes", {})

        # Severity
        level = (attrs.get("effective_severity_level") or "medium").lower()
        if level in sev:
            sev[level] += 1

        # Fixable
        if attrs.get("is_fixable") or attrs.get("is_upgradeable") or attrs.get("is_patchable"):
            fixable += 1

        # License
        issue_type = (attrs.get("type") or "").lower()
        if "license" in issue_type:
            license_issues += 1

    return {
        "critical": sev["critical"],
        "high": sev["high"],
        "medium": sev["medium"],
        "low": sev["low"],
        "total": sum(sev.values()),
        "fixable": fixable,
        "license_issues": license_issues,
    }


def detect_eol_components(issues: List[Dict]) -> List[Dict[str, Any]]:
    """Detect end-of-life / deprecated packages from Snyk issues.

    EOL indicators:
      • issue title contains "end-of-life", "eol", "deprecated", "no longer maintained"
      • package has no available fix and is marked as not upgradeable
      • semver suggests major-version lag (e.g. v1.x when v5.x exists)
    """
    EOL_KEYWORDS = [
        "end-of-life", "end of life", "eol", "deprecated",
        "no longer maintained", "unmaintained", "abandoned",
        "unsupported", "sunset", "reached its end",
    ]
    eol_list: List[Dict[str, Any]] = []
    seen_packages: Set[str] = set()

    for issue in issues:
        attrs = issue.get("attributes", {})
        title = (attrs.get("title") or "").lower()
        desc = (attrs.get("description") or "").lower()
        pkg_name = attrs.get("package") or attrs.get("pkgName") or ""

        # Check for EOL keywords in title or description
        is_eol = any(kw in title or kw in desc for kw in EOL_KEYWORDS)

        # Also flag packages with no fix available and marked not upgradeable
        if not is_eol:
            has_no_fix = (
                not attrs.get("is_fixable")
                and not attrs.get("is_upgradeable")
                and not attrs.get("is_patchable")
            )
            sev = (attrs.get("effective_severity_level") or "").lower()
            if has_no_fix and sev in ("critical", "high"):
                is_eol = True  # High/critical with no fix path → likely EOL

        if is_eol and pkg_name and pkg_name.lower() not in seen_packages:
            seen_packages.add(pkg_name.lower())
            eol_list.append({
                "package": pkg_name,
                "version": attrs.get("version") or attrs.get("pkgVersions") or "unknown",
                "severity": (attrs.get("effective_severity_level") or "medium").lower(),
                "reason": title[:120] if title else "deprecated / no fix available",
            })

    return eol_list


# ---------------------------------------------------------------------------
# Per-repo collection
# ---------------------------------------------------------------------------


def collect_for_repo(
    repo_projects: List[Dict],
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Aggregate issues across all Snyk projects mapped to one repo."""
    now = utc_now().isoformat()
    all_issues: List[Dict] = []
    project_summaries: List[Dict[str, Any]] = []
    accessible = True

    for proj in repo_projects:
        pid = proj.get("id", "")
        attrs = proj.get("attributes", {})
        issues, ok = fetch_issues(pid, cfg)
        if not ok:
            accessible = False
            continue

        sev = compute_severity(issues)
        project_summaries.append(
            {
                "project_id": pid,
                "name": attrs.get("name", pid),
                "type": attrs.get("type", ""),
                "origin": attrs.get("origin", ""),
                "total_issues": sev["total"],
                "severity": {
                    "critical": sev["critical"],
                    "high": sev["high"],
                    "medium": sev["medium"],
                    "low": sev["low"],
                },
            }
        )
        all_issues.extend(issues)

    totals = compute_severity(all_issues)
    eol_components = detect_eol_components(all_issues)

    return {
        "available": accessible and len(project_summaries) > 0,
        "collected_at": now,
        "collector_version": COLLECTOR_VERSION,
        "total_issues": totals["total"],
        "severity": {
            "critical": totals["critical"],
            "high": totals["high"],
            "medium": totals["medium"],
            "low": totals["low"],
        },
        "fixable": totals["fixable"],
        "license_issues": totals["license_issues"],
        "eol_components": eol_components,
        "eol_component_count": len(eol_components),
        "projects": project_summaries,
    }


def maybe_update_security(
    raw: Dict[str, Any], snyk_section: Dict[str, Any]
) -> None:
    """If GitHub security data is unavailable, populate normalised security
    fields from Snyk data."""
    avail = raw.get("availability") or {}
    github_sec = (
        avail.get("code_scanning") is not False
        and avail.get("dependabot") is not False
    )
    if github_sec:
        return  # GitHub security is available, don't overwrite

    if not snyk_section.get("available"):
        return

    sev = snyk_section.get("severity") or {}
    raw.setdefault("security", {})
    sec = raw["security"]
    sec.setdefault("critical", sev.get("critical", 0))
    sec.setdefault("high", sev.get("high", 0))
    sec.setdefault("medium", sev.get("medium", 0))
    sec.setdefault("low", sev.get("low", 0))
    sec.setdefault("dependency_alerts", snyk_section.get("total_issues", 0))


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def load_raw_repos() -> Dict[str, tuple[Path, Dict]]:
    """Load all ``data/raw/*.json`` and return ``{name_lower: (path, data)}``."""
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


def main() -> None:
    cfg = _load_config()

    logging.basicConfig(
        level=getattr(logging, cfg["log_level"], logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )

    logger.info(
        "Snyk collector starting — org=%s, api=%s",
        cfg["org_id"],
        cfg["api_base"],
    )

    # 1. List Snyk projects
    projects, accessible = list_projects(cfg)
    if not accessible:
        logger.error("Snyk API not accessible — aborting")
        return
    if not projects:
        logger.warning("No Snyk projects found")
        return

    logger.info("Found %d Snyk projects", len(projects))

    # 2. Load raw repos
    repos = load_raw_repos()
    if not repos:
        logger.warning("No raw repo files found in %s", RAW_DATA_DIR)
        return

    # 3. Map projects → repos
    mapping = map_projects_to_repos(projects, set(repos.keys()))
    logger.info(
        "Mapped %d repos (of %d known) to Snyk projects",
        len(mapping),
        len(repos),
    )

    # 4. Collect per repo
    enriched = 0
    for repo_name, repo_projects in mapping.items():
        if repo_name not in repos:
            continue
        path, raw = repos[repo_name]

        logger.info("Snyk → %s (%d projects)", repo_name, len(repo_projects))
        snyk = collect_for_repo(repo_projects, cfg)
        raw["snyk"] = snyk

        # Propagate EOL data to security section
        sec = raw.setdefault("security", {})
        eol = snyk.get("eol_components", [])
        if eol:
            sec["eol_components"] = len(eol)
            sec["eol_component_list"] = eol

        maybe_update_security(raw, snyk)

        with open(path, "w", encoding="utf-8") as fh:
            json.dump(raw, fh, indent=2, default=str)
        enriched += 1

        if snyk["available"]:
            sev = snyk["severity"]
            logger.info(
                "  ✓ C=%d H=%d M=%d L=%d (total=%d)",
                sev["critical"], sev["high"], sev["medium"], sev["low"],
                snyk["total_issues"],
            )
        else:
            logger.info("  ✗ not available")

    # 5. Mark repos with no Snyk mapping as unavailable
    for repo_name in repos:
        if repo_name not in mapping:
            path, raw = repos[repo_name]
            if "snyk" not in raw:
                raw["snyk"] = {
                    "available": False,
                    "collected_at": utc_now().isoformat(),
                    "collector_version": COLLECTOR_VERSION,
                    "error": "No matching Snyk project found",
                }
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(raw, fh, indent=2, default=str)

    logger.info(
        "Snyk collection complete — %d/%d repos enriched", enriched, len(repos)
    )


if __name__ == "__main__":
    main()
