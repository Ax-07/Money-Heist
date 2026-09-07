from app.trading.risk import KillSwitch


def test_stop_new_trades_blocks_new_trades_without_stopping_ai() -> None:
    switch = KillSwitch()
    state = switch.stop_new_trades(reason="operator")
    assert state.blocks_new_trades is True
    assert state.stop_ai is False
    assert state.reason == "operator"


def test_stop_ai_alone_does_not_claim_to_block_trade_authorization() -> None:
    switch = KillSwitch()
    state = switch.stop_ai(reason="budget")
    assert state.stop_ai is True
    assert state.blocks_new_trades is False


def test_emergency_blocks_trading_and_ai() -> None:
    switch = KillSwitch()
    state = switch.emergency(reason="incident")
    assert state.blocks_new_trades is True
    assert state.stop_ai is True
    assert state.emergency_mode is True


def test_reset_restores_inactive_state() -> None:
    switch = KillSwitch()
    switch.emergency(reason="incident")
    state = switch.reset()
    assert state.blocks_new_trades is False
    assert state.stop_ai is False
