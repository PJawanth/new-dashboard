"""
aggregator.schemas.validators
==============================
Runtime validation helpers that wrap the Pydantic schemas and return
detailed, human-readable error messages.

Usage::

    errors = assert_raw_repo(data_dict, repo="my-repo")
    if errors:
        for e in errors:
            print(e)

    errors = assert_dashboard(data_dict)
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import ValidationError

from aggregator.schemas.schema_dashboard import DashboardPayload
from aggregator.schemas.schema_raw_repo import RawRepoPayload


def _format_pydantic_errors(exc: ValidationError, label: str) -> List[str]:
    """Convert a ``ValidationError`` into a flat list of readable strings."""
    messages: List[str] = []
    for err in exc.errors():
        loc = " → ".join(str(p) for p in err["loc"])
        messages.append(f"[{label}] {loc}: {err['msg']} (type={err['type']})")
    return messages


# ── Raw repo validation ──────────────────────────────────────


def assert_raw_repo(data: Dict[str, Any], repo: str = "") -> List[str]:
    """Validate a per-repo raw JSON dict against ``RawRepoPayload``.

    Returns an empty list on success, or a list of error strings.
    """
    label = f"raw/{repo}" if repo else "raw-repo"
    errors: List[str] = []

    # Structural check — required top-level keys
    for key in ("repo_metadata", "collection"):
        if key not in data:
            errors.append(f"[{label}] missing required key: '{key}'")

    if "repo_metadata" in data:
        rm = data["repo_metadata"]
        if not isinstance(rm, dict):
            errors.append(f"[{label}] 'repo_metadata' must be an object")
        else:
            if not rm.get("repo"):
                errors.append(f"[{label}] 'repo_metadata.repo' is required")
            if not rm.get("full_name"):
                errors.append(f"[{label}] 'repo_metadata.full_name' is required")

    if "collection" in data:
        col = data["collection"]
        if not isinstance(col, dict):
            errors.append(f"[{label}] 'collection' must be an object")
        else:
            if not col.get("collected_at"):
                errors.append(f"[{label}] 'collection.collected_at' is required")
            if not col.get("lookback_days"):
                errors.append(f"[{label}] 'collection.lookback_days' is required")

    # Pydantic deep validation
    try:
        RawRepoPayload.model_validate(data)
    except ValidationError as exc:
        errors.extend(_format_pydantic_errors(exc, label))

    return errors


# ── Dashboard validation ─────────────────────────────────────


def assert_dashboard(data: Dict[str, Any]) -> List[str]:
    """Validate the aggregated ``dashboard.json`` against ``DashboardPayload``.

    Returns an empty list on success, or a list of error strings.
    """
    label = "dashboard.json"
    errors: List[str] = []

    # Structural: required top-level keys
    required_keys = ("metadata", "repos")
    for key in required_keys:
        if key not in data:
            errors.append(f"[{label}] missing required key: '{key}'")

    if "metadata" in data:
        md = data["metadata"]
        if not isinstance(md, dict):
            errors.append(f"[{label}] 'metadata' must be an object")
        else:
            for f in ("generated_at", "total_repos", "scanned_repos"):
                if f not in md:
                    errors.append(f"[{label}] 'metadata.{f}' is required")

    if "repos" in data:
        repos = data["repos"]
        if not isinstance(repos, list):
            errors.append(f"[{label}] 'repos' must be an array")
        else:
            for i, repo in enumerate(repos):
                if not isinstance(repo, dict):
                    errors.append(f"[{label}] repos[{i}] must be an object")
                elif not repo.get("name"):
                    errors.append(f"[{label}] repos[{i}].name is required")

    # Score bounds check
    scores = data.get("scores")
    if scores and isinstance(scores, dict):
        for field_name in ("engineering_health", "delivery", "quality", "security", "governance"):
            val = scores.get(field_name)
            if val is not None and not (0 <= val <= 100):
                errors.append(
                    f"[{label}] scores.{field_name}={val} is out of range [0, 100]"
                )

    # Pydantic deep validation
    try:
        DashboardPayload.model_validate(data)
    except ValidationError as exc:
        errors.extend(_format_pydantic_errors(exc, label))

    return errors
