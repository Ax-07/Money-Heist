from pathlib import Path

MARKER = "<!-- BATCH_24A5_PATTERNS_CAUSAL_LIFECYCLE -->"
SECTION = f"""

{MARKER}
## Batch 24A.5 — Patterns & Causal Lifecycle

- registry expérimental versionné de 12 patterns adapté de P5.v2 ;
- source primaire de pivots `CAUSAL_ZIGZAG` via contrat source-agnostic `PatternPivot` ;
- lifecycle causal `FORMING / CONFIRMED / FAILED / INVALIDATED` ;
- `detected_at` distinct de l'origine géométrique et aucune back-propagation du statut final ;
- breakout/invalidation sur clôture, policy intrabar conservatrice ;
- IDs stables, state fingerprints évolutifs, provenance des pivots conservée ;
- intégration `AnalyticsSnapshot` et `pattern_registry_version` ;
- observation-only : aucun impact Scanner/DecisionContext/Agents/Risk/PAPER/LIVE/Forward Outcomes ;
- calibration et comparaison de sources réservées au Batch 24A.6.
"""

FILES = (
    "docs/02_ARCHITECTURE.md",
    "docs/08_API_ET_MODELES_DE_DONNEES.md",
    "docs/09_ROADMAP_DEVELOPPEMENT.md",
    "docs/10_DECISIONS_ET_CHANGELOG.md",
    "docs/11_BACKTESTING_ET_REPLAY_HISTORIQUE.md",
    "CHANGELOG_BATCH.md",
)


def main() -> None:
    changed = []
    for name in FILES:
        path = Path(name)
        text = path.read_text(encoding="utf-8")
        if MARKER in text:
            continue
        path.write_text(text.rstrip() + SECTION.rstrip() + "\n", encoding="utf-8")
        changed.append(name)
    print("Batch 24A.5 documentation updated:")
    for name in changed:
        print(f"- {name}")


if __name__ == "__main__":
    main()
