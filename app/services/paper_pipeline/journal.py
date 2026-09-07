from __future__ import annotations

from dataclasses import dataclass, field

from .models import PaperPipelineEvent


class JournalUnavailableError(RuntimeError):
    pass


@dataclass(slots=True)
class InMemoryPaperPipelineJournal:
    """Deterministic V1 journal matching the in-memory nature of PaperBroker."""

    available: bool = True
    _events: list[PaperPipelineEvent] = field(default_factory=list, init=False)
    _claimed_opportunities: set[str] = field(default_factory=set, init=False)
    _claimed_proposals: set[str] = field(default_factory=set, init=False)

    def preflight(self) -> None:
        if not self.available:
            raise JournalUnavailableError("paper pipeline journal is unavailable")

    def append(self, event: PaperPipelineEvent) -> None:
        self.preflight()
        self._events.append(event)

    def claim_execution(
        self,
        *,
        opportunity_id: str,
        proposal_id: str,
        source_snapshot_id: str,
    ) -> bool:
        del source_snapshot_id  # retained in the contract for durable journal implementations
        self.preflight()
        if opportunity_id in self._claimed_opportunities:
            return False
        if proposal_id in self._claimed_proposals:
            return False
        self._claimed_opportunities.add(opportunity_id)
        self._claimed_proposals.add(proposal_id)
        return True

    def events(self) -> tuple[PaperPipelineEvent, ...]:
        return tuple(self._events)
