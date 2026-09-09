from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

import pytest

from app.portfolio import (
    AllocationEnvelopeStatus,
    AllocationPolicySource,
    CrewAllocationEnvelope,
    MasterAllocationPolicy,
    PortfolioMemberRef,
    build_master_allocation_policy,
)


def member(system_id: str, *, membership_ref: str | None = None) -> PortfolioMemberRef:
    return PortfolioMemberRef(
        system_id=system_id,
        membership_ref=membership_ref or f"member:{system_id}",
    )


def configured_envelope(
    system_id: str,
    *,
    capital: str = "50",
    risk: str = "5",
    gross: str = "100",
) -> CrewAllocationEnvelope:
    return CrewAllocationEnvelope(
        system_id=system_id,
        status=AllocationEnvelopeStatus.CONFIGURED,
        capital_ceiling_amount=Decimal(capital),
        open_risk_ceiling_amount=Decimal(risk),
        gross_exposure_ceiling_amount=Decimal(gross),
    )


def not_configured_envelope(
    system_id: str,
    *,
    reason_code: str = "OPERATOR_CONFIGURATION_REQUIRED",
) -> CrewAllocationEnvelope:
    return CrewAllocationEnvelope(
        system_id=system_id,
        status=AllocationEnvelopeStatus.NOT_CONFIGURED,
        reason_code=reason_code,
    )


def policy(*, reverse_input: bool = False):
    members = (member("crew-a"), member("crew-b"))
    envelopes = (
        configured_envelope("crew-a", capital="60", risk="4", gross="120"),
        configured_envelope("crew-b", capital="60", risk="3", gross="80"),
    )
    if reverse_input:
        members = tuple(reversed(members))
        envelopes = tuple(reversed(envelopes))
    return build_master_allocation_policy(
        master_portfolio_id="master-main",
        policy_id="static-v1",
        members=members,
        envelopes=envelopes,
        source_ref="operator-config:static-v1",
    )


def test_configured_policy_is_canonical_and_operator_owned() -> None:
    result = policy(reverse_input=True)

    assert result.status is AllocationEnvelopeStatus.CONFIGURED
    assert tuple(member.system_id for member in result.members) == ("crew-a", "crew-b")
    assert tuple(envelope.system_id for envelope in result.envelopes) == ("crew-a", "crew-b")
    assert result.source is AllocationPolicySource.OPERATOR_CONFIGURATION
    assert result.reason_codes == ()


def test_envelope_ceilings_are_not_normalized_or_split_from_master_capital() -> None:
    result = policy()

    assert result.envelopes[0].capital_ceiling_amount == Decimal("60")
    assert result.envelopes[1].capital_ceiling_amount == Decimal("60")
    assert sum(envelope.capital_ceiling_amount or 0 for envelope in result.envelopes) == 120
    assert not hasattr(result, "allocated_capital_total")
    assert not hasattr(result, "master_equity")


def test_configured_envelope_requires_every_operator_ceiling() -> None:
    with pytest.raises(ValueError, match="requires every ceiling"):
        CrewAllocationEnvelope(
            system_id="crew-a",
            status=AllocationEnvelopeStatus.CONFIGURED,
            capital_ceiling_amount=Decimal("50"),
            open_risk_ceiling_amount=Decimal("5"),
        )


def test_configured_envelope_rejects_reason_code() -> None:
    with pytest.raises(ValueError, match="cannot carry reason_code"):
        CrewAllocationEnvelope(
            system_id="crew-a",
            status=AllocationEnvelopeStatus.CONFIGURED,
            capital_ceiling_amount=Decimal("50"),
            open_risk_ceiling_amount=Decimal("5"),
            gross_exposure_ceiling_amount=Decimal("100"),
            reason_code="NOT_NEEDED",
        )


def test_not_configured_envelope_requires_reason_and_carries_no_numbers() -> None:
    with pytest.raises(ValueError, match="requires reason_code"):
        CrewAllocationEnvelope(
            system_id="crew-a",
            status=AllocationEnvelopeStatus.NOT_CONFIGURED,
        )

    with pytest.raises(ValueError, match="cannot carry numeric ceilings"):
        CrewAllocationEnvelope(
            system_id="crew-a",
            status=AllocationEnvelopeStatus.NOT_CONFIGURED,
            capital_ceiling_amount=Decimal("50"),
            reason_code="MISSING_OTHER_LIMITS",
        )


