from __future__ import annotations

import subprocess
from pathlib import Path

BASELINE = "0dc8200025ae7ca43964cadc04dff6e1ba1ac065"
MARKER = "<!-- BATCH_24A7_CONTEXTS_SEQUENCES -->"

DOC_ADDENDA = {
    "docs/02_ARCHITECTURE.md": """
<!-- BATCH_24A7_CONTEXTS_SEQUENCES -->
## Addendum Batch 24A.7 — Causal Contexts & Sequences

La couche `app.analytics.research` interroge en lecture seule les artefacts Analytics canoniques
via `AnalyticsObservationIndex`. Elle n'est jamais importée par le pipeline décisionnel.
`AnalyticsContextDefinition` est une hypothèse de recherche et ne doit pas être confondu avec
`DecisionContextV1`. Les recherches possèdent une identité séparée (`AnalyticsResearchRun`) afin
de ne pas modifier l'identité de `AnalyticsLabRun`, `BacktestRun.run_id` ou le business
fingerprint.
""",
    "docs/06_EVALUATION_ET_APPRENTISSAGE.md": """
<!-- BATCH_24A7_CONTEXTS_SEQUENCES -->
## Addendum Batch 24A.7 — discipline des hypothèses de recherche

Les Contexts/Sequences sont des hypothèses descriptives versionnées. Leur `origin_period_role`
conserve DESIGN/VALIDATION/OOS. Une hypothèse destinée à VALIDATION/OOS doit conserver la même
révision/fingerprint figée ; 24A.7 n'effectue ni ranking, ni auto-tuning, ni jointure vers
Forward Outcomes.
""",
    "docs/08_API_ET_MODELES_DE_DONNEES.md": """
<!-- BATCH_24A7_CONTEXTS_SEQUENCES -->
## Addendum Batch 24A.7 — Research Contexts / Sequences

Contrats principaux : `AnalyticsObservationIndex`, `AnalyticsContextDefinition`,
`AnalyticsContextMatch`, `AnalyticsSequenceDefinition`, `AnalyticsSequenceMatch`,
`AnalyticsResearchRun`, `ConditionEvaluation`. Les définitions et résultats sont immuables,
versionnés et fingerprintés. Les anchors v1 sont Technical Event, Pattern Transition et ZigZag
Pivot confirmé.
""",
    "docs/09_ROADMAP_DEVELOPPEMENT.md": """
<!-- BATCH_24A7_CONTEXTS_SEQUENCES -->
## Addendum Batch 24A.7 — Analytics Core

24A.7 complète le noyau Analytics avec des Contexts et Sequences causaux observation-only. La
phase suivante reste Batch 24B — Decision ↔ Analytics Attribution ; aucun join
Scanner/Opportunity n'est ajouté par 24A.7.
""",
    "docs/10_DECISIONS_ET_CHANGELOG.md": """
<!-- BATCH_24A7_CONTEXTS_SEQUENCES -->
### 2026-09-17 — Batch 24A.7 Causal Contexts & Sequences

**ACCEPTED (candidate pending local validation)** — Contexts et Sequences deviennent une couche
Research séparée de `DecisionContextV1`. Anchors v1 : Technical Event, Pattern Transition,
ZigZag Pivot confirmé. Conditions : Indicator/Event/Pattern/Structure/ZigZag. `THEN` est strict
(same-bar rejeté), les fenêtres sont en barres avec borne N incluse, le matching choisit le
prédécesseur compatible le plus récent, les partials et failed evaluations ne sont pas
persistés. Les conditions MTF réutilisent les observations closes/as-of canoniques.
""",
    "docs/11_BACKTESTING_ET_REPLAY_HISTORIQUE.md": """
<!-- BATCH_24A7_CONTEXTS_SEQUENCES -->
## Addendum Batch 24A.7 — replay causal des recherches

La résolution Context/Sequence respecte l'invariant prefix : à `as_of=T`, le résultat est
identique avec le dataset complet ou tronqué à T. Les anchors utilisent leurs timestamps de
disponibilité (`available_at` / `confirmed_at`) et une séquence complétée ultérieurement n'est
jamais rétro-propagée dans un snapshot antérieur.
""",
    "CHANGELOG_BATCH.md": """
<!-- BATCH_24A7_CONTEXTS_SEQUENCES -->
## Batch 24A.7 — Causal Contexts & Sequences

- Observation Index causal/read-only sur Indicators, Events, Structure, ZigZag et Pattern
  transitions ;
- Context DSL v1 immuable/versionné et resolver explicable ;
- Sequence DSL v1 2..10 étapes, strict THEN, fenêtres inclusives à N ;
- research identity séparée de `AnalyticsLabRun`/`BacktestRun` ;
- tests causalité, prefix invariance, ordering, window boundaries et import boundaries ;
- aucune dépendance Forward Outcomes / trading authority.
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
    if not (root / "pyproject.toml").exists() or not (root / "app" / "analytics").exists():
        raise SystemExit("Run this script from the Money-Heist repository root.")
    head = git_head()
    if head != BASELINE:
        raise SystemExit(f"Unexpected HEAD: {head}; expected baseline {BASELINE}")
    for relative, text in DOC_ADDENDA.items():
        append_once(root / relative, text)
    print("Batch 24A.7 documentation addenda applied.")


if __name__ == "__main__":
    main()
