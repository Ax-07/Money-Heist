from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.storage.models import LiveSafetyPersistenceRecord
from app.trading.risk.models import KillSwitchState

from .models import LiveAuditEvent
from .ports import LiveAuditSink


class SqlAlchemyLiveSafetyStore:
    """Durable human-controlled safety state for LIVE new entries.

    Missing state is deliberately UNKNOWN. Initialization/clearing is an
    explicit operator action and is independent from LIVE arming.
    """

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def healthcheck(self) -> bool:
        with self._session_factory() as session:
            session.execute(select(LiveSafetyPersistenceRecord.system_id).limit(1))
        return True

    def snapshot(self, *, system_id: str) -> KillSwitchState | None:
        with self._session_factory() as session:
            row = session.get(LiveSafetyPersistenceRecord, system_id)
            if row is None or not row.initialized:
                return None
            return KillSwitchState(
                stop_new_trades=bool(row.stop_new_trades),
                stop_ai=bool(row.stop_ai),
                emergency_mode=bool(row.emergency_mode),
                reason=row.reason,
                activated_at=_utc_or_none(row.activated_at),
            )

    def clear_for_new_entries(self, *, system_id: str, reason: str) -> KillSwitchState:
        if not reason.strip():
            raise ValueError("reason must not be blank")
        now = datetime.now(timezone.utc)
        self._write(
            system_id=system_id,
            initialized=True,
            stop_new_trades=False,
            stop_ai=False,
            emergency_mode=False,
            reason=reason,
            activated_at=None,
            updated_at=now,
        )
        return self.snapshot(system_id=system_id) or KillSwitchState(stop_new_trades=True)

    def stop_new_trades(self, *, system_id: str, reason: str) -> KillSwitchState:
        if not reason.strip():
            raise ValueError("reason must not be blank")
        now = datetime.now(timezone.utc)
        current = self.snapshot(system_id=system_id)
        self._write(
            system_id=system_id,
            initialized=True,
            stop_new_trades=True,
            stop_ai=current.stop_ai if current is not None else False,
            emergency_mode=current.emergency_mode if current is not None else False,
            reason=reason,
            activated_at=now,
            updated_at=now,
        )
        return self.snapshot(system_id=system_id) or KillSwitchState(stop_new_trades=True)

    def emergency(self, *, system_id: str, reason: str) -> KillSwitchState:
        if not reason.strip():
            raise ValueError("reason must not be blank")
        now = datetime.now(timezone.utc)
        self._write(
            system_id=system_id,
            initialized=True,
            stop_new_trades=True,
            stop_ai=True,
            emergency_mode=True,
            reason=reason,
            activated_at=now,
            updated_at=now,
        )
        return self.snapshot(system_id=system_id) or KillSwitchState(
            stop_new_trades=True,
            stop_ai=True,
            emergency_mode=True,
        )

    def _write(self, *, system_id: str, **values: object) -> None:
        if not system_id.strip():
            raise ValueError("system_id must not be blank")
        with self._session_factory.begin() as session:
            row = session.get(LiveSafetyPersistenceRecord, system_id)
            if row is None:
                session.add(LiveSafetyPersistenceRecord(system_id=system_id, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)


class LiveSafetyOperator:
    """Audited operator commands. No agent-facing integration is provided."""

    def __init__(
        self,
        *,
        store: SqlAlchemyLiveSafetyStore,
        audit: LiveAuditSink,
        system_id: str,
        now=lambda: datetime.now(timezone.utc),
    ) -> None:
        self._store = store
        self._audit = audit
        self._system_id = system_id
        self._now = now

    @property
    def clear_confirmation(self) -> str:
        return f"CLEAR LIVE SAFETY {self._system_id}"

    def clear(self, *, confirmation: str, reason: str) -> KillSwitchState:
        if confirmation != self.clear_confirmation:
            raise ValueError("operator confirmation does not match the required phrase")
        state = self._store.clear_for_new_entries(system_id=self._system_id, reason=reason)
        self._event("LIVE_SAFETY_CLEARED", "CRITICAL", reason=reason)
        return state

    def stop_new_trades(self, *, reason: str) -> KillSwitchState:
        state = self._store.stop_new_trades(system_id=self._system_id, reason=reason)
        self._event("LIVE_STOP_NEW_TRADES", "CRITICAL", reason=reason)
        return state

    def emergency(self, *, reason: str) -> KillSwitchState:
        state = self._store.emergency(system_id=self._system_id, reason=reason)
        self._event("LIVE_EMERGENCY_MODE", "CRITICAL", reason=reason)
        return state

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


def _utc_or_none(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        # SQLite may deserialize timezone-aware values as naive. Persisted
        # project timestamps are specified as UTC, so restore that contract.
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
