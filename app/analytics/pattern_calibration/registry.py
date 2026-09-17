from __future__ import annotations

from dataclasses import dataclass

from app.analytics.patterns.registry import ANALYTICS_PATTERN_REGISTRY_IDENTITY
from app.analytics.structure import StructureSource
from app.market.structure import MARKET_STRUCTURE_VERSION

PATTERN_CALIBRATION_VERSION = "money-heist.pattern-calibration.v1"
PATTERN_REJECTION_TAXONOMY_VERSION = "money-heist.pattern-rejection-taxonomy.v1"
PATTERN_COMPARISON_SEMANTICS_VERSION = "money-heist.pattern-source-comparison.v1"
MONEY_HEIST_STRUCTURE_PIVOT_ADAPTER_VERSION = "money-heist.structure-pattern-pivots.v1"


@dataclass(frozen=True, slots=True)
class PatternCalibrationDefinition:
    version: str
    rejection_taxonomy_version: str
    comparison_semantics_version: str
    pattern_registry_identity: str
    supported_sources: tuple[StructureSource, ...]
    structure_adapter_version: str
    production_structure_version: str


PATTERN_CALIBRATION_DEFINITION = PatternCalibrationDefinition(
    version=PATTERN_CALIBRATION_VERSION,
    rejection_taxonomy_version=PATTERN_REJECTION_TAXONOMY_VERSION,
    comparison_semantics_version=PATTERN_COMPARISON_SEMANTICS_VERSION,
    pattern_registry_identity=ANALYTICS_PATTERN_REGISTRY_IDENTITY,
    supported_sources=(StructureSource.MONEY_HEIST_STRUCTURE, StructureSource.CAUSAL_ZIGZAG),
    structure_adapter_version=MONEY_HEIST_STRUCTURE_PIVOT_ADAPTER_VERSION,
    production_structure_version=MARKET_STRUCTURE_VERSION,
)
