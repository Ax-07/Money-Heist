from __future__ import annotations

from typing import Any

from app.common.canonical import canonical_json, stable_digest, stable_uuid


def analytics_identity_sha256(payload: Any) -> str:
    return stable_digest(payload)


def analytics_run_id(payload: Any) -> str:
    return stable_uuid("analytics-lab-run", payload)


def analytics_snapshot_id(payload: Any) -> str:
    return stable_uuid("analytics-snapshot", payload)


__all__ = [
    "analytics_identity_sha256",
    "analytics_run_id",
    "analytics_snapshot_id",
    "canonical_json",
    "stable_digest",
]
