from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
MARKER_22 = "<!-- BATCH22_FRONTEND_V2 -->"
MARKER_22_1 = "<!-- BATCH22_1_BACKTEST_COCKPIT -->"

ADDITIONS_22: dict[str, str] = {
    "02_ARCHITECTURE.md": f"""

{MARKER_22}
## Addendum Batch 22 — Frontend V2 / Trading Cockpit

Le frontend devient une application séparée `frontend/` en Next.js + React + TypeScript.
FastAPI reste l'autorité métier. Le navigateur accède aux contrats via un proxy Next
server-side et une couche API centralisée/Zod.

Le Frontend V2 ne recalcule ni Feature Engine, ni Scanner, ni TradeProposal,
ni RiskDecision, ni backtest. La V2 utilise un polling centralisé TanStack Query tant
qu'aucun flux opérateur WebSocket/SSE n'est disponible.
""",
    "08_API_ET_MODELES_DE_DONNEES.md": f"""

{MARKER_22}
## Addendum Batch 22 — API Frontend V2

L'API `/api/frontend/v2` expose les capacités non sensibles, les candles/contraintes
Kraken publiques, le lancement de campagnes Batch 16 et un Historical Replay visuel.
Aucun endpoint d'armement LIVE n'est ajouté.
""",
    "09_ROADMAP_DEVELOPPEMENT.md": f"""

{MARKER_22}
## Batch 22 — Frontend V2 / Trading Cockpit

Foundation Next.js/TypeScript strict, navigation desktop/mobile, Trading Workspace,
Lightweight Charts derrière un adapter, Backtests DESIGN/VALIDATION/OOS,
Historical Replay, Decision Trace, observabilité et Settings fail-closed.
Le Dashboard V1 n'est pas supprimé.
""",
    "10_DECISIONS_ET_CHANGELOG.md": f"""

{MARKER_22}
### ADR-029 — Frontend Money Heist V2 en Next.js

**Date :** 2026-09-12  
**Statut :** ACCEPTED

Le cockpit V2 utilise Next.js + React + TypeScript strict. FastAPI reste responsable
du métier, du Risk Engine, de l'exécution, des secrets et de la sécurité. Le chart est
abstrait derrière `TradingChartAdapter` et utilise Lightweight Charts en l'absence de
bibliothèque TradingView propriétaire fournie.
""",
    "11_BACKTESTING_ET_REPLAY_HISTORIQUE.md": f"""

{MARKER_22}
## Extension Batch 22 — Historical Replay visuel

Frontend V2 ajoute un workspace de replay autour du moteur Batch 16 sans créer de
second moteur historique. Le frontend ne résout jamais lui-même l'intrabar, les gaps,
fees/slippage, agents, Risk ou lifecycle de position.
""",
    "CHANGELOG_BATCH.md": f"""

{MARKER_22}
## Batch 22 — Frontend V2 / Trading Cockpit

- frontend Next.js/React/TypeScript strict ;
- Trading Workspace et chart ;
- Historical Replay / Decision Trace ;
- API V2 minimale sans capacité LIVE ;
- Dashboard V1 conservé pendant la migration.
""",
}

