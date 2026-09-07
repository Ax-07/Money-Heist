from __future__ import annotations

from uuid import UUID

from app.services.shadow import (
    AGGRESSIVE_TOKYO,
    BALANCED,
    CONSERVATIVE_VAULT,
    DEFAULT_SHADOW_SYSTEMS,
    ShadowSystemFamily,
    branch_idempotency_key,
    default_shadow_systems,
    derived_opportunity_id,
    root_correlation_id,
)

ROOT_OPPORTUNITY_ID = "70000000-0000-0000-0000-000000000011"
SNAPSHOT_ID = "snapshot-shadow-root-11"


def test_three_stable_shadow_identities_exist_in_required_order():
    systems = default_shadow_systems()
    assert systems == DEFAULT_SHADOW_SYSTEMS
    assert systems == (CONSERVATIVE_VAULT, BALANCED, AGGRESSIVE_TOKYO)
    assert tuple(item.family for item in systems) == (
        ShadowSystemFamily.CONSERVATIVE,
        ShadowSystemFamily.BALANCED,
        ShadowSystemFamily.AGGRESSIVE,
    )
    assert tuple(item.execution_order for item in systems) == (10, 20, 30)


def test_vault_and_tokyo_are_aliases_not_risk_presets():
    assert CONSERVATIVE_VAULT.aliases == ("Vault",)
    assert AGGRESSIVE_TOKYO.aliases == ("Tokyo",)
    for identity in DEFAULT_SHADOW_SYSTEMS:
        assert identity.mode == "SHADOW"
        assert not hasattr(identity, "max_risk_per_trade_pct")
        assert not hasattr(identity, "max_leverage")


def test_system_ids_are_distinct_and_stable():
    ids = tuple(item.system_id for item in DEFAULT_SHADOW_SYSTEMS)
    assert ids == (
        "shadow_conservative_vault_v1",
        "shadow_balanced_v1",
        "shadow_aggressive_tokyo_v1",
    )
    assert len(ids) == len(set(ids)) == 3


def test_root_correlation_is_common_and_deterministic():
    first = root_correlation_id(ROOT_OPPORTUNITY_ID, SNAPSHOT_ID)
    second = root_correlation_id(ROOT_OPPORTUNITY_ID, SNAPSHOT_ID)
    assert first == second
    UUID(first)


def test_derived_opportunity_ids_are_deterministic_and_system_scoped():
    ids = {
        identity.system_id: derived_opportunity_id(ROOT_OPPORTUNITY_ID, identity.system_id)
        for identity in DEFAULT_SHADOW_SYSTEMS
    }
    assert len(set(ids.values())) == 3
    for identity in DEFAULT_SHADOW_SYSTEMS:
        assert ids[identity.system_id] == derived_opportunity_id(
            ROOT_OPPORTUNITY_ID, identity.system_id
        )
        UUID(ids[identity.system_id])


def test_branch_idempotency_keys_are_deterministic_and_system_scoped():
    keys = [
        branch_idempotency_key(
            root_opportunity_id=ROOT_OPPORTUNITY_ID,
            source_snapshot_id=SNAPSHOT_ID,
            system_id=identity.system_id,
        )
        for identity in DEFAULT_SHADOW_SYSTEMS
    ]
    assert len(set(keys)) == 3
    for key in keys:
        UUID(key)


def test_changing_root_event_changes_all_derived_ids():
    old = derived_opportunity_id(ROOT_OPPORTUNITY_ID, BALANCED.system_id)
    new = derived_opportunity_id(
        "70000000-0000-0000-0000-000000000012", BALANCED.system_id
    )
    assert old != new
