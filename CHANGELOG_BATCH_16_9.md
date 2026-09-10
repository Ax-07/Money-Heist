# CHANGELOG_BATCH — Batch 16.9 Backtest Dashboard UX

## Ajouté
- axe `candle_close_ms` dans le preview ;
- `suggested_split_indices` ;
- `SplitIndexView` ;
- metadata agents dans `/capabilities` ;
- `AgentTraceView.targets` ;
- `CampaignProgressView.active_agents` ;
- wrapper dashboard `ObservableBacktestAIClient` ;
- timeline segmentée ;
- cards crew ;
- flux SVG animés ;
- test `tests/dashboard/test_backtest_ux.py`.

## Modifié par le script
- `app/dashboard/backtest.py`
- `app/dashboard/static/backtest.html`
- `app/dashboard/static/backtest.js`
- `app/dashboard/static/backtest.css`

## Invariants
- PAPER-only ;
- aucune dépendance LIVE ajoutée ;
- Risk Engine inchangé ;
- PaperBroker inchangé ;
- contrat backend `CampaignRequest.split` conservé ;
- aucune clé OpenAI dans le frontend ;
- aucune chaîne de pensée privée exposée.
