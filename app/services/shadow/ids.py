from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5


_PREFIX = "money-heist:shadow:v1"


def _stable_uuid(kind: str, *parts: str) -> UUID:
    cleaned = tuple(str(part).strip() for part in parts)
    if any(not part for part in cleaned):
        raise ValueError(f"{kind} identity parts must not be empty")
    return uuid5(NAMESPACE_URL, ":".join((_PREFIX, kind, *cleaned)))


def root_correlation_id(root_opportunity_id: str, source_snapshot_id: str) -> str:
    """Stable id linking all SHADOW branches to the same root market event."""

    return str(_stable_uuid("root", root_opportunity_id, source_snapshot_id))


def derived_opportunity_id(root_opportunity_id: str, system_id: str) -> str:
    """Stable per-system opportunity id.

    Batch 09 derives PAPER client order idempotency from ``opportunity_id``. A
    distinct derived id therefore prevents one SHADOW twin from blocking the
    legitimate PAPER execution of another twin observing the same root event.
    """

    return str(_stable_uuid("opportunity", root_opportunity_id, system_id))


def branch_idempotency_key(
    *,
    root_opportunity_id: str,
    source_snapshot_id: str,
    system_id: str,
) -> str:
    return str(
        _stable_uuid(
            "idempotency",
            root_opportunity_id,
            source_snapshot_id,
            system_id,
        )
    )
