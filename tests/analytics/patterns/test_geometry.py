from app.analytics.patterns.engine import _classify_geometry
from app.analytics.patterns.registry import PatternType


def test_geometry_family_classification():
    assert _classify_geometry(0.0, 0.08, 0.7)[0] == PatternType.ASCENDING_TRIANGLE
    assert _classify_geometry(-0.08, 0.0, 0.7)[0] == PatternType.DESCENDING_TRIANGLE
    assert _classify_geometry(-0.08, 0.08, 0.7)[0] == PatternType.SYMMETRICAL_TRIANGLE
    assert _classify_geometry(0.06, 0.12, 0.7)[0] == PatternType.RISING_WEDGE
    assert _classify_geometry(-0.12, -0.06, 0.7)[0] == PatternType.FALLING_WEDGE
    assert _classify_geometry(0.08, 0.075, 1.0)[0] == PatternType.ASCENDING_CHANNEL
    assert _classify_geometry(-0.08, -0.075, 1.0)[0] == PatternType.DESCENDING_CHANNEL
    assert _classify_geometry(0.0, 0.0, 1.0)[0] == PatternType.RANGE


def test_non_converging_triangle_is_rejected():
    assert _classify_geometry(-0.08, 0.08, 0.95) is None
