$ErrorActionPreference = "Stop"

Write-Host "=== Batch 24D.1 - baseline ==="
git rev-parse HEAD
git merge-base --is-ancestor a010155337a446bcbd06ded32667ea667b1512d7 HEAD
if ($LASTEXITCODE -ne 0) { throw "Baseline a010155 is not an ancestor of HEAD." }

Write-Host "`n=== Ruff - Python 24D.1 ==="
uv run ruff check `
  app/evaluation/decision_quality `
  tests/evaluation/test_decision_quality.py `
  tests/evaluation/test_decision_quality_architecture.py

Write-Host "`n=== Tests 24D.1 ==="
uv run pytest `
  tests/evaluation/test_decision_quality.py `
  tests/evaluation/test_decision_quality_architecture.py `
  -q

Write-Host "`n=== Regression 23A ==="
$tests23A = @(
  "tests/evaluation/test_forward_outcomes.py",
  "tests/backtest/test_forward_outcomes.py",
  "tests/evaluation/test_scanner_forward_outcomes.py",
  "tests/backtest/test_scanner_forward_outcomes.py",
  "tests/backtest/test_funnel_outcome_attribution.py"
) | Where-Object { Test-Path $_ }
if ($tests23A.Count -gt 0) { uv run pytest @tests23A -q }

Write-Host "`n=== Regression 24A / 24B ==="
$tests24AB = @(
  "tests/analytics",
  "tests/evaluation/test_opportunity_analytics_attribution.py",
  "tests/evaluation/test_decision_intelligence.py",
  "tests/evaluation/test_decision_intelligence_architecture.py",
  "tests/evaluation/test_analytics_attribution_architecture.py",
  "tests/evaluation/test_scanner_analytics_attribution.py",
  "tests/evaluation/test_scanner_analytics_attribution_architecture.py",
  "tests/evaluation/test_funnel_stage_analytics_attribution.py"
) | Where-Object { Test-Path $_ }
if ($tests24AB.Count -gt 0) { uv run pytest @tests24AB -q }

Write-Host "`n=== Regression 24C post-run/projection ==="
$tests24C = @(
  "tests/services/test_frontend_postrun_architecture.py",
  "tests/services/test_frontend_projection_architecture.py",
  "tests/services/test_frontend_decision_intelligence_projection.py",
  "tests/api/test_frontend_v2_decision_intelligence.py",
  "tests/api/test_frontend_v2_analytics_overlays.py"
) | Where-Object { Test-Path $_ }
if ($tests24C.Count -gt 0) { uv run pytest @tests24C -q }

Write-Host "`n=== Full suite ==="
uv run pytest -q

Write-Host "`n=== Git audit ==="
git status --short
git diff --stat
git diff --name-only
