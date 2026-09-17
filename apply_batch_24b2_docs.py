from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
MARKER = "<!-- BATCH_24B2_DECISION_INTELLIGENCE_RECORD -->"

ADDITIONS = {
    "docs/02_ARCHITECTURE.md": f"""

{MARKER}
## Addendum Batch 24B.2 — Decision Intelligence Record

La couche `app.evaluation.decision_intelligence` projette en lecture seule les artefacts déjà
émis par Historical Replay (`CandidateOpportunity`, `DecisionContextV1`, orchestration, Risk et
PAPER) avec le `OpportunityAnalyticsLink` 24B.1. Elle ne possède aucune autorité de trading et
ne rappelle aucun service actif. Le `DecisionFunnelReport` reste un agrégat 23A ; le détail par
opportunité provient du `HistoricalReplayPoint` et de son `PaperPipelineResult`.

La direction des dépendances reste strictement post-hoc : Scanner/Agents/Risk/PAPER/LIVE et
`app.analytics` n'importent pas Decision Intelligence.
""",
    "docs/06_EVALUATION_ET_APPRENTISSAGE.md": f"""

{MARKER}
## Addendum Batch 24B.2 — projection factuelle de la décision

`DecisionIntelligenceRecord` fournit une représentation déterministe de ce que Money Heist a
observé et produit pour une `CandidateOpportunity`, avec l'identité Analytics same-as-of déjà
résolue par 24B.1. Le record est indépendant des Forward Outcomes : H1/H3/H5/H10/H20, MFE/MAE,
PnL futur et jugements de qualité restent des informations postérieures à la décision et seront
rejoints extérieurement pour les analyses futures.
""",
    "docs/08_API_ET_MODELES_DE_DONNEES.md": f"""

{MARKER}
## Addendum Batch 24B.2 — modèles Decision Intelligence

Contrats publics ajoutés sous `app.evaluation.decision_intelligence` :
- `DecisionIntelligenceRecord` ;
- `DecisionIntelligenceRecordSet` ;
- projections typées Scanner, Compute Gate, DecisionContext ref, PLAN, spécialistes, Palermo,
  FINAL, TradeProposal, Risk et exécution PAPER ;
- `AnalyticsRefProjection`, qui reprend exclusivement le sidecar 24B.1.

Schema : `money-heist.decision-intelligence-record.v1`. Policy :
`decision-intelligence-projection-v1`. `record_id`, `record_fingerprint` et `set_fingerprint`
sont déterministes via les helpers canoniques communs.
""",
    "docs/09_ROADMAP_DEVELOPPEMENT.md": f"""

{MARKER}
## État Batch 24B.2 — Decision Intelligence Record

24B.2 introduit la projection read-only d'une opportunité complète avec son link Analytics 24B.1.
Le batch prépare 24B.3/24B.4/24C sans commencer leurs analyses, statistiques ou API/UI.
""",
    "docs/10_DECISIONS_ET_CHANGELOG.md": f"""

{MARKER}
### ADR-040 — Decision Intelligence Record read-only

**Date :** 2026-09-17
**Statut :** ACCEPTED (candidate pending local validation)

**Décision :** `DecisionIntelligenceRecord` est un artefact post-hoc sous
`app.evaluation.decision_intelligence`. Il projette les artefacts canoniques du replay et consomme
le `OpportunityAnalyticsLink` 24B.1 sans rematching. Un lien Analytics non résolu n'efface pas la
décision. Le record n'embarque aucun Forward Outcome et n'a aucune autorité sur Scanner, agents,
Risk, PAPER ou LIVE.

**Conséquences :** l'ordre réel des spécialistes est conservé, les failures restent techniques,
les étapes non atteintes ne reçoivent aucun statut métier fabriqué et l'identité du BacktestRun
ainsi que son fingerprint business restent indépendants du record. Le contrat français
`money-heist.agent-dialogue.fr.v1` / `money-heist.prompt-transport.v4` est inchangé.
""",
    "docs/11_BACKTESTING_ET_REPLAY_HISTORIQUE.md": f"""

{MARKER}
## Addendum Batch 24B.2 — projection Decision Intelligence après replay

Après un replay terminé et la construction des links 24B.1, 24B.2 peut produire un record par
`CandidateOpportunity` depuis les `HistoricalReplayPoint` déjà présents. Cette opération est
purement dérivée : elle ne relance ni Scanner, ni orchestration, ni Risk, ni broker et ne modifie
pas `BacktestRun.run_id` ou le fingerprint business. Les résultats futurs et `exit_events` ne
font pas partie du core record causal.
""",
    "CHANGELOG_BATCH.md": f"""

{MARKER}
## Batch 24B.2 — Decision Intelligence Record

- nouvelle couche `app.evaluation.decision_intelligence` read-only ;
- un record déterministe par `CandidateOpportunity` et couple BacktestRun/AnalyticsRun ;
- réutilisation stricte des `OpportunityAnalyticsLink` 24B.1, sans second matching ;
- projections typées du funnel réel et conservation des failures/not-reached ;
- séparation stricte des Forward Outcomes ;
- guards d'architecture anti-retour vers le pipeline de trading ;
- préservation explicite du contrat agents français v1 / prompt transport v4.
""",
}


def main() -> None:
    changed: list[str] = []
    for relative, addition in ADDITIONS.items():
        path = ROOT / relative
        if not path.exists():
            raise FileNotFoundError(path)
        text = path.read_text(encoding="utf-8")
        base = text.split(MARKER, 1)[0] if MARKER in text else text
        rendered = base.rstrip() + "\n\n" + addition.strip() + "\n"
        if text == rendered:
            continue
        path.write_text(rendered, encoding="utf-8")
        changed.append(relative)
    print("Batch 24B.2 documentation updated:")
    for item in changed:
        print(f"- {item}")
    if not changed:
        print("- no changes (already applied)")


if __name__ == "__main__":
    main()
