$ErrorActionPreference = "Stop"

$expectedBaseline = "4c0bcdfb4d44421d4282ebaad5232051c0deedfa"
$head = (git rev-parse HEAD).Trim()
if ($head -ne $expectedBaseline) {
    Write-Warning "HEAD=$head ; baseline 24B.3 attendue=$expectedBaseline"
}

Write-Host "`n=== Ruff 24B.3 + non-regression ciblee ==="
uv run ruff check `
  app/evaluation/scanner_observations.py `
  app/evaluation/analytics_attribution `
  app/evaluation/scanner_forward_outcomes/models.py `
  apply_batch_24b3_docs.py `
  tests/evaluation/test_scanner_analytics_attribution.py `
  tests/evaluation/test_scanner_analytics_attribution_architecture.py `
  tests/evaluation/test_opportunity_analytics_attribution.py `
  tests/evaluation/test_scanner_forward_outcomes.py `
  tests/evaluation/test_analytics_attribution_architecture.py

Write-Host "`n=== Tests cibles 24B.1 / 24B.2 / 23A.4 / 24B.3 ==="
uv run pytest `
  tests/evaluation/test_opportunity_analytics_attribution.py `
  tests/evaluation/test_decision_intelligence.py `
  tests/evaluation/test_decision_intelligence_architecture.py `
  tests/evaluation/test_scanner_forward_outcomes.py `
  tests/backtest/test_scanner_forward_outcomes.py `
  tests/evaluation/test_analytics_attribution_architecture.py `
  tests/evaluation/test_scanner_analytics_attribution.py `
  tests/evaluation/test_scanner_analytics_attribution_architecture.py `
  -q

Write-Host "`n=== Suite Analytics ==="
uv run pytest tests/analytics -q

Write-Host "`n=== Etat Git ==="
git status --short
