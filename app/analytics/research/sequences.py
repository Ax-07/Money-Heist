from __future__ import annotations

from .contexts import AnalyticsContextResolver
from .models import (
    AnalyticsResearchRun,
    AnalyticsSequenceDefinition,
    AnalyticsSequenceMatch,
    ResolvedAnchor,
    SequenceStepMatch,
)
from .observation_index import AnalyticsObservationIndex


class AnalyticsSequenceResolver:
    """Resolve strict A THEN B sequences without inventing same-bar ordering.

    Matching policy v1: for each final occurrence, walk backwards and select the
    latest compatible predecessor in each `within_bars` window. This keeps the
    result deterministic and avoids combinatorial path expansion.
    """

    def __init__(self) -> None:
        self._contexts = AnalyticsContextResolver()

    def resolve(
        self,
        *,
        definition: AnalyticsSequenceDefinition,
        research_run: AnalyticsResearchRun,
        observation_index: AnalyticsObservationIndex,
        symbol: str,
        as_of,
    ) -> tuple[AnalyticsSequenceMatch, ...]:
        if research_run.revision_id != definition.revision_id:
            raise ValueError("research run revision does not match sequence definition")
        index = (
            observation_index.with_as_of(as_of)
            if as_of < observation_index.as_of
            else observation_index
        )
        rows = [
            index.anchor_candidates(step.anchor, symbol=symbol, as_of=as_of)
            for step in definition.steps
        ]
        if any(not item for item in rows):
            return ()

        matches: list[AnalyticsSequenceMatch] = []
        seen: set[str] = set()
        for final in rows[-1]:
            path: list[ResolvedAnchor] = [final]
            current = final
            valid = True
            for step_index in range(len(definition.steps) - 2, -1, -1):
                relation = definition.steps[step_index + 1]
                assert relation.within_bars is not None
                candidates: list[tuple[int, ResolvedAnchor]] = []
                for candidate in rows[step_index]:
                    if candidate.anchor_at >= current.anchor_at:
                        # Strict THEN: same bar is intentionally not ordered.
                        continue
                    distance = index.bar_distance(
                        symbol=symbol,
                        timeframe=definition.timeframe,
                        earlier=candidate.anchor_at,
                        later=current.anchor_at,
                    )
                    if distance is not None and 1 <= distance <= relation.within_bars:
                        candidates.append((distance, candidate))
                if not candidates:
                    valid = False
                    break
                _, current = min(
                    candidates,
                    key=lambda pair: (
                        pair[0],
                        -pair[1].anchor_at.timestamp(),
                        pair[1].source_ref,
                    ),
                )
                path.append(current)
            if not valid:
                continue
            path.reverse()

            final_condition_results = tuple(
                self._contexts.evaluate_condition(
                    condition,
                    anchor=path[-1],
                    observation_index=index,
                )
                for condition in definition.final_conditions
            )
            if not all(item.matched for item in final_condition_results):
                continue

            step_matches = tuple(
                SequenceStepMatch(
                    step_id=step.step_id,
                    source_type=anchor.source_type,
                    source_ref=anchor.source_ref,
                    occurred_at=anchor.anchor_at,
                    source_fingerprint=anchor.source_fingerprint,
                )
                for step, anchor in zip(definition.steps, path, strict=True)
            )
            match = AnalyticsSequenceMatch.create(
                research_run=research_run,
                definition=definition,
                symbol=symbol,
                step_matches=step_matches,
                final_condition_results=final_condition_results,
            )
            if match.match_id not in seen:
                seen.add(match.match_id)
                matches.append(match)

        matches.sort(key=lambda item: (item.completed_at, item.started_at, item.match_id))
        return tuple(matches)


__all__ = ["AnalyticsSequenceResolver"]
