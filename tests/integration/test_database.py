from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select

from app.config.settings import Settings, get_settings
from app.domain.enums import SystemMode
from app.storage.database import Database
from app.storage.models import SystemRuntimeRecord


def test_alembic_migration_and_runtime_upsert(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "migration.db"
    monkeypatch.setenv("MONEY_HEIST_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("MONEY_HEIST_RUNTIME_MODE", "PAPER")
    monkeypatch.setenv("MONEY_HEIST_APP_ENV", "test")
    get_settings.cache_clear()

    config = Config("alembic.ini")
    command.upgrade(config, "head")

    settings = Settings(_env_file=None)
    database = Database(settings.database_url)
    try:
        assert "system_runtime" in inspect(database.engine).get_table_names()

        database.upsert_system_runtime("balanced_v1", SystemMode.PAPER)
        with database.session_factory() as session:
            record = session.scalar(
                select(SystemRuntimeRecord).where(
                    SystemRuntimeRecord.system_id == "balanced_v1"
                )
            )
            assert record is not None
            assert record.mode == "PAPER"
    finally:
        database.dispose()
