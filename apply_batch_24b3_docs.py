from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
MARKER = "<!-- BATCH_24B3_SCANNER_ANALYTICS_ATTRIBUTION -->"

ADDITIONS = {
    "docs/02_ARCHITECTURE.md": f"""

{MARKER}
## Addendum Batch 24B.3 — Scanner ↔ Analytics Attribution

La couche `app.evaluation.analytics_attribution` couvre désormais chaque évaluation Scanner du
Historical Replay, y compris `NO_TRIGGER` et `TRIGGER_BELOW_CANDIDATE_THRESHOLD`. L'identité
canonique reste `FeatureSnapshot.snapshot_id`. La résolution Analytics est factorisée dans
`AnalyticsSnapshotResolver` et reste strictement post-hoc, same-as-of et read-only.

`app.evaluation.scanner_observations` porte la primitive State@T neutre réutilisée par 23A.4 et
24B.3. Scanner/Agents/Risk/PAPER/LIVE et `app.analytics` ne dépendent pas de cette attribution.
""",
    "docs/06_EVALUATION_ET_APPRENTISSAGE.md": f"""

{MARKER}
## Addendum Batch 24B.3 — attribution Analytics de toutes les évaluations Scanner

`ScannerAnalyticsAttributionRecord` relie chaque état Scanner déjà émis à un
`AnalyticsSnapshot` exact quand la provenance le permet. Les trois classes Scanner sont
conservées sans recalcul et les comptes doivent conserver exactement le nombre d'évaluations
Scanner. Aucun Forward Outcome, rendement futur ou jugement de qualité n'entre dans le record.
""",
    "docs/08_API_ET_MODELES_DE_DONNEES.md": f"""

{MARKER}
## Addendum Batch 24B.3 — contrats Scanner Analytics Attribution

Contrats publics ajoutés :
- `ScannerObservation` et `ScannerOutcomeClassification` sous
  `app.evaluation.scanner_observations` ;
- `AnalyticsSnapshotResolver` partagé par 24B.1 et 24B.3 ;
- `ScannerAnalyticsAttributionRecord` ;
- `ScannerAnalyticsAttributionSet` ;
- `build_scanner_analytics_attribution`.

Schema record : `money-heist.scanner-analytics-attribution.v1`. Projection :
`scanner-analytics-attribution-v1`. La policy de matching reste
`opportunity-analytics-exact-v1` afin de conserver une seule vérité d'attribution Analytics.
""",
    "docs/09_ROADMAP_DEVELOPPEMENT.md": f"""

{MARKER}
## État Batch 24B.3 — Scanner ↔ Analytics Attribution

24B.3 étend le lien causal Analytics à 100 % des évaluations Scanner du replay, sans commencer
les analyses de performance, le tuning, les Forward Outcomes enrichis ou l'activation LIVE.
""",
    "docs/10_DECISIONS_ET_CHANGELOG.md": f"""

{MARKER}
### ADR-041 — Scanner Analytics Attribution read-only et exact

**Date :** 2026-09-17
**Statut :** ACCEPTED (candidate pending local validation)

**Décision :** `FeatureSnapshot.snapshot_id` est l'identité canonique d'une ScannerEvaluation.
Les trois classes Scanner de 23A.4 sont déplacées vers une primitive neutre partagée. 24B.1 et
24B.3 utilisent le même `AnalyticsSnapshotResolver` et la même policy
`opportunity-analytics-exact-v1`. Aucun fallback précédent/futur n'est autorisé.

**Conséquences :** chaque ScannerEvaluation possède un record d'attribution même sans candidate ;
les candidates peuvent référencer 24B.1/24B.2 ; la provenance MTF/cursor reste causale ; aucune
autorité Analytics ne remonte vers Scanner, Agents, Risk, PAPER ou LIVE ; l'identité du
BacktestRun et le fingerprint business restent inchangés.
""",
    "docs/11_BACKTESTING_ET_REPLAY_HISTORIQUE.md": f"""

{MARKER}
## Addendum Batch 24B.3 — attribution Scanner après replay

Après un Historical Replay terminé, 24B.3 projette les `FeatureSnapshot` et `ScanResult` déjà
présents en `ScannerObservation`, puis résout le `AnalyticsSnapshot` exact au même `as_of` avec
le même `source_cursor_fingerprint`. Le Scanner n'est jamais relancé et aucune donnée future
n'est utilisée pour sélectionner un snapshot Analytics.
""",
    "CHANGELOG_BATCH.md": f"""

{MARKER}
## Batch 24B.3 — Scanner ↔ Analytics Attribution Layer

- attribution post-hoc d'un record par ScannerEvaluation ;
- identité canonique `FeatureSnapshot.snapshot_id` ;
- trois classes Scanner State@T partagées avec 23A.4 ;
- extraction du resolver exact 24B.1 sans changement de policy ;
- absence de fallback précédent/futur ;
- conservation stricte du `source_cursor_fingerprint` et de la provenance MTF ;
- références optionnelles cohérentes vers 24B.1 et 24B.2 pour les candidates ;
- IDs/fingerprints/ordre déterministes et guards d'architecture read-only.
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
    print("Batch 24B.3 documentation updated:")
    for item in changed:
        print(f"- {item}")
    if not changed:
        print("- no changes (already applied)")


if __name__ == "__main__":
    main()
