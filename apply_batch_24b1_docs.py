from __future__ import annotations

import subprocess
from pathlib import Path

BASELINE = "6d67e3f25a6c95f23552a5f4f025bd1b4d29a26c"
MARKER = "<!-- BATCH_24B1_OPPORTUNITY_ANALYTICS_LINKING -->"

DOC_ADDENDA = {
    "docs/BATCH_24A1_ANALYTICS_LAB_FOUNDATION.md": """
<!-- BATCH_24B1_OPPORTUNITY_ANALYTICS_LINKING -->
## Addendum 24B.1 — consumer externe du noyau Analytics

24B.1 ne modifie pas l'autorité de `app.analytics`. La nouvelle couche
`app.evaluation.analytics_attribution` est un consumer post-hoc externe qui peut
lire les
contrats Analytics et les artefacts décisionnels. La dépendance inverse reste
interdite :
`app.analytics` ne connaît ni `CandidateOpportunity`, ni `DecisionContextV1`, ni
la couche
d'attribution.
""",
    "docs/02_ARCHITECTURE.md": """
<!-- BATCH_24B1_OPPORTUNITY_ANALYTICS_LINKING -->
## Addendum Batch 24B.1 — Opportunity ↔ Analytics Linking

La phase 24B introduit une couche extérieure `app.evaluation.analytics_attribution`
qui peut
lire à la fois les artefacts du replay décisionnel et les artefacts `app.analytics`. La
direction de dépendance reste strictement post-hoc : Scanner, DecisionContext,
agents, Risk,
PAPER/LIVE et le calcul du business fingerprint n'importent jamais cette couche,
tandis que
`app.analytics` reste decision-agnostic.

```text
Historical Replay artifacts ──read-only──┐
                                         ├─> Analytics Attribution
Analytics Lab artifacts ──────read-only──┘
```

24B.1 ne recalcule ni Analytics ni décision et ne crée aucune autorité de trading.
""",
    "docs/06_EVALUATION_ET_APPRENTISSAGE.md": """
<!-- BATCH_24B1_OPPORTUNITY_ANALYTICS_LINKING -->
## Addendum Batch 24B.1 — attribution d'identité décision ↔ Analytics

24B.1 fournit une preuve de provenance, pas une métrique de performance. Une
`CandidateOpportunity` historique est reliée post-hoc à un `AnalyticsSnapshot`
uniquement si
le BacktestRun, le dataset content-addressed, le symbole, le decision timeframe,
le `as_of`, la
policy MTF et le `source_cursor_fingerprint` décrivent le même univers causal.
Le taux de
couverture mesure l'intégrité des artefacts ; il ne mesure ni l'edge ni la qualité
du trading.

Le contrat générique `DecisionObservationKey` est préparé pour la future attribution des
évaluations Scanner de 24B.3, sans implémenter cette attribution dans 24B.1.
""",
    "docs/08_API_ET_MODELES_DE_DONNEES.md": """
<!-- BATCH_24B1_OPPORTUNITY_ANALYTICS_LINKING -->
## Addendum Batch 24B.1 — contrats Opportunity ↔ Analytics

Nouveaux contrats read-only : `DecisionObservationKey`, `OpportunityObservationRef`,
`AnalyticsSnapshotRef`, `OpportunityAnalyticsLink`, `OpportunityAnalyticsLinkSet` et
`OpportunityAnalyticsLinkStatus`. La policy v1 est
`opportunity-analytics-exact-v1`.

`CandidateOpportunity` et `AnalyticsSnapshot` restent inchangés. Le `created_at`
actuel de
`CandidateOpportunity` est utilisé comme `observed_at` uniquement après validation de
l'invariant Scanner existant (`created_at == FeatureSnapshot.observed_at == replay point
observed_at`). Le fingerprint de curseur provient du `HistoricalReplayPoint` MTF
et ne dépend
pas de l'existence d'un `DecisionContext`.

Le sidecar ne copie aucun Indicator/Event/Pattern/Context/Sequence. Il conserve
seulement les
identités et la provenance nécessaires, ainsi qu'une projection minimale de
l'identité du
snapshot Analytics.
""",
    "docs/09_ROADMAP_DEVELOPPEMENT.md": """
<!-- BATCH_24B1_OPPORTUNITY_ANALYTICS_LINKING -->
## Addendum Batch 24B — Decision ↔ Analytics Attribution

Roadmap de la phase :

```text
24B.1 — Opportunity ↔ Analytics Linking
24B.2 — Decision Intelligence Record
24B.3 — Scanner ↔ Analytics Attribution
24B.4 — Funnel Stage ↔ Analytics Attribution
```

24B.1 livre uniquement la primitive de jointure exacte et les diagnostics de
provenance. Il ne
construit ni Decision Intelligence Record, ni attribution complète Scanner/Funnel,
ni UI.
""",
    "docs/10_DECISIONS_ET_CHANGELOG.md": """
<!-- BATCH_24B1_OPPORTUNITY_ANALYTICS_LINKING -->
### 2026-09-17 — Batch 24B.1 Opportunity ↔ Analytics Linking

**ACCEPTED (candidate pending local validation)** — La jointure Decision ↔ Analytics
devient
une dérivation post-hoc dans `app.evaluation.analytics_attribution`. Le run Analytics
est
sélectionné explicitement ; aucun `latest run` implicite n'est autorisé. La policy
v1 exige une
égalité exacte de provenance et interdit tout nearest-neighbor temporel. Les statuts
distinguent
notamment snapshot manquant, ambiguïté, mismatch dataset/symbole/timeframe/policy/
cursor et
provenance source incomplète. `CandidateOpportunity`, `AnalyticsSnapshot`, le replay
métier et
le business fingerprint restent inchangés.
""",
    "docs/11_BACKTESTING_ET_REPLAY_HISTORIQUE.md": """
<!-- BATCH_24B1_OPPORTUNITY_ANALYTICS_LINKING -->
## Addendum Batch 24B.1 — jointure post-hoc après replay

Après un `HistoricalReplayResult` complété et un `AnalyticsLabRun` complété sur le
même univers,
24B.1 adapte les points ayant une `CandidateOpportunity` vers un
`DecisionObservationKey`.
`HistoricalReplayPoint.mtf_cursor_fingerprint` fournit la preuve de préfixe causal
même si
l'opportunité ne possède pas de `DecisionContext`.

Le lookup Analytics est exact sur `(symbol, decision_timeframe, as_of)` à
l'intérieur d'un
`analytics_run_id` explicitement fourni. Un snapshot précédent ou futur n'est
jamais choisi.
Deux snapshots distincts portant la même clé canonique produisent
`AMBIGUOUS_ANALYTICS_SNAPSHOT`.
Le linker ne lance aucun Indicator/Event/ZigZag/Pattern/Context/Sequence resolver
et ne rejoue
aucun Scanner/agent/Risk.
""",
    "CHANGELOG_BATCH.md": """
<!-- BATCH_24B1_OPPORTUNITY_ANALYTICS_LINKING -->
## Batch 24B.1 — Opportunity ↔ Analytics Linking

- couche post-hoc `app.evaluation.analytics_attribution` ;
- `DecisionObservationKey` générique réutilisable par 24B.3 ;
- sidecar `OpportunityAnalyticsLink` déterministe ;
- lookup exact de `AnalyticsSnapshot`, sans nearest-time fallback ;
- contrôle BacktestRun/dataset/symbole/timeframe/as_of/MTF policy/cursor ;
- diagnostics explicites missing/mismatch/ambiguous ;
- `DecisionContext` optionnel ;
- business fingerprint et pipelines trading inchangés ;
- architecture guards Analytics/Decision/Attribution renforcés.
""",
}


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def append_once(path: Path, text: str) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    current = path.read_text(encoding="utf-8")
    if MARKER in current:
        print(f"skip: {path} (already updated)")
        return
    path.write_text(current.rstrip() + "\n\n" + text.strip() + "\n", encoding="utf-8")
    print(f"updated: {path}")


def main() -> None:
    root = Path.cwd()
    valid_root = (
        (root / "pyproject.toml").exists()
        and (root / "app" / "analytics").exists()
    )
    if not valid_root:
        raise SystemExit("Run this script from the Money-Heist repository root.")
    head = git_head()
    if head != BASELINE:
        raise SystemExit(f"Unexpected HEAD: {head}; expected baseline {BASELINE}")
    for relative, text in DOC_ADDENDA.items():
        append_once(root / relative, text)
    print("Batch 24B.1 documentation addenda applied.")


if __name__ == "__main__":
    main()
