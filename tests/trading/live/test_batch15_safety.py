from app.storage.base import Base
from app.storage.database import Database
from app.trading.live.safety import LiveSafetyOperator, SqlAlchemyLiveSafetyStore
from app.trading.live.store import SqlAlchemyLiveAuditSink


def database(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'batch15-safety.db'}")
    Base.metadata.create_all(db.engine)
    return db


def test_missing_durable_safety_state_is_unknown_and_fail_closed(tmp_path):
    db = database(tmp_path)
    store = SqlAlchemyLiveSafetyStore(db.session_factory)
    assert store.snapshot(system_id="balanced_v1") is None


def test_operator_clear_requires_exact_confirmation_and_persists(tmp_path):
    db = database(tmp_path)
    store = SqlAlchemyLiveSafetyStore(db.session_factory)
    audit = SqlAlchemyLiveAuditSink(db.session_factory)
    operator = LiveSafetyOperator(store=store, audit=audit, system_id="balanced_v1")

    try:
        operator.clear(confirmation="yes", reason="validated before preflight")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid confirmation cleared LIVE safety")

    state = operator.clear(
        confirmation="CLEAR LIVE SAFETY balanced_v1",
        reason="validated before preflight",
    )
    assert not state.blocks_new_trades

    reconstructed = SqlAlchemyLiveSafetyStore(db.session_factory)
    restored = reconstructed.snapshot(system_id="balanced_v1")
    assert restored is not None
    assert not restored.blocks_new_trades


def test_stop_new_trades_and_emergency_are_durable(tmp_path):
    db = database(tmp_path)
    store = SqlAlchemyLiveSafetyStore(db.session_factory)
    audit = SqlAlchemyLiveAuditSink(db.session_factory)
    operator = LiveSafetyOperator(store=store, audit=audit, system_id="balanced_v1")
    operator.clear(
        confirmation="CLEAR LIVE SAFETY balanced_v1",
        reason="initial operator initialization",
    )

    stopped = operator.stop_new_trades(reason="operator stop")
    assert stopped.blocks_new_trades
    restored = SqlAlchemyLiveSafetyStore(db.session_factory).snapshot(system_id="balanced_v1")
    assert restored is not None and restored.stop_new_trades

    emergency = operator.emergency(reason="incident")
    assert emergency.emergency_mode
    assert emergency.stop_ai
    restored = SqlAlchemyLiveSafetyStore(db.session_factory).snapshot(system_id="balanced_v1")
    assert restored is not None and restored.emergency_mode and restored.stop_ai
