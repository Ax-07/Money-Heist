"""Persist LIVE orders, fills, reconciliation, audit and safety state.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "live_orders",
        sa.Column("client_order_id", sa.String(length=64), nullable=False),
        sa.Column("order_intent_id", sa.String(length=64), nullable=False),
        sa.Column("risk_decision_id", sa.String(length=64), nullable=False),
        sa.Column("system_id", sa.String(length=100), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.String(length=80), nullable=False),
        sa.Column("limit_price", sa.String(length=80), nullable=True),
        sa.Column("intent_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("intent_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("external_order_id", sa.String(length=128), nullable=True),
        sa.Column("exchange_status", sa.String(length=64), nullable=True),
        sa.Column("filled_quantity", sa.String(length=80), nullable=False),
        sa.Column("average_fill_price", sa.String(length=80), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("client_order_id"),
    )
    op.create_index("ix_live_orders_system_id", "live_orders", ["system_id"], unique=False)
    op.create_index(
        "ix_live_orders_external_order_id",
        "live_orders",
        ["external_order_id"],
        unique=False,
    )
    op.create_index(
        "ix_live_orders_system_status",
        "live_orders",
        ["system_id", "status"],
        unique=False,
    )

    op.create_table(
        "live_fills",
        sa.Column("trade_id", sa.String(length=128), nullable=False),
        sa.Column("client_order_id", sa.String(length=64), nullable=False),
        sa.Column("external_order_id", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.String(length=80), nullable=False),
        sa.Column("price", sa.String(length=80), nullable=False),
        sa.Column("fee", sa.String(length=80), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("trade_id"),
    )
    op.create_index(
        "ix_live_fills_client_order_id", "live_fills", ["client_order_id"], unique=False
    )
    op.create_index(
        "ix_live_fills_external_order_id",
        "live_fills",
        ["external_order_id"],
        unique=False,
    )

    op.create_table(
        "live_audit_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("system_id", sa.String(length=100), nullable=False),
        sa.Column("client_order_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_live_audit_events_event_type",
        "live_audit_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_live_audit_events_system_id",
        "live_audit_events",
        ["system_id"],
        unique=False,
    )
    op.create_index(
        "ix_live_audit_events_client_order_id",
        "live_audit_events",
        ["client_order_id"],
        unique=False,
    )

    op.create_table(
        "live_reconciliation_state",
        sa.Column("system_id", sa.String(length=100), nullable=False),
        sa.Column("reconciliation_required", sa.Boolean(), nullable=False),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_result", sa.String(length=64), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("system_id"),
    )

    op.create_table(
        "live_safety_state",
        sa.Column("system_id", sa.String(length=100), nullable=False),
        sa.Column("initialized", sa.Boolean(), nullable=False),
        sa.Column("stop_new_trades", sa.Boolean(), nullable=False),
        sa.Column("stop_ai", sa.Boolean(), nullable=False),
        sa.Column("emergency_mode", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("system_id"),
    )


def downgrade() -> None:
    op.drop_table("live_safety_state")
    op.drop_table("live_reconciliation_state")
    op.drop_index("ix_live_audit_events_client_order_id", table_name="live_audit_events")
    op.drop_index("ix_live_audit_events_system_id", table_name="live_audit_events")
    op.drop_index("ix_live_audit_events_event_type", table_name="live_audit_events")
    op.drop_table("live_audit_events")
    op.drop_index("ix_live_fills_external_order_id", table_name="live_fills")
    op.drop_index("ix_live_fills_client_order_id", table_name="live_fills")
    op.drop_table("live_fills")
    op.drop_index("ix_live_orders_system_status", table_name="live_orders")
    op.drop_index("ix_live_orders_external_order_id", table_name="live_orders")
    op.drop_index("ix_live_orders_system_id", table_name="live_orders")
    op.drop_table("live_orders")
