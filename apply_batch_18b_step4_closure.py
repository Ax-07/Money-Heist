from __future__ import annotations

from pathlib import Path

_BLOCKS = {
    "evaluation": """## Addendum Batch 18b — Campagnes d'ablation exécutables

Batch 18b complète les fondations Batch 18a avec une campagne reproductible baseline + twins.
`build_ablation_campaign()` fige l'identité expérimentale, puis un variant `WITHOUT_AGENT` retire
exactement un spécialiste. `AblationCampaignExecutor` exécute chaque variant via Batch 16
et produit
un `AblationCampaignExecutionReport` ainsi que les `AblationComparison` correspondantes.

L'assemblage concret PAPER/Risk ne vit pas dans `app.evaluation`. Il appartient à
`app.services.backtest.ablation_runtime`, qui recrée broker, portfolio, lifecycle, journal, budget,
usage recorder, AI Gateway et instances spécialistes pour chaque variant. Evaluation reste une
couche de mesure/advisory sans autorité d'exécution.

Les exports de campagne conservent les identités, métriques et fingerprints nécessaires
à l'audit,
mais n'exposent pas les objets runtime/replay bruts. Aucune campagne d'ablation n'autorise le LIVE
trading et aucune recommandation de réputation n'est auto-appliquée.
""",
    "api": """## Addendum Batch 18b — Modèles de campagne d'ablation

Contrats publics principaux :
- `AblationCampaignPlan` : identité, crew baseline, cibles et variants ;
- `AblationCampaignVariant` : BASELINE ou WITHOUT_AGENT avec `BacktestRun` dédié ;
- `AblationCampaignExecutionReport` : exécutions, comparaisons et fingerprint d'exécution ;
- `PaperAblationRuntimeSettings` : RiskProfile, MarketConstraints, budget/pricing IA et clients ;
- `PaperAblationRuntimeFactory` : stack PAPER/Batch 16 neuf par variant ;
- `ablation_campaign_execution_to_dict/json()` : export compact d'audit.

Les symboles Batch 18b exposés depuis `app.evaluation` et `app.services.backtest` utilisent un
chargement lazy afin d'éviter une dépendance circulaire entre Evaluation et Backtest.
""",
    "roadmap": """## Addendum Batch 18b — Batch 18 terminé

Le Batch 18 est désormais livré en deux sous-batches :
- 18a : réputation multidimensionnelle, ablation comparative, policy advisory et provenance ;
- 18b : planification déterministe, exécution baseline/twins, runtime PAPER isolé et exports.

La campagne peut produire des preuves comparables par agent sur DESIGN/VALIDATION/OOS, mais les
changements d'état restent advisory-only, soumis aux seuils opérateur pré-définis
et sans mutation
automatique du registry. Le Risk Engine reste autoritaire et aucun chemin LIVE n'est ajouté.

La prochaine étape de roadmap peut donc être **Batch 19 — Recruitment Engine**,
en réutilisant les
preuves de réputation/ablation du Batch 18 au lieu d'un score opaque ou d'un simple rendement.
""",
    "backtest": """## Extension Batch 18b — Ablation Campaign Runner

Batch 18b réutilise `HistoricalReplayRunner` ; il ne crée pas un second moteur de backtest.
Pour une campagne, une baseline et un twin par agent ciblé sont construits sur le même dataset,
la même période et les mêmes hypothèses matérielles, avec des identités de run distinctes.

Chaque variant reçoit un stack PAPER indépendant : PaperBroker, portfolio, lifecycle, journal,
budget IA, usage recorder, AI Gateway et instances spécialistes. La réutilisation d'un runner ou
d'un broker entre variants est rejetée. Le crew du twin diffère de la baseline par exactement
l'agent ablaté.

`MOCK`, `CACHED` et `LIVE_EVAL` restent les modes IA Batch 16. Même en LIVE_EVAL, seule la requête
IA peut être réelle ; l'exécution de trading reste PAPER. Les contextes historiques Rio/Denver ne
sont jamais inventés et doivent provenir de datasets/providers compatibles avec le replay.
""",
    "changelog": """# Batch 18b — Ablation Campaign Runner — clôture

## Livré

- plan de campagne déterministe baseline + `WITHOUT_AGENT` ;
- `run_id` distinct par twin avec fingerprint de comparaison commun ;
- exécution Batch 16/PAPER isolée par variant ;
- conversion automatique en `BacktestPeriodReport` et `AblationComparison` ;
- rejet de toute réutilisation broker/runner entre twins ;
- PAPER Runtime Factory dans `app.services.backtest`, hors couche Evaluation ;
- spécialistes recréés avec un AI Gateway/budget/usage scope propre à chaque variant ;
- modes IA MOCK/CACHED/LIVE_EVAL conservés ;
- export compact JSON/dict du rapport de campagne ;
- exports publics lazy pour éviter les cycles Evaluation ↔ Backtest ;
- aucune mutation `AgentRegistry`, aucun bypass Risk et aucun trading LIVE.

## Clôture Batch 18

Batch 18a + 18b fournissent désormais l'infrastructure complète de réputation et d'ablation.
Une décision organisationnelle réelle reste conditionnée aux campagnes empiriques,
à l'OOS et aux
seuils opérateur pré-définis ; elle n'est jamais appliquée automatiquement.
""",
}