ADDITIONS_22_1: dict[str, str] = {
    "02_ARCHITECTURE.md": f"""

{MARKER_22_1}
## Addendum Batch 22.1 — Backtest Cockpit durable

Frontend V2 conserve `BacktestDashboardService` comme autorité d'exécution mais ajoute
un sidecar durable sous `.money-heist/frontend-v2/`. Il persiste bibliothèque de
datasets, configuration figée, progression/traces, résumé et exports nécessaires au
replay. Aucun calcul métier n'est déplacé hors du moteur Batch 16.
""",
    "08_API_ET_MODELES_DE_DONNEES.md": f"""

{MARKER_22_1}
## Addendum Batch 22.1 — API Backtest Cockpit

L'API V2 ajoute une bibliothèque de datasets, le lancement par `dataset_id`, le
listing/détail/progress/configuration persistants et le replay durable. Le CSV reste
côté backend et n'est pas renvoyé au navigateur pour réutilisation.
""",
    "09_ROADMAP_DEVELOPPEMENT.md": f"""

{MARKER_22_1}
## Batch 22.1 — Frontend V2 Backtest Cockpit Completion

Le lanceur suit Dataset → Périodes → Risk → IA → Exécution → Données avancées →
Walk-Forward → Revue. Les defaults deviennent visibles/modifiables et les
datasets/artefacts de replay V2 sont persistés localement.
""",
    "10_DECISIONS_ET_CHANGELOG.md": f"""

{MARKER_22_1}
### ADR-030 — Sidecar durable Frontend V2 pour Historical Replay

**Date :** 2026-09-13  
**Statut :** ACCEPTED

Les entrées immuables et sorties déjà produites du Backtest Cockpit sont persistées
sous `.money-heist/frontend-v2/`, surchargeable par
`MONEY_HEIST_FRONTEND_V2_STORAGE_DIR`. Ce sidecar ne devient jamais un second moteur
de backtest et ne recalcule ni Scanner, agents, Risk, fills ni métriques.
""",
    "11_BACKTESTING_ET_REPLAY_HISTORIQUE.md": f"""

{MARKER_22_1}
## Extension Batch 22.1 — Backtest Cockpit et replay durable

Le cockpit expose explicitement split, Risk, IA, exécution et Walk-Forward. Un dataset
validé est persisté une fois puis référencé par `dataset_id`. À la fin d'une campagne,
Frontend V2 snapshotte résumé, traces et exports existants afin de restaurer le replay
après redémarrage, sans réexécution du moteur historique.
""",
    "CHANGELOG_BATCH.md": f"""

{MARKER_22_1}
## Batch 22.1 — Backtest Cockpit Completion

- configuration complète du backtest depuis l'UI ;
- édition DESIGN/VALIDATION/OOS alignée sur les bougies ;
- Walk-Forward pilotable ;
- bibliothèque de datasets persistés ;
- persistance V2 des configurations, traces, résumés et exports de replay ;
- aucun changement des frontières PAPER/LIVE ou du Risk Engine.
""",
}

GITIGNORE_22 = f"""
{MARKER_22}
# Frontend V2
frontend/node_modules/
frontend/.next/
frontend/coverage/
frontend/playwright-report/
frontend/test-results/
frontend/.env.local
"""
GITIGNORE_22_1 = f"""
{MARKER_22_1}
# Frontend V2 durable runtime artifacts
.money-heist/frontend-v2/
"""


def append_once(path: Path, block: str, marker: str) -> bool:
    if not path.exists():
        return False
    content = path.read_text(encoding="utf-8")
    if marker in content:
        return False
    path.write_text(content.rstrip() + block + "\n", encoding="utf-8")
    return True


def apply_additions(additions: dict[str, str], marker: str, changed: list[str]) -> None:
    for relative, block in additions.items():
        candidates = [ROOT / relative]
        if relative != "CHANGELOG_BATCH.md":
            candidates.append(ROOT / "docs" / relative)
        for candidate in candidates:
            if append_once(candidate, block, marker):
                changed.append(str(candidate.relative_to(ROOT)))


def main() -> None:
    changed: list[str] = []
    apply_additions(ADDITIONS_22, MARKER_22, changed)
    if append_once(ROOT / ".gitignore", GITIGNORE_22, MARKER_22):
        changed.append(".gitignore")
    apply_additions(ADDITIONS_22_1, MARKER_22_1, changed)
    if append_once(ROOT / ".gitignore", GITIGNORE_22_1, MARKER_22_1):
        changed.append(".gitignore")

    print("Batch 22 / 22.1 documentation integration:")
    if changed:
        for item in changed:
            print(f"- updated: {item}")
    else:
        print("- no changes (already applied or source documents absent)")


if __name__ == "__main__":
    main()
