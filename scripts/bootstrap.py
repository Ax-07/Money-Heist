import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from app.config.settings import get_settings  # noqa: E402
from app.observability.logging import configure_logging  # noqa: E402
from app.storage.database import Database  # noqa: E402


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    alembic_cfg = Config(PROJECT_ROOT / "alembic.ini")
    command.upgrade(alembic_cfg, "head")

    database = Database(settings.database_url)
    try:
        record = database.upsert_system_runtime(
            system_id=settings.default_system_id,
            mode=settings.runtime_mode,
        )
        system_id = record.system_id
        mode = record.mode
    finally:
        database.dispose()

    print(
        f"Bootstrap terminé: system_id={system_id}, mode={mode}, "
        f"database={settings.database_url}"
    )


if __name__ == "__main__":
    main()
