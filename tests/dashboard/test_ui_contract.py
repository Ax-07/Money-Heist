from pathlib import Path


STATIC = Path(__file__).resolve().parents[2] / "app" / "dashboard" / "static"


def test_frontend_only_fetches_dashboard_overview_with_get():
    js = (STATIC / "dashboard.js").read_text(encoding="utf-8")
    assert 'const endpoint = "/api/dashboard/overview"' in js
    assert 'method: "GET"' in js
    assert 'method: "POST"' not in js
    assert 'method: "PUT"' not in js
    assert 'method: "DELETE"' not in js


def test_frontend_never_labels_data_as_live_execution():
    html = (STATIC / "dashboard.html").read_text(encoding="utf-8")
    assert "LIVE DÉSACTIVÉ" in html
    assert "Aucune donnée n'est présentée comme LIVE" in html
    assert "PAPER" in html
    assert "SHADOW" in html


def test_frontend_renders_unavailable_explicitly():
    js = (STATIC / "dashboard.js").read_text(encoding="utf-8")
    assert "Indisponible" in js
    assert 'metric.availability === "UNAVAILABLE"' in js


def test_frontend_states_comparison_has_no_promotion_authority():
    js = (STATIC / "dashboard.js").read_text(encoding="utf-8")
    assert "aucune promotion ni modification du risque" in js
