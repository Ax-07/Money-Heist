from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.base import Base


class SystemRuntimeRecord(Base):
    __tablename__ = "system_runtime"

    system_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class LiveOrderPersistenceRecord(Base):
    """Durable LIVE order state used for crash recovery and reconciliation."""

    __tablename__ = "live_orders"

    client_order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_intent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_decision_id: Mapped[str] = mapped_column(String(64), nullable=False)
    system_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[str] = mapped_column(String(80), nullable=False)
    limit_price: Mapped[str | None] = mapped_column(String(80), nullable=True)
    intent_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    intent_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    external_order_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    exchange_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    filled_quantity: Mapped[str] = mapped_column(String(80), nullable=False, default="0")
    average_fill_price: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_live_orders_system_status", "system_id", "status"),
    )


class LiveFillPersistenceRecord(Base):
    __tablename__ = "live_fills"

    trade_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    client_order_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_order_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[str] = mapped_column(String(80), nullable=False)
    price: Mapped[str] = mapped_column(String(80), nullable=False)
    fee: Mapped[str] = mapped_column(String(80), nullable=False)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LiveAuditPersistenceRecord(Base):
    __tablename__ = "live_audit_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    system_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    client_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class LiveReconciliationPersistenceRecord(Base):
    __tablename__ = "live_reconciliation_state"

    system_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    reconciliation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_result: Mapped[str] = mapped_column(String(64), nullable=False, default="NEVER")
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LiveSafetyPersistenceRecord(Base):
    """Durable operator-controlled safety state for LIVE new entries."""

    __tablename__ = "live_safety_state"

    system_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    initialized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stop_new_trades: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    stop_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    emergency_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
