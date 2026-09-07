from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from .models import LiveAuditEvent
from .ports import LiveAuditSink


@dataclass(frozen=True, slots=True)
class LiveAuthorization:
    authorized: bool
    source: str
    reason: str


class LiveAuthorizationProvider(Protocol):
    def get_authorization(self, *, system_id: str) -> LiveAuthorization: ...


class DenyAllLiveAuthorization:
    """Safe default. Credentials/configuration never imply LIVE authorization."""

    def get_authorization(self, *, system_id: str) -> LiveAuthorization:
        return LiveAuthorization(
            authorized=False,
            source="structural_lock",
            reason="LIVE requires Batch 15 preflight and an explicit operator arm",
        )


@dataclass(frozen=True, slots=True)
class StaticLiveAuthorization:
    """Injection-only helper for deterministic tests; never wired from environment."""

    authorized: bool
    source: str = "injected_test_authorization"
    reason: str = "explicit test fixture"

    def get_authorization(self, *, system_id: str) -> LiveAuthorization:
        return LiveAuthorization(self.authorized, self.source, self.reason)


class LiveOperationalState(StrEnum):
    LIVE_DISABLED = "LIVE_DISABLED"
    LIVE_PREFLIGHT = "LIVE_PREFLIGHT"
    LIVE_ARMED = "LIVE_ARMED"


class LiveActivationError(RuntimeError):
    pass


class LiveActivationController:
    """Process-local operator authorization.

    The armed state is intentionally never persisted. Constructing a new
    controller (including after every restart) always yields LIVE_DISABLED.
    An agent receives neither this controller nor the operator confirmation.
    """

    def __init__(
        self,
        *,
        system_id: str,
        audit: LiveAuditSink,
        now=lambda: datetime.now(timezone.utc),
    ) -> None:
        if not system_id.strip():
            raise ValueError("system_id must not be blank")
        self._system_id = system_id
        self._audit = audit
        self._now = now
        self._state = LiveOperationalState.LIVE_DISABLED
        self._session_id: str | None = None
        self._preflight_fingerprint: str | None = None

    @property
    def state(self) -> LiveOperationalState:
        return self._state

    @property
    def system_id(self) -> str:
        return self._system_id

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def expected_confirmation(self) -> str:
        return f"ARM LIVE {self._system_id}"

    def begin_preflight(self) -> None:
        self._state = LiveOperationalState.LIVE_PREFLIGHT
        self._session_id = None
        self._preflight_fingerprint = None
        self._event("LIVE_PREFLIGHT_ENTERED", "INFO")

    def arm(self, *, report, operator_confirmation: str) -> str:
        """Arm this process only after a READY report and exact human confirmation."""

        from .preflight import LivePreflightStatus

        if self._state is not LiveOperationalState.LIVE_PREFLIGHT:
            raise LiveActivationError("LIVE can only be armed from LIVE_PREFLIGHT")
        if report.system_id != self._system_id:
            raise LiveActivationError("preflight report belongs to another system")
        if report.status is not LivePreflightStatus.READY:
            raise LiveActivationError("BLOCKED preflight cannot arm LIVE")
        if operator_confirmation != self.expected_confirmation:
            raise LiveActivationError("operator confirmation does not match the required phrase")

        self._session_id = str(uuid4())
        self._preflight_fingerprint = report.fingerprint
        self._state = LiveOperationalState.LIVE_ARMED
        self._event(
            "LIVE_ARMED",
            "CRITICAL",
            session_id=self._session_id,
            preflight_fingerprint=report.fingerprint,
        )
        return self._session_id

    def disarm(self, *, reason: str) -> None:
        if not reason.strip():
            raise ValueError("disarm reason must not be blank")
        previous = self._state
        self._state = LiveOperationalState.LIVE_DISABLED
        self._session_id = None
        self._preflight_fingerprint = None
        self._event("LIVE_DISARMED", "CRITICAL", previous_state=previous.value, reason=reason)

    def get_authorization(self, *, system_id: str) -> LiveAuthorization:
        if system_id != self._system_id:
            return LiveAuthorization(False, "batch15_operator_arm", "system_id is not armed")
        if self._state is not LiveOperationalState.LIVE_ARMED:
            return LiveAuthorization(False, "batch15_operator_arm", "LIVE is not armed")
        if self._session_id is None or self._preflight_fingerprint is None:
            return LiveAuthorization(False, "batch15_operator_arm", "arm state is incomplete")
        return LiveAuthorization(True, "batch15_operator_arm", "explicit operator arm is active")

    def _event(self, event_type: str, severity: str, **details: str) -> None:
        self._audit.record(
            LiveAuditEvent(
                event_type=event_type,
                severity=severity,
                system_id=self._system_id,
                client_order_id=None,
                created_at=self._utc_now(),
                details=details,
            )
        )

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("clock must be timezone-aware")
        return value.astimezone(timezone.utc)
