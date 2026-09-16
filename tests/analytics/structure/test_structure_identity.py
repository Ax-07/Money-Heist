from app.analytics.structure import ANALYTICS_STRUCTURE_IDENTITY
from app.market.structure import MARKET_STRUCTURE_VERSION


def test_structure_identity_includes_production_definition_version() -> None:
    assert MARKET_STRUCTURE_VERSION in ANALYTICS_STRUCTURE_IDENTITY
