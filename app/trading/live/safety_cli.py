from __future__ import annotations

import argparse
import json
import sys

from pydantic import ValidationError

from app.config.settings import Settings
from app.storage.database import Database

from .safety import LiveSafetyOperator, SqlAlchemyLiveSafetyStore
from .store import SqlAlchemyLiveAuditSink


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Money Heist LIVE safety operator control")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="read durable LIVE safety state")

    stop = sub.add_parser("stop-new-trades", help="block all new LIVE entries")
    stop.add_argument("--reason", required=True)

    emergency = sub.add_parser("emergency", help="block new entries and AI")
    emergency.add_argument("--reason", required=True)

    clear = sub.add_parser("clear", help="explicitly clear the durable LIVE safety block")
    clear.add_argument("--reason", required=True)
    clear.add_argument("--confirm", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = Settings()
    except ValidationError:
        print(json.dumps({"status": "BLOCKED", "reason": "SETTINGS_INVALID"}, indent=2))
        return 2

    system_id = settings.live_system_id or settings.default_system_id
    database = Database(settings.database_url)
    store = SqlAlchemyLiveSafetyStore(database.session_factory)
    audit = SqlAlchemyLiveAuditSink(database.session_factory)
    try:
        store.healthcheck()
        audit.healthcheck()
        operator = LiveSafetyOperator(store=store, audit=audit, system_id=system_id)
        if args.command == "status":
            state = store.snapshot(system_id=system_id)
            if state is None:
                output = {"status": "UNKNOWN", "system_id": system_id, "blocks_new_trades": True}
                code = 2
            else:
                output = {
                    "status": "KNOWN",
                    "system_id": system_id,
                    "stop_new_trades": state.stop_new_trades,
                    "stop_ai": state.stop_ai,
                    "emergency_mode": state.emergency_mode,
                    "reason": state.reason,
                    "blocks_new_trades": state.blocks_new_trades,
                }
                code = 0
        elif args.command == "stop-new-trades":
            state = operator.stop_new_trades(reason=args.reason)
            output = {"status": "STOPPED", "blocks_new_trades": state.blocks_new_trades}
            code = 0
        elif args.command == "emergency":
            state = operator.emergency(reason=args.reason)
            output = {"status": "EMERGENCY", "blocks_new_trades": state.blocks_new_trades}
            code = 0
        else:
            state = operator.clear(confirmation=args.confirm, reason=args.reason)
            output = {"status": "CLEAR", "blocks_new_trades": state.blocks_new_trades}
            code = 0
    except Exception:
        output = {"status": "BLOCKED", "reason": "LIVE_SAFETY_OPERATION_FAILED"}
        code = 2
    print(json.dumps(output, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
