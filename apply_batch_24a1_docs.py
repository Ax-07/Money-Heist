from __future__ import annotations

from pathlib import Path

SECTIONS: dict[str, tuple[str, str]] = {
    "docs/00_ETAT_ACTUEL_POST_BATCH_15.md": (
        "<!-- BATCH24A1_STATE -->",
        """
<!-- BATCH24A1_STATE -->
## Batch 24A.1 — Analytics Lab Foundation

L'Analytics Lab possède désormais une fondation observation-only distincte du
`BacktestRun` : contrats immuables, provenance dataset/as-of/MTF, versions de
composants, snapshots vides autorisés, manifeste et fingerprints déterministes.
Aucun élément Analytics n'est injecté dans Scanner, `CandidateOpportunity`,
`DecisionContextV1`, agents, Risk, PAPER ou LIVE. Les Forward Outcomes Batch 23A
restent la vérité post-hoc canonique.
""",
    ),
    "docs/02_ARCHITECTURE.md": (
        "<!-- BATCH24A1_ARCHITECTURE -->",
        """
<!-- BATCH24A1_ARCHITECTURE -->
## Analytics Lab — frontière observation-only (Batch 24A.1)

```text
Historical Replay / DatasetRef / MTF
        ├── Decision pipeline canonique
        └── Analytics Lab (read-only)
                    ↓
              artefacts Analytics
```

`app.analytics` ne possède aucune autorité de trading. Il ne peut ni créer une
opportunité, ni modifier le `DecisionContextV1`, ni influencer
Professor/Palermo/Risk/PAPER/LIVE. Le Lab réutilise l'identité dataset et le
`source_cursor_fingerprint` MTF ; il ne possède pas de seconde source de marché
ni de resampler indépendant.

`BacktestRun != AnalyticsLabRun`. Les versions Analytics restent hors du business
fingerprint tant que la couche demeure observation-only.
""",
    ),
    "docs/08_API_ET_MODELES_DE_DONNEES.md": (
        "<!-- BATCH24A1_MODELS -->",
        """
<!-- BATCH24A1_MODELS -->
## Contrats Analytics Lab — Batch 24A.1

Contrats ajoutés : `AnalyticsComponentVersions`, `AnalyticsAsOfInput`,
`AnalyticsLabRun`, `AnalyticsSnapshot`, `AnalyticsLabManifest` et
`AnalyticsObservationProvenance`.

Invariants : timestamps timezone-aware/UTC, SHA-256 validés,
`source_cursor_fingerprint` conservé, rôle DESIGN/VALIDATION/OOS explicite, IDs
et digests déterministes. `components={}` est valide tant qu'aucun moteur
Analytics n'est installé.

Aucun champ Analytics n'est ajouté à `CandidateOpportunity` ni à
`DecisionContextV1` dans ce batch.
""",
    ),
    "docs/09_ROADMAP_DEVELOPPEMENT.md": (
        "<!-- BATCH24A1_ROADMAP -->",
        """
<!-- BATCH24A1_ROADMAP -->
## Batch 24 — Analytics Lab & Decision Intelligence

### 24A.1 — Foundation, Contracts & Isolation Guards

Fondation observation-only : identité `AnalyticsLabRun`, provenance
dataset/as-of/MTF, versions, snapshots/manifeste/fingerprints déterministes et
guards AST. Aucun indicateur, event, ZigZag, pattern, attribution ou UI n'est
inclus.

Sous-batchs suivants explicitement hors scope de 24A.1 : 24A.2 Indicators,
24A.3 Technical Events, 24A.4 ZigZag, 24A.5 Patterns, 24A.6 Calibration,
24A.7 Contexts/Sequences, 24B Attribution, 24C Frontend, 24D Decision Quality
Research.
""",
    ),
    "docs/10_DECISIONS_ET_CHANGELOG.md": (
        "<!-- ADR037_ANALYTICS_LAB_OBSERVATION_ONLY -->",
        """
<!-- ADR037_ANALYTICS_LAB_OBSERVATION_ONLY -->
### ADR-037 — Analytics Lab Observation-Only Authority Boundary

**Date :** 2026-09-16
**Statut :** ACCEPTED

Le futur Analytics Lab est une dérivation read-only du Historical Replay
canonique. `BacktestRun` et `AnalyticsLabRun` ont des identités distinctes ; les
versions Analytics ne modifient pas le `BacktestRun.run_id` ni le business
fingerprint tant qu'Analytics n'influence aucune décision. `DatasetRef`/MTF
Money Heist restent la seule vérité de marché et Batch 23A reste la vérité
post-hoc canonique. Toute future injection Analytics dans `DecisionContextV1`
devra être traitée comme un batch comportemental distinct.

Voir `docs/ADR_037_ANALYTICS_LAB_OBSERVATION_ONLY.md`.
""",
    ),
    "docs/11_BACKTESTING_ET_REPLAY_HISTORIQUE.md": (
        "<!-- BATCH24A1_REPLAY -->",
        """
<!-- BATCH24A1_REPLAY -->
## Dérivation Analytics Lab (Batch 24A.1)

Un `AnalyticsLabRun` dérive d'un `BacktestRun` existant sans rerun du Scanner ni
des agents. L'adaptateur conserve `DatasetRef`, bornes de période, rôle
DESIGN/VALIDATION/OOS, politique MTF et `source_cursor_fingerprint` de l'univers
visible. Les versions Analytics produisent uniquement une nouvelle identité
Analytics.

Les Forward Outcomes 23A ne sont pas consommés par `app.analytics`; une future
jointure décision + Analytics + outcomes appartiendra à une couche d'attribution
séparée.
""",
    ),
    "CHANGELOG_BATCH.md": (
        "<!-- BATCH24A1_CHANGELOG -->",
        """
<!-- BATCH24A1_CHANGELOG -->
## Batch 24A.1 — Analytics Lab Foundation, Contracts & Isolation Guards

- package `app.analytics` observation-only ;
- identité `AnalyticsLabRun` distincte de `BacktestRun` ;
- provenance dataset/as-of/MTF et `source_cursor_fingerprint` ;
- versions Analytics, snapshots vides, manifeste et SHA-256 déterministes ;
- canonicalisation commune verrouillée par golden test sans changement
  historique attendu ;
- guards AST anti-couplage décisionnel, Forward Outcomes et LIVE ;
- aucune modification fonctionnelle Scanner/DecisionContext/Agents/Risk/PAPER/LIVE.
""",
    ),
}


def main() -> None:
    root = Path(__file__).resolve().parent
    updated: list[str] = []
    for relative, (marker, section) in SECTIONS.items():
        path = root / relative
        if not path.exists():
            raise SystemExit(f"missing canonical document: {relative}")
        text = path.read_text(encoding="utf-8")
        if marker in text:
            continue
        suffix = "" if text.endswith("\n") else "\n"
        path.write_text(text + suffix + section.lstrip("\n"), encoding="utf-8")
        updated.append(relative)
    print("Batch 24A.1 documentation updated:")
    for item in updated:
        print(f"- {item}")
    if not updated:
        print("- no changes (already applied)")


if __name__ == "__main__":
    main()
