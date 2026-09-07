$ErrorActionPreference = "Stop"

Write-Host "Money Heist — Batch 15 LIVE preflight (READ-ONLY côté Kraken)"
Write-Host "Cette commande n'arme pas le LIVE et ne peut pas soumettre/annuler un ordre."

uv run alembic current
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

uv run python -m app.trading.live.preflight_cli
exit $LASTEXITCODE
