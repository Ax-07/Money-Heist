# Clôture Batch 16.10 puis Batch 16.11

## 1. Clôturer Batch 16.10

Après les validations dashboard et le smoke multi-agents :

```powershell
git status --short
git add app/dashboard/backtest.py
git add app/dashboard/static/backtest.html
git add app/dashboard/static/backtest.js
git add tests/dashboard/test_backtest_defaults.py
git add tests/dashboard/test_backtest_agent_coverage.py
git add README_BATCH_16_10.md
git add CHANGELOG_BATCH_16_10.md
git add apply_batch_16_10_dataset_aware_defaults.py
git add README_BATCH_16_10_QUICK_TEST_FIX.md
git add CHANGELOG_BATCH_16_10_QUICK_TEST_FIX.md
git add apply_batch_16_10_quick_test_fix.py
git add README_BATCH_16_10_MOCK_AGENT_COVERAGE.md
git add CHANGELOG_BATCH_16_10_MOCK_AGENT_COVERAGE.md
git add apply_batch_16_10_mock_agent_coverage.py

git diff --cached --check
git diff --cached --stat
git commit -m "feat(dashboard): complete Batch 16.10 agent smoke coverage"
```

Ne pas utiliser `git add .`.

## 2. Appliquer et valider Batch 16.11

```powershell
uv run pytest -q tests/backtest/test_advanced_specialist_smokes.py
uv run pytest -q
uv run python run_advanced_specialist_smokes.py --csv "CHEMIN\VERS\BTCUSDC_1H.csv"
```

Puis :

```powershell
git add run_advanced_specialist_smokes.py
git add tests/backtest/test_advanced_specialist_smokes.py
git add README_BATCH_16_11_ADVANCED_SPECIALIST_SMOKE.md
git add CHANGELOG_BATCH_16_11.md
git add BATCH_16_10_16_11_CLOSURE.md

git diff --cached --check
git diff --cached --stat
git commit -m "test(agents): add grounded Rio and Denver smoke validation"
```
