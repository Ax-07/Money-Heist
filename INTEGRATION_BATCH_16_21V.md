# Batch 16.21v — Strict Specialist Evidence Schema

## Contexte

Le LIVE_EVAL sur `18a30bef3031ed7781de2215c982ad302b24ddd9` a validé
le grounding FINALIZE et la sémantique temporelle MTF de 16.21u. Il restait
toutefois des réponses spécialistes qui inventaient des chemins plausibles mais
absents du payload réel.

Exemples observés :

- `market_context.decision_context.market.snapshots.15m.swing_structure`
- `market_context.decision_context.market.snapshots.15m.breakout_state`
- `market_context.decision_context.market.snapshots.4h.swing_structure`

Les champs structurels réels sont sous
`market_context.decision_context.structure.payload.timeframes.<tf>...`.

Le validateur post-provider les rejetait correctement, mais le coût fournisseur
avait déjà été engagé et l'opportunité échouait ensuite en fail-closed.

## Correctif

La production spécialiste passe de prompt `v2` à `v3`. Les versions `v1` et
`v2` restent immuables et adressables.

Pour chaque appel v3 :

1. les chemins autorisés sont construits déterministement comme avant ;
2. ils sont exposés dans `allowed_evidence_source_keys`, triés ;
3. le schéma fournisseur ne contient plus de `source_key` texte libre ;
4. chaque evidence renvoie un `source_index` entier ;
5. le modèle Pydantic provider est construit dynamiquement avec
   `0 <= source_index <= len(allowed_evidence_source_keys) - 1` ;
6. le Gateway strict transmet cette borne au JSON Schema ;
7. après validation structurée, le code convertit l'index vers le vrai
   `source_key` canonique ;
8. `_assert_grounded_evidence` reste actif comme seconde barrière fail-closed.

Le contrat public ne change pas : `BerlinAnalysis`, `TokyoAnalysis`,
`NairobiAnalysis`, `RioAnalysis` et `DenverAnalysis` continuent de sortir des
`evidence[].source_key` exacts.

## Pourquoi un index borné

Un grand enum de chemins texte gonflerait le JSON Schema et peut rencontrer les
limites de taille des Structured Outputs. Un entier borné reste compact et ne
permet aucune invention syntaxique de chemin.

## Non-changements

Aucun changement sur Scanner, cadence 1h, Feature Engine, construction MTF,
Professor, Palermo, Compute Gate, orchestration, fournisseurs Rio/Denver,
Risk Engine, PaperBroker, règles de trading ou politique de budget.

## Régressions

Les tests vérifient :

- production spécialiste sur prompt v3 ;
- v1/v2 toujours disponibles ;
- modèle provider request-specific sous-classe du modèle canonique ;
- `source_index` borné de 0 à N-1 ;
- absence de `source_key` libre dans le JSON Schema provider ;
- rejet local d'un index hors plage ;
- conversion déterministe index -> `source_key` ;
- maintien du validateur post-provider historique ;
- compatibilité Rio/Denver.

## Validation suivante

Après commit, refaire 1 mois LIVE_EVAL avec la configuration scientifique
inchangée et un hard budget suffisant pour couvrir le mois entier. Vérifier
ensuite la traversée `PLAN -> spécialistes -> Palermo -> FINALIZE` et la
disparition des échecs spécialistes `UNGROUNDED_EVIDENCE`.

## Compatibilité provider / MOCK — correctif de validation

La première application locale de 16.21v a révélé un effet de bord de compatibilité :

- le modèle Pydantic dynamique portait un nom de classe suffixé, ce qui modifiait
  `schema_name` et cassait les routeurs MOCK basés sur les noms canoniques ;
- les fournisseurs déterministes MOCK et les clients scriptés de tests émettaient
  encore le contrat canonique `source_key` alors que le schéma provider v3 exige
  `source_index`.

Le correctif conserve le nom de schéma canonique (`BerlinAnalysis`,
`TokyoAnalysis`, `NairobiAnalysis`, `RioAnalysis`, `DenverAnalysis`) tout en
gardant une classe Pydantic request-specific avec `source_index` borné.

Les fournisseurs MOCK convertissent désormais leurs `source_key` déterministes
vers `source_index` uniquement lorsque `prompt_version == "v3"`, et uniquement
si le chemin est un membre exact de `allowed_evidence_source_keys`.

LIVE_EVAL reste inchangé et strict : aucune réécriture d'une sortie OpenAI
`source_key` invalide n'est effectuée. Les chemins invalides sont bloqués par le
schéma structuré avant le post-validator.

## Intégrations direct-Gateway — compatibilité v3

Les fixtures d'intégration qui injectent directement des objets Pydantic
canoniques dans un faux `generate_structured()` acceptent désormais que le
`output_model` demandé soit une sous-classe request-specific de leur type
canonique.

Ce changement est limité aux doubles de Gateway de test :

- `tests/orchestration/test_advanced_specialists.py`
- `tests/orchestration/test_rio_paper_shadow_integration.py`

Il ne modifie ni le Gateway réel, ni OpenAI Structured Outputs, ni LIVE_EVAL.
Le test spécialiste strict dédié continue de valider que le vrai modèle
provider v3 expose un `source_index` borné et non un `source_key` libre.

