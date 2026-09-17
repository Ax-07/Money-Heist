from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence

from .models import PatternCandidateDiagnostic, PatternSourceSummary, PatternTypeSummary


def summarize_pattern_source(
    *, pivot_source: str, pivot_count: int, diagnostics: Sequence[PatternCandidateDiagnostic]
) -> PatternSourceSummary:
    accepted_by_type: Counter[str] = Counter()
    rejected_by_type: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    grouped: dict[str, list[PatternCandidateDiagnostic]] = defaultdict(list)
    for item in diagnostics:
        if item.pivot_source != pivot_source:
            raise ValueError("source summary received diagnostics from another pivot source")
        grouped[item.pattern_type].append(item)
        if item.accepted:
            accepted_by_type[item.pattern_type] += 1
        else:
            rejected_by_type[item.pattern_type] += 1
            reasons.update(reason.value for reason in item.rejection_reasons)

    per_pattern: list[PatternTypeSummary] = []
    for pattern_type, rows in sorted(grouped.items()):
        accepted = sum(item.accepted for item in rows)
        local_reasons: Counter[str] = Counter()
        for item in rows:
            if not item.accepted:
                local_reasons.update(reason.value for reason in item.rejection_reasons)
        total = len(rows)
        per_pattern.append(
            PatternTypeSummary(
                pattern_type=pattern_type,
                candidate_count=total,
                accepted_count=accepted,
                rejected_count=total - accepted,
                acceptance_ratio=accepted / total if total else 0.0,
                rejection_reason_counts=dict(sorted(local_reasons.items())),
            )
        )
    total = len(diagnostics)
    accepted = sum(item.accepted for item in diagnostics)
    return PatternSourceSummary(
        pivot_source=pivot_source,
        pivot_count=pivot_count,
        candidate_count=total,
        accepted_count=accepted,
        rejected_count=total - accepted,
        acceptance_ratio=accepted / total if total else 0.0,
        accepted_by_pattern_type=dict(sorted(accepted_by_type.items())),
        rejected_by_pattern_type=dict(sorted(rejected_by_type.items())),
        rejection_reason_counts=dict(sorted(reasons.items())),
        per_pattern=tuple(per_pattern),
    )
