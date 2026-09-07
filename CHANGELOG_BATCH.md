# Money Heist — Batch 11 — Systèmes SHADOW

## Objectif

Ajouter la couche de systèmes SHADOW prévue par la roadmap sans modifier le Risk Engine déterministe, sans introduire de valeurs numériques de risque implicites et sans ajouter de capacité d’exécution autre que PAPER.

Flux couvert :

```text
même marché / même snapshot racine
→ Conservative / Vault
→ Balanced
→ Aggressive / Tokyo
→ orchestration isolée par système
→ Risk Engine déterministe existant
→ Paper Broker existant et isolé
→ Evaluation Batch 10 via frontière explicite
→ comparaison déterministe read-only
```

## Changements principaux

- ajout de trois identités SHADOW stables :
  - `shadow_conservative_vault_v1` ;
  - `shadow_balanced_v1` ;
  - `shadow_aggressive_tokyo_v1` ;
- aucune limite numérique de risque n'est attachée à ces identités ;
- dérivation déterministe des IDs de corrélation racine, opportunités par système et clés d'idempotence ;
- conservation du même `FeatureSnapshot` immuable pour les trois branches ;
- création d'une copie dérivée de `CandidateOpportunity` par système sans mutation de l'objet racine ;
- fan-out séquentiel dans un ordre stable afin de rendre les scénarios reproductibles ;
- isolement obligatoire des objets stateful :
  - orchestration ;
  - Paper Broker ;
  - journal/idempotence ;
  - provider de portefeuille ;
  - provider de RiskProfile ;
  - kill switch logique ;
  - comptabilité AI usage ;
  - budget IA lorsque le contrat de l'orchestration l'expose ;
  - gateway IA stateful lorsque le contrat de l'orchestration l'expose ;
- partage autorisé uniquement pour un provider de contraintes de marché explicitement immuable ;
- réutilisation du `RiskEngine` Batch 05 sans modification de ses règles ;
- réutilisation du `PaperBroker` Batch 04 et du `PaperTradingPipeline` Batch 09 ;
- lorsqu'aucun `RiskProfile` n'est injecté, utilisation de `unresolved_profile(...)` afin de conserver le comportement fail-closed existant ;
- aucun preset Conservative/Balanced/Aggressive chiffré n'est créé ;
- une erreur PAPER/orchestration d'une branche est contenue et n'arrête pas les branches suivantes ;
- une erreur Evaluation reste distincte et n'annule pas un résultat PAPER déjà produit ;
- conservation d'un historique PAPER séparé par `system_id` pour Evaluation ;
- frontière `Batch10EvaluationPort` et adaptateur `CallableBatch10EvaluationAdapter` pour raccorder l'implémentation Batch 10 installée localement sans créer de dépendance inverse depuis le pipeline PAPER ;
- projection explicite des métriques comparables :
  - PnL réalisé ;
  - Trading Net ;
  - Economic Net ;
  - coût IA ;
  - SelfFundingRatio ;
- les valeurs absentes ou impossibles à reconstruire restent `None` et produisent `UNAVAILABLE` ou `PARTIAL` ;
- calcul de deltas pairwise uniquement lorsque deux valeurs existent ;
- aucune notion de gagnant, promotion, modification automatique du risque ou transition d'agent n'est fournie par la comparaison ;
- aucune nouvelle dépendance Python.

## Tests Batch 11

49 nouveaux tests couvrent notamment :

- les trois systèmes recevant le même contexte marché immuable ;
- l'identifiant racine commun ;
- les `system_id` distincts ;
- les opportunités dérivées stables et distinctes ;
- l'idempotence indépendante ;
- les brokers, journaux, portefeuilles et profils distincts ;
- cash, equity, frais et exposition indépendants ;
- LONG et SHORT simultanés sans compensation croisée ;
- profils explicitement injectés ;
- profil non résolu sans valeur inventée et rejet `PROFILE_INCOMPLETE` ;
- réutilisation du `RiskEngine` existant ;
- acceptation et rejet différents lorsque les contextes explicitement injectés le justifient ;
- `NO_ANALYSIS`, `NO_TRADE`, `RISK_REJECTED` et erreur orchestration sans contamination des autres systèmes ;
- isolation des budgets IA lorsque le contrat actuel les expose ;
- rattachement des usages IA au bon `system_id` ;
- Evaluation distincte par système ;
- erreur Evaluation sans rollback PAPER ;
- comparaison uniquement des métriques disponibles ;
- absence d'autorité de promotion ou de modification du risque ;
- absence de surface d'exécution autre que PAPER dans le module Batch 11.

## Validation effectuée dans l'environnement de livraison

- compilation Python du module et des tests : OK ;
- 12 tests purs IDs/comparaison exécutés directement : `12 passed` ;
- 49 tests Batch 11 exécutés dans un environnement de compatibilité reproduisant les contrats Batch 09 accessibles : `49 passed`.

### Limite de validation

Au moment de la génération de ce lot, le connecteur GitHub expose `main` au commit Batch 09 `087183154dcd606f6e4977f6f738634fbc947112`. Le commit Batch 10 annoncé localement n'est pas visible sur le dépôt distant connecté. Le lot n'écrase donc aucun fichier `app/evaluation` et raccorde Batch 10 via une frontière explicite/adaptable.

La validation autoritative reste votre dépôt local contenant Batch 10 : après extraction, exécuter `uv sync` puis `uv run pytest -q`. Avec 215 tests existants et les 49 tests Batch 11 de ce lot, le total attendu est **264 tests** si aucun autre test local n'a été ajouté entre-temps.

## Hors périmètre confirmé

Ce batch n'ajoute ni moteur d'exécution réel, ni connecteur d'exchange, ni recrutement, ni Rio/Denver, ni réputation multidimensionnelle complète, ni ablation complète, ni Dashboard. Il ne modifie ni le plafond de risque, ni le Risk Engine, ni le SelfFundingRatio pour influencer le risque.
