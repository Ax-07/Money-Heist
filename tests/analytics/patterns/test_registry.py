from app.analytics.patterns.registry import (
    ANALYTICS_PATTERN_INTRABAR_POLICY_VERSION,
    ANALYTICS_PATTERN_REGISTRY_FINGERPRINT,
    PATTERN_DEFINITIONS,
    PatternType,
)


def test_registry_contains_exact_initial_catalog_and_is_experimental():
    assert {item.pattern_type for item in PATTERN_DEFINITIONS} == set(PatternType)
    assert len(PATTERN_DEFINITIONS) == 12
    assert all(item.experimental for item in PATTERN_DEFINITIONS)
    assert all(item.minimum_pivots in {3, 5, 6} for item in PATTERN_DEFINITIONS)


def test_registry_exposes_geometry_lifecycle_and_source_contracts():
    for definition in PATTERN_DEFINITIONS:
        assert definition.geometry_constraints
        assert definition.atr_normalization_rules
        assert definition.breakout_semantics
        assert definition.lifecycle_rules
        assert definition.source_requirements
        assert definition.parameter_names


def test_registry_identity_material_is_explicit():
    assert ANALYTICS_PATTERN_INTRABAR_POLICY_VERSION.endswith("conservative.v1")
    assert len(ANALYTICS_PATTERN_REGISTRY_FINGERPRINT) == 64
