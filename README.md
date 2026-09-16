# Money Heist

Money Heist est une plateforme de trading crypto assistée par IA, organisée autour d’une crew d’agents spécialisés, d’un Risk Engine déterministe et de chemins séparés PAPER / SHADOW / LIVE / BACKTEST.

## Architecture

```text
Market Data → Feature Engine → Scanner → Crew / Professor / Palermo
→ TradeProposal → Risk Engine → Broker → Evaluation
                                 ↓
                         Frontend V2 Cockpit
```

Le backend Python/FastAPI reste l’autorité métier. Le frontend Next.js observe, configure uniquement les paramètres explicitement autorisés et rejoue les résultats historiques sans recalculer les décisions.

## Backend

Prérequis : Python 3.13 et `uv`.

```bash
uv sync
uv run python scripts/bootstrap.py
uv run --env-file .env python scripts/run_dev.py
```

Validation :

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

API par défaut : `http://127.0.0.1:8000`.

## Frontend V2

```bash
cd frontend
pnpm install
pnpm run dev
```

Puis ouvrir `http://127.0.0.1:3000`.

Le Backtest Cockpit V2.1 persiste ses datasets/campagnes/replays sous `.money-heist/frontend-v2/`. Le chemin peut être surchargé côté backend avec `MONEY_HEIST_FRONTEND_V2_STORAGE_DIR` dans `.env`.

Validation :

```bash
pnpm run lint
pnpm run typecheck
pnpm run test
pnpm run build
```

Le Frontend V2 utilise Next.js, React, TypeScript strict, Tailwind, TanStack Query, Zod, Zustand pour le seul état UI global et Lightweight Charts derrière `TradingChartAdapter`.

## Sécurité

- aucune clé exchange/OpenAI dans le navigateur ;
- aucun droit de retrait ;
- Risk Engine non contournable ;
- LIVE fail-closed et armement opérateur séparé ;
- Historical Replay et LIVE_EVAL restent PAPER-only ;
- aucune action critique fictive dans l’interface.

## Documentation

La documentation permanente a une seule source de vérité : `docs/`.
Commencer par [`docs/README.md`](docs/README.md), puis consulter
`docs/00_ETAT_ACTUEL_POST_BATCH_15.md` pour l’état courant. Les documents numérotés ne sont plus
dupliqués à la racine du dépôt.

<!-- DOC_REALIGN_README_20260915_START -->

## Prompt Cache et coûts IA

Le AI Gateway peut activer explicitement le Prompt Cache OpenAI sur les routes qui déclarent cette capability. Le transport courant est `money-heist.prompt-transport.v2`. Les métriques distinguent input normal, cache read, cache write et output, ainsi qu’une estimation du coût sans cache.

Le cache fournisseur est distinct du cache de réponses Historical Replay `money-heist.backtest-ai-cache.v2`.

## Utilitaires Market Data

Les scripts opérateur de préparation/audit historique sont regroupés sous `scripts/market_data/`. Utiliser `--help` sur chaque script avant exécution.

<!-- DOC_REALIGN_README_20260915_END -->
