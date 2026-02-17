#!/usr/bin/env python3
"""
Logging Monitor Collector — GitHub Actions MVP (v2)
=====================================================
Uses GitHub Actions workflow runs as an MVP "logging" signal: tracks
total runs, failures, success rate, average duration, and top-failing
workflow names per repository.

Enriches ``data/raw/{repo}.json`` with a ``logging`` section and writes
an org-level summary to ``data/meta/logging_summary.json``.

Uses ``collectors.common`` for all HTTP and utility functions.

Environment variables
---------------------
Required:
    GITHUB_TOKEN  — GitHub PAT / fine-grained token
    GITHUB_ORG    — GitHub org (omit to use authenticated user repos)

Optional:
    LOG_DAYS      — Number of days to look back (default 7)
"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from collectors.common import (
    get_paginated,
    hours_between,
    make_get,
    require_env,
    utc_now,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

COLLECTOR_VERSION = "2.0.0"

logger = logging.getLogger("logging-collector")

RAW_DATA_DIR: Path = Path(__file__).resolve().parents[2] / "data" / "raw"
META_DIR: Path = Path(__file__).resolve().parents[2] / "data" / "meta"


def _load_config() -> Dict[str, Any]:
    env = require_env(["GITHUB_TOKEN"])
    return {
        "token": env["GITHUB_TOKEN"],
        "org": os.environ.get("GITHUB_ORG", "").strip(),
        "api": os.environ.get("GITHUB_API", "https://api.github.com").strip().rstrip("/"),
        "log_days": int(os.environ.get("LOG_DAYS", "7")),
        "max_pages": int(os.environ.get("MAX_PAGES", "10")),
        "log_level": os.environ.get("LOG_LEVEL", "INFO").upper(),
    }


# ---------------------------------------------------------------------------
# HTTP wrappers
# ---------------------------------------------------------------------------


def _gh_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def gh_paginated(
    path: str,
    cfg: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
    items_key: Optional[str] = None,
) -> tuple[List[Any], bool, bool]:
    """Paginated GitHub GET. Returns (items, truncated, accessible)."""
    url = f"{cfg['api']}{path}" if path.startswith("/") else path
    items, truncated, err, meta = get_paginated(
        url,
        headers=_gh_headers(cfg["token"]),
        params=params,
        per_page=100,
        max_pages=cfg["max_pages"],
        source="github",
        items_key=items_key,
    )
    accessible = True
    if err and err.status_code in (403, 404):
        accessible = False
    return items, truncated, accessible


# ---------------------------------------------------------------------------
# Per-repo logging metrics
# ---------------------------------------------------------------------------


def fetch_workflow_runs(
    owner: str, repo: str, since_date: str, cfg: Dict[str, Any]
) -> tuple[List[Dict], bool, bool]:
    """Fetch workflow runs created since ``since_date``."""
    items, truncated, accessible = gh_paginated(
        f"/repos/{owner}/{repo}/actions/runs",
        cfg,
        {"created": f">={since_date}", "per_page": "100"},
        items_key="workflow_runs",
    )
    return items, truncated, accessible


def compute_logging_metrics(runs: List[Dict]) -> Dict[str, Any]:
    """Compute MVP logging metrics from workflow runs."""
    total = len(runs)
    successes = [r for r in runs if r.get("conclusion") == "success"]
    failures = [r for r in runs if r.get("conclusion") == "failure"]

    # Average duration in minutes
    durations: List[float] = []
    for r in runs:
        start = r.get("run_started_at") or r.get("created_at")
        end = r.get("updated_at")
        h = hours_between(start, end)
        if h is not None and h >= 0:
            durations.append(h * 60)  # hours → minutes

    avg_duration = round(sum(durations) / len(durations), 2) if durations else None

    # Top failing workflow names
    fail_names: Counter = Counter()
    for r in failures:
        name = r.get("name") or r.get("workflow_id") or "unknown"
        fail_names[name] += 1
    top_failing = [
        {"name": name, "count": count}
        for name, count in fail_names.most_common(10)
    ]

    failure_rate = round(len(failures) / total, 4) if total else 0.0
    success_rate = round(len(successes) / total, 4) if total else 0.0

    return {
        "total_runs": total,
        "success_count": len(successes),
        "failure_count": len(failures),
        "success_rate": success_rate,
        "failure_rate": failure_rate,
        "avg_duration_mins": avg_duration,
        "top_failing_workflows": top_failing,
    }


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def load_raw_repos() -> Dict[str, tuple[Path, Dict]]:
    """Load all ``data/raw/*.json`` → ``{name_lower: (path, data)}``."""
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

    now = utc_now()
    since = now - timedelta(days=cfg["log_days"])
    since_date = since.strftime("%Y-%m-%d")

    logger.info(
        "Logging collector (GH Actions MVP) starting — log_days=%d, org=%s",
        cfg["log_days"],
        cfg["org"] or "(user)",
    )

    repos = load_raw_repos()
    if not repos:
        logger.warning("No raw repo files in %s", RAW_DATA_DIR)
        return

    org_totals: Dict[str, Any] = {
        "total_runs": 0,
        "success_count": 0,
        "failure_count": 0,
        "per_repo": [],
    }
    enriched = 0

    for repo_name, (path, raw) in repos.items():
        meta = raw.get("repo_metadata") or raw
        full_name = meta.get("full_name", repo_name)
        owner = meta.get("owner") or (full_name.split("/")[0] if "/" in full_name else cfg["org"])
        short = meta.get("repo", repo_name)

        if not owner:
            logger.info("Skip %s — no owner", repo_name)
            continue

        logger.info("Logging → %s/%s", owner, short)

        runs, truncated, accessible = fetch_workflow_runs(owner, short, since_date, cfg)
        if not accessible:
            raw["logging"] = {
                "available": False,
                "collected_at": now.isoformat(),
                "collector_version": COLLECTOR_VERSION,
                "error": "Workflow runs API not accessible",
            }
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(raw, fh, indent=2, default=str)
            continue

        metrics = compute_logging_metrics(runs)
        raw["logging"] = {
            "available": True,
            "collected_at": now.isoformat(),
            "collector_version": COLLECTOR_VERSION,
            "log_days": cfg["log_days"],
            "truncated": truncated,
            **metrics,
        }

        with open(path, "w", encoding="utf-8") as fh:
            json.dump(raw, fh, indent=2, default=str)
        enriched += 1

        # Accumulate org totals
        org_totals["total_runs"] += metrics["total_runs"]
        org_totals["success_count"] += metrics["success_count"]
        org_totals["failure_count"] += metrics["failure_count"]
        org_totals["per_repo"].append(
            {
                "repo": repo_name,
                "total_runs": metrics["total_runs"],
                "failure_rate": metrics["failure_rate"],
                "avg_duration_mins": metrics["avg_duration_mins"],
            }
        )

        logger.info(
            "  ✓ %d runs, fail_rate=%.2f%%, avg=%.1f min",
            metrics["total_runs"],
            metrics["failure_rate"] * 100,
            metrics["avg_duration_mins"] or 0,
        )

    # Write org-level summary
    total = org_totals["total_runs"]
    org_summary = {
        "source": "github_actions_logging",
        "collected_at": now.isoformat(),
        "collector_version": COLLECTOR_VERSION,
        "log_days": cfg["log_days"],
        "total_runs": total,
        "success_count": org_totals["success_count"],
        "failure_count": org_totals["failure_count"],
        "failure_rate": round(org_totals["failure_count"] / total, 4) if total else 0.0,
        "repos_scanned": len(repos),
        "repos_with_data": enriched,
        "per_repo": sorted(
            org_totals["per_repo"],
            key=lambda r: r.get("failure_rate", 0),
            reverse=True,
        ),
    }

    META_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = META_DIR / "logging_summary.json"
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(org_summary, fh, indent=2, default=str)

    logger.info(
        "Logging collection complete — %d/%d repos enriched, org summary at %s",
        enriched,
        len(repos),
        meta_path,
    )


if __name__ == "__main__":
    main()
