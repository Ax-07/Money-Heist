# Money Heist Frontend V2

Cockpit Next.js séparé du backend FastAPI.

## Prérequis

- Node.js 22+ recommandé ;
- npm ;
- backend Money Heist démarré sur `http://127.0.0.1:8000` par défaut.

## Installation

```bash
cd frontend
npm install
cp .env.example .env.local   # PowerShell: Copy-Item .env.example .env.local
npm run dev
```

`MONEY_HEIST_API_URL` est lu uniquement côté serveur Next. Aucun secret ni URL de contrôle sensible ne doit être placé dans `NEXT_PUBLIC_*`.

## Validation

```bash
npm run lint
npm run typecheck
npm run test
npm run build
npm run test:e2e
```

## Architecture courte

```text
src/app               routing App Router
src/components        shell, UI, chart, inspectors
src/features          workspaces métier
src/lib/api            client centralisé + Zod + queries
src/lib/ui-store.ts    préférences UI uniquement
```

Server state : TanStack Query. Le chart utilise `TradingChartAdapter` et Lightweight Charts. Les décisions et métriques viennent du backend ; elles ne sont pas recalculées côté navigateur.

## Connexion backend

Par défaut :

```env
MONEY_HEIST_API_URL=http://127.0.0.1:8000
```

Le navigateur appelle `/api/money-heist/*`; Next relaie vers FastAPI. L’URL backend reste donc server-side.

## Backtests

Le launcher V2 utilise l’import CSV et le moteur historique existants. Le replay détaillé V2 est disponible pour les campagnes lancées via `/api/frontend/v2/backtests/runs` pendant la vie du même processus backend.

`LIVE_EVAL` signifie fournisseur IA réel dans un backtest PAPER. Il ne signifie jamais exécution LIVE.

## Backtest Cockpit V2.1

Le lanceur Backtests expose Dataset, DESIGN/VALIDATION/OOS, Risk, IA, Exécution, Walk-Forward et une revue finale. Les datasets et artefacts V2 sont persistés par le backend ; aucun CSV n'est stocké dans le navigateur.

Le stockage backend par défaut est `.money-heist/frontend-v2/` à la racine du dépôt. Il peut être déplacé avec `MONEY_HEIST_FRONTEND_V2_STORAGE_DIR`.
