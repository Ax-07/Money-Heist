from __future__ import annotations

from pathlib import Path


BLOCKS = {
    "06_EVALUATION_ET_APPRENTISSAGE.md": """\
<!-- BATCH18A_STEP4_EVALUATION_START -->

## Addendum Batch 18a — Réputation, ablation et advisory d’état

Le Batch 18a ajoute une couche d’évaluation déterministe au-dessus des métriques agents et
du moteur historique Batch 16. Une ablation compare une baseline et un run identique sans
exactement un agent ;
les runs non comparables sont rejetés.

La réputation reste multidimensionnelle : participation, accord directionnel, confiance, coût,
latence, marginal Trading Net, marginal Economic Net et contribution au drawdown. Aucun score global
opaque n’est utilisé comme autorité.

Pour une recommandation de changement d’état fondée sur l’ablation, la preuve consommée par
`ReputationAdvisoryService` doit être OOS-only. Les seuils sont injectés explicitement via
`ReputationPolicy` et `ReputationPolicyThresholds` ; les valeurs de tests ne constituent pas des
seuils de production.

Les recommandations `HOLD / PROMOTE / DEMOTE / REDUCE_FREQUENCY` sont advisory-only. Elles ne
modifient jamais `AgentRegistry`, ne peuvent pas s’auto-appliquer (`auto_apply=False`) et ne
changent ni le Risk Engine, ni le broker, ni PAPER/SHADOW/LIVE. Les fonctions Core restent
protégées.

Chaque `AgentReputationAdvisoryReport` conserve la provenance des comparaisons et un fingerprint
SHA-256 déterministe afin de rendre la recommandation reconstruisible et auditable.

<!-- BATCH18A_STEP4_EVALUATION_END -->
""",
    "08_API_ET_MODELES_DE_DONNEES.md": """\
<!-- BATCH18A_STEP4_API_START -->

## Addendum Batch 18a — Contrats réputation et ablation

Contrats publics principaux :
- `AblationRunDescriptor`, `AblationComparison`, `AblationAggregate` ;
- `ReputationPolicy`, `AgentReputationProfile` ;
- `ReputationPolicyThresholds`, `AgentStateEvidence`, `AgentStateRecommendation` ;
- `DeterministicAgentStateAdvisor` ;
- `ReputationEvidenceProvenance`, `AgentReputationAdvisoryReport` ;
- `ReputationAdvisoryService` ;
- `reputation_advisory_to_dict()` / `reputation_advisory_to_json()`.

Les deltas d’ablation utilisent les conventions suivantes : `baseline - ablated` pour Trading
Net et Economic Net, `ablated - baseline` pour la réduction de drawdown. Une valeur positive de
`drawdown_reduction_pct` signifie donc que la présence de l’agent a réduit le drawdown observé.

Le rapport advisory inclut l’état courant lu dans le registry, les preuves, les seuils
explicitement fournis, la recommandation et sa provenance. Il ne contient aucune opération de
mutation du registry ou d’activation LIVE.

<!-- BATCH18A_STEP4_API_END -->
""",
    "09_ROADMAP_DEVELOPPEMENT.md": """\
<!-- BATCH18A_STEP4_ROADMAP_START -->

## Addendum Batch 18a — Fondations réputation et ablation livrées

Le sous-batch 18a est livré avec :
- comparaison d’ablation déterministe sur runs comparables ;
- agrégation et réputation multidimensionnelle ;
- politique advisory de recommandation d’état avec seuils injectés ;
- bridge OOS-only réputation/ablation vers `AgentStateEvidence` ;
- provenance et fingerprint d’audit déterministes ;
- exports publics de la couche Evaluation ;
- aucune mutation automatique des états agents et aucun impact LIVE.

Cette livraison fournit l’infrastructure de preuve du Batch 18. Elle ne constitue pas, à elle
seule, une validation empirique d’un agent : les campagnes comparables réelles et les seuils
opérateur
pré-définis restent nécessaires avant toute décision organisationnelle.

<!-- BATCH18A_STEP4_ROADMAP_END -->
""",
}


def upsert_block(text: str, block: str) -> tuple[str, bool]:
    start = block.splitlines()[0]
    end = block.rstrip().splitlines()[-1]
    if start in text:
        before, remainder = text.split(start, 1)
        if end not in remainder:
            raise ValueError(f"found start marker without end marker: {start}")
        _, after = remainder.split(end, 1)
        updated = before.rstrip() + "\n\n" + block.strip() + after
        return updated.rstrip() + "\n", updated.rstrip() + "\n" != text
    updated = text.rstrip() + "\n\n" + block.strip() + "\n"
    return updated, True


def update_document(path: Path, block: str) -> bool:
    if not path.exists():
        return False
    original = path.read_text(encoding="utf-8")
    updated, changed = upsert_block(original, block)
    if changed:
        path.write_text(updated, encoding="utf-8")
    return changed


def main(root: Path | None = None) -> int:
    root = Path.cwd() if root is None else root
    changed: list[str] = []
    found = 0
    for filename, block in BLOCKS.items():
        for candidate in (root / filename, root / "docs" / filename):
            if not candidate.exists():
                continue
            found += 1
            if update_document(candidate, block):
                changed.append(str(candidate.relative_to(root)))
    if found == 0:
        raise SystemExit("No Money Heist reference documents found")
    if changed:
        print("Batch 18a documentation updated:")
        for path in changed:
            print(f"- {path}")
    else:
        print("Batch 18a documentation already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