def upsert_marked_block(text: str, marker: str, body: str) -> str:
    start = f"<!-- {marker}_START -->"
    end = f"<!-- {marker}_END -->"
    block = f"{start}\n\n{body.strip()}\n\n{end}"
    if start in text:
        before, remainder = text.split(start, 1)
        if end not in remainder:
            raise ValueError(f"missing closing marker for {marker}")
        _, after = remainder.split(end, 1)
        return before.rstrip() + "\n\n" + block + after
    return text.rstrip() + "\n\n" + block + "\n"


def _update(path: Path, marker: str, body: str) -> bool:
    if not path.exists():
        return False
    current = path.read_text(encoding="utf-8")
    updated = upsert_marked_block(current, marker, body)
    if updated != current:
        path.write_text(updated, encoding="utf-8", newline="\n")
    return True


def apply(root: Path) -> tuple[str, ...]:
    updated: list[str] = []
    targets = (
        ("06_EVALUATION_ET_APPRENTISSAGE.md", "BATCH18B_STEP4_EVALUATION", "evaluation"),
        (
            "docs/06_EVALUATION_ET_APPRENTISSAGE.md",
            "BATCH18B_STEP4_EVALUATION",
            "evaluation",
        ),
        ("08_API_ET_MODELES_DE_DONNEES.md", "BATCH18B_STEP4_API", "api"),
        ("docs/08_API_ET_MODELES_DE_DONNEES.md", "BATCH18B_STEP4_API", "api"),
        ("09_ROADMAP_DEVELOPPEMENT.md", "BATCH18B_STEP4_ROADMAP", "roadmap"),
        ("docs/09_ROADMAP_DEVELOPPEMENT.md", "BATCH18B_STEP4_ROADMAP", "roadmap"),
        (
            "11_BACKTESTING_ET_REPLAY_HISTORIQUE.md",
            "BATCH18B_STEP4_BACKTEST",
            "backtest",
        ),
        (
            "docs/11_BACKTESTING_ET_REPLAY_HISTORIQUE.md",
            "BATCH18B_STEP4_BACKTEST",
            "backtest",
        ),
        ("CHANGELOG_BATCH.md", "BATCH18B_STEP4_CHANGELOG", "changelog"),
    )
    for relative, marker, block_name in targets:
        path = root / relative
        if _update(path, marker, _BLOCKS[block_name]):
            updated.append(relative)

    tombstone = root / "app/evaluation/ablation_campaign_runtime.py"
    if tombstone.exists():
        tombstone.unlink()
        updated.append("deleted:app/evaluation/ablation_campaign_runtime.py")
    return tuple(updated)


def main() -> None:
    changed = apply(Path.cwd())
    if not changed:
        print("Batch 18b closure: no matching files found.")
        return
    print("Batch 18b closure applied:")
    for item in changed:
        print(f"- {item}")


if __name__ == "__main__":
    main()
