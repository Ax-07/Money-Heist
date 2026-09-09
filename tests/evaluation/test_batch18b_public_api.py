from __future__ import annotations

import subprocess
import sys


def test_batch18b_symbols_are_public_without_eager_import_cycles() -> None:
    code = """
import app.services.backtest as backtest
import app.evaluation as evaluation

assert backtest.PaperAblationRuntimeFactory.__name__ == 'PaperAblationRuntimeFactory'
assert backtest.PaperAblationRuntimeSettings.__name__ == 'PaperAblationRuntimeSettings'
assert callable(backtest.execute_paper_ablation_campaign)
assert evaluation.AblationCampaignPlan.__name__ == 'AblationCampaignPlan'
assert evaluation.AblationCampaignExecutor.__name__ == 'AblationCampaignExecutor'
assert callable(evaluation.ablation_campaign_execution_to_json)
print('ok')
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"


def test_batch18b_symbols_are_listed_in_public_all() -> None:
    import app.evaluation as evaluation
    import app.services.backtest as backtest

    assert "AblationCampaignExecutionReport" in evaluation.__all__
    assert "ablation_campaign_execution_to_json" in evaluation.__all__
    assert "PaperAblationRuntimeFactory" in backtest.__all__
    assert "execute_paper_ablation_campaign" in backtest.__all__