def test_envelope_rejects_negative_or_non_finite_ceilings() -> None:
    with pytest.raises(ValueError, match="finite and >= 0"):
        configured_envelope("crew-a", capital="-1")
    with pytest.raises(ValueError, match="finite and >= 0"):
        configured_envelope("crew-a", risk="NaN")
    with pytest.raises(ValueError, match="finite and >= 0"):
        configured_envelope("crew-a", gross="Infinity")


def test_zero_ceilings_are_valid_explicit_operator_configuration() -> None:
    envelope = configured_envelope("crew-a", capital="0", risk="0", gross="0")

    assert envelope.capital_ceiling_amount == Decimal("0")
    assert envelope.open_risk_ceiling_amount == Decimal("0")
    assert envelope.gross_exposure_ceiling_amount == Decimal("0")


def test_policy_rejects_duplicate_or_missing_crew_envelopes() -> None:
    with pytest.raises(ValueError, match="envelope system_id values must be unique"):
        build_master_allocation_policy(
            master_portfolio_id="master-main",
            policy_id="static-v1",
            members=(member("crew-a"), member("crew-b")),
            envelopes=(configured_envelope("crew-a"), configured_envelope("crew-a")),
        )

    with pytest.raises(ValueError, match="requires exactly one envelope"):
        build_master_allocation_policy(
            master_portfolio_id="master-main",
            policy_id="static-v1",
            members=(member("crew-a"), member("crew-b")),
            envelopes=(configured_envelope("crew-a"),),
        )


def test_not_configured_crew_makes_policy_fail_closed() -> None:
    result = build_master_allocation_policy(
        master_portfolio_id="master-main",
        policy_id="static-v1",
        members=(member("crew-a"), member("crew-b")),
        envelopes=(
            configured_envelope("crew-a"),
            not_configured_envelope("crew-b"),
        ),
        source_ref="operator-config:static-v1",
    )

    assert result.status is AllocationEnvelopeStatus.NOT_CONFIGURED
    assert result.reason_codes == (
        "ALLOCATION_ENVELOPE_NOT_CONFIGURED:crew-b:OPERATOR_CONFIGURATION_REQUIRED",
    )


def test_input_order_does_not_change_policy_fingerprint() -> None:
    assert policy().fingerprint_sha256 == policy(reverse_input=True).fingerprint_sha256


def test_material_ceiling_change_changes_policy_fingerprint() -> None:
    baseline = policy()
    changed = build_master_allocation_policy(
        master_portfolio_id="master-main",
        policy_id="static-v1",
        members=baseline.members,
        envelopes=(
            configured_envelope("crew-a", capital="61", risk="4", gross="120"),
            configured_envelope("crew-b", capital="60", risk="3", gross="80"),
        ),
        source_ref="operator-config:static-v1",
    )

    assert changed.fingerprint_sha256 != baseline.fingerprint_sha256


def test_membership_provenance_change_changes_policy_fingerprint() -> None:
    baseline = policy()
    changed = build_master_allocation_policy(
        master_portfolio_id="master-main",
        policy_id="static-v1",
        members=(
            member("crew-a", membership_ref="member:crew-a:revision-2"),
            member("crew-b"),
        ),
        envelopes=baseline.envelopes,
        source_ref="operator-config:static-v1",
    )

    assert changed.fingerprint_sha256 != baseline.fingerprint_sha256


def test_policy_is_immutable_and_has_no_automatic_authority() -> None:
    result = policy()

    assert result.auto_apply is False
    assert result.dynamic_allocation is False
    assert result.reservation_authority is False
    assert result.admission_authority is False
    assert result.risk_authority is False
    assert result.registry_mutation is False
    assert result.live_authority is False
    with pytest.raises(FrozenInstanceError):
        result.policy_id = "changed"  # type: ignore[misc]


def test_policy_detects_tampered_fingerprint() -> None:
    result = policy()

    with pytest.raises(ValueError, match="fingerprint does not match payload"):
        replace(result, fingerprint_sha256="0" * 64)


def test_policy_detects_tampered_status() -> None:
    result = policy()

    with pytest.raises(ValueError, match="status does not match"):
        replace(result, status=AllocationEnvelopeStatus.NOT_CONFIGURED)


def test_policy_type_cannot_be_constructed_with_non_operator_source() -> None:
    result = policy()

    with pytest.raises(TypeError):
        MasterAllocationPolicy(
            master_portfolio_id=result.master_portfolio_id,
            policy_id=result.policy_id,
            members=result.members,
            envelopes=result.envelopes,
            status=result.status,
            reason_codes=result.reason_codes,
            fingerprint_sha256=result.fingerprint_sha256,
            source=AllocationPolicySource.OPERATOR_CONFIGURATION,  # type: ignore[call-arg]
        )
