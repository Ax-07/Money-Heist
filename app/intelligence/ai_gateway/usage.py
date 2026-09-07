from __future__ import annotations

from typing import Protocol

from .models import AIUsageRecord


class AIUsageRecorder(Protocol):
    async def record(self, usage: AIUsageRecord) -> None: ...


class InMemoryAIUsageRecorder:
    """Default recorder for tests/prototype use; replaceable by persistent storage later."""

    def __init__(self) -> None:
        self.records: list[AIUsageRecord] = []

    async def record(self, usage: AIUsageRecord) -> None:
        self.records.append(usage)
