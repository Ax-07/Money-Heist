from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.enums import SystemMode
from app.storage.models import SystemRuntimeRecord


class Database:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._ensure_sqlite_parent_directory()
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )

    def _ensure_sqlite_parent_directory(self) -> None:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            return
        raw_path = self.database_url.removeprefix(prefix)
        if raw_path == ":memory:":
            return
        path = Path(raw_path)
        path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self.session_factory() as session:
            yield session

    def ping(self) -> bool:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True

    def upsert_system_runtime(self, system_id: str, mode: SystemMode) -> SystemRuntimeRecord:
        with self.session_factory.begin() as session:
            record = session.scalar(
                select(SystemRuntimeRecord).where(SystemRuntimeRecord.system_id == system_id)
            )
            if record is None:
                record = SystemRuntimeRecord(system_id=system_id, mode=mode.value)
                session.add(record)
            else:
                record.mode = mode.value
            session.flush()
            session.refresh(record)
            return record

    def dispose(self) -> None:
        self.engine.dispose()
