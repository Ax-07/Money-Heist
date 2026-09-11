# Batch 16.21h — Portfolio & Market Constraints Parity

## Objective

Expose decision-time `PortfolioRiskState` and `MarketConstraints` in the same
frozen `DecisionContextV1` shared by the agents.

The Risk Engine remains authoritative.

## Authority boundary

Replay order:

1. historical lifecycle updates positions and portfolio;
2. Scanner emits an opportunity;
3. runner freezes current portfolio and market constraints in DecisionContext;
4. agents reason from that immutable copy;
5. `PaperTradingPipeline` reads its providers again;
6. `RiskEngine.evaluate(...)` makes the deterministic authorization decision.

DecisionContext never authorizes an order.

## Shared-provider invariant

Dashboard and Ablation create one `InMemoryMarketConstraintsProvider` and inject
the same object into both `HistoricalReplayRunner` and `PaperTradingPipeline`.

`BacktestPortfolioStateProvider` was already shared.

The runner fails closed if a real PAPER pipeline and runner use different market
constraint providers.

## Audit semantics

`HistoricalReplayPoint` distinguishes:

- `decision_portfolio_state`: pre-AI state;
- `decision_market_constraints`: pre-AI constraints;
- `portfolio_state`: post-pipeline state.

This prevents an execution from retroactively changing what agents are recorded
as having seen.

## Reproducibility

MTF runs additionally bind:

`risk_context_binding_version=portfolio-market-constraints-v1`

## Missing-aware behavior

When a decision-time source is absent, the corresponding DecisionContext field
remains absent and stays listed in `missing_components`. No zero portfolio or
exchange constraint is fabricated.

## Validation

```powershell
uv run pytest -q tests/backtest/test_replay_runner_mtf.py
uv run pytest -q tests/backtest/test_mtf_runtime_activation.py
uv run pytest -q tests/dashboard/test_mtf_runtime_activation.py
uv run pytest -q

uv run python .\scripts\validate_risk_context_parity.py `
  ".\data\historical\binance_spot\backtest_ready\binance_btc_usdc_1m_2025-09-11_2026-09-10.csv"
```
