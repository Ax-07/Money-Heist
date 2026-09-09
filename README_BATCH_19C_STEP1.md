# Batch 19c — Step 1 — Recruitment → Batch 18 Ablation Bridge

Baseline attendue : Batch 19b Step 3 installé et validé localement.

## Objectif

Adapter une campagne Recruitment `BASELINE` vs `WITH_CANDIDATE` déjà exécutée et acceptée par le gate de preuve vers le contrat existant `app.evaluation.ablation.AblationComparison`.

Le bridge ne recalcule pas les métriques marginales. Il réutilise `compare_ablation(...)` du Batch 18.

## Sémantique importante

Dans Batch 18, le paramètre `baseline` de `compare_ablation` représente le système complet **avec** l'agent étudié, et `ablated` le même système **sans** cet agent.

Pour Recruitment :

- `WITH_CANDIDATE` → côté Batch 18 `baseline` (système complet avec candidat) ;
- `BASELINE` incumbent → côté Batch 18 `ablated` (système sans candidat).

Ainsi :

- `marginal_trading_net = WITH_CANDIDATE - BASELINE` ;
- `marginal_economic_net = WITH_CANDIDATE - BASELINE` ;
- `drawdown_reduction_pct = drawdown(BASELINE incumbent) - drawdown(WITH_CANDIDATE)` ;
- `additional_ai_cost_eur = ai_cost(WITH_CANDIDATE) - ai_cost(BASELINE incumbent)`.

## Sécurité et gouvernance

Le bridge :

- recalcule le `RecruitmentEvidenceGateDecision` avant adaptation ;
- refuse un gate BLOCK ;
- refuse un gate stale ou altéré ;
- n'évalue pas encore les success criteria ;
- ne prend aucune décision de recrutement ;
- ne change pas le lifecycle ;
- ne crée ni ne modifie `AgentRegistryEntry` ;
- ne touche pas au Risk Engine ;
- n'a aucune autorité LIVE.

Un bridge DIAGNOSTIC DESIGN/VALIDATION peut exister si le gate diagnostic est ALLOW, mais il conserve `is_out_of_sample=False`. Les recommandations ultérieures doivent continuer à appliquer les règles OOS du Batch 18/19.

## Installation

Extraire l'archive à la racine du dépôt.

## Tests

```powershell
uv run pytest -q tests/recruitment
uv run pytest -q
```

Puis :

```powershell
git status --short
```

Ne pas commit/push avant validation locale. Ne pas utiliser `git add -A`.
