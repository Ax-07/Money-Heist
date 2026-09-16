# Documentation Money Heist

`docs/` est la **source de vérité documentaire unique** du projet pour les documents permanents.
Les fichiers numérotés ne doivent pas être dupliqués à la racine.

## Ordre de lecture recommandé

1. `00_ETAT_ACTUEL_POST_BATCH_15.md` — état courant synthétique.
2. `01_PROJECT_MASTER.md` — vision, objectifs et invariants.
3. `02_ARCHITECTURE.md` — architecture technique.
4. `03_SYSTEME_AGENTS.md` — agents et orchestration.
5. `04_TRADING_ET_RISQUE.md` — trading, risque et autorité déterministe.
6. `05_MARKET_DATA_ET_EXECUTION.md` — Market Data et exécution.
7. `06_EVALUATION_ET_APPRENTISSAGE.md` — Evaluation, Lisbon et apprentissage.
8. `07_SECURITE_ET_OPERATIONS.md` — sécurité et opérations.
9. `08_API_ET_MODELES_DE_DONNEES.md` — contrats et API.
10. `09_ROADMAP_DEVELOPPEMENT.md` — roadmap et état des lots.
11. `10_DECISIONS_ET_CHANGELOG.md` — ADR et décisions ouvertes.
12. `11_BACKTESTING_ET_REPLAY_HISTORIQUE.md` — Historical Replay / Backtest.
13. `12_FRONTEND_ET_INTERFACE.md` — Frontend V2 / Backtest Cockpit.
14. `ADR_031_OPENAI_PROMPT_CACHE_ET_COUTS.md` — Prompt Cache OpenAI et coûts IA.
15. `CHANGELOG_PROMPT_CACHE.md` — détail du chantier Prompt Cache.

## Fichiers opérationnels conservés à la racine

La racine conserve volontairement les points d’entrée et documents opérateur transverses, notamment
`README.md`, `CHANGELOG_BATCH.md`, `LIVE_ACTIVATION_CHECKLIST.md`, `LIVE_PREFLIGHT.md` et
`LIVE_RUNBOOKS.md`.

## Règle de layout

Toute évolution d’un document permanent numéroté doit modifier uniquement sa copie sous `docs/`.
Les tests de documentation vérifient que les doublons racine ne réapparaissent pas.
