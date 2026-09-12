# Batch 16.21w — Atomic Evidence Catalogue

## Contexte

Le LIVE_EVAL 1 mois exécuté sur
`69b817e3c4ad35bd9438029853417e9ffddb5808` a validé le mécanisme strict
`source_index` de 16.21v : les spécialistes n'émettent plus de `source_key`
libre dans le schéma fournisseur.

L'audit a toutefois révélé un défaut qualitatif : une forte proportion des
preuves Berlin/Tokyo/Nairobi citait `source_index = 0`. Dans le catalogue v3,
l'index 0 correspondait souvent au conteneur très large `market_context`.
La référence était donc syntaxiquement valide mais trop générique pour
constituer une provenance utile.

Le FINALIZE Professor restait par ailleurs sur un `source_key` texte libre et
pouvait encore produire occasionnellement un chemin mal composé.

## Correctif

### Spécialistes v4

La production Berlin/Tokyo/Nairobi/Rio/Denver passe de prompt v3 à v4.

Le catalogue v4 :

- ne contient que des chemins feuilles/scalaires ou éléments de listes ;
- exclut tous les conteneurs et namespaces parents ;
- est trié déterministement ;
- expose chaque entrée sous la forme
  `{"source_index": N, "source_key": "exact.path"}` ;
- ne s'inclut jamais lui-même ;
- ignore les valeurs `null` comme preuves disponibles.

Le schéma fournisseur continue d'exiger uniquement `source_index`, avec une
borne déterministe `0 <= source_index <= N-1`. Après validation structurée,
l'index est reconverti vers le `source_key` canonique pour le contrat public.

Le post-validator v4 utilise également les chemins feuilles : un conteneur
existant tel que `market_context` ou `opportunity.triggers` n'est plus une
référence de preuve acceptable.

### Professor v5 FINALIZE

The Professor passe de prompt v4 à v5.

PLAN conserve exactement ses responsabilités et contraintes Compute Gate.
Pendant FINALIZE uniquement :

- un `evidence_source_catalog` atomique est construit à partir de
  `opportunity`, `market_context`, `specialist_analyses`, `palermo_review`
  et l'éventuel `task_force_report` ;
- le modèle fournisseur FINALIZE est request-specific et remplace
  `evidence[].source_key` par un `source_index` entier borné ;
- le nom de schéma canonique (`ProfessorDecision` ou
  `ProfessorFinalDecision`) est conservé pour le routage et les mocks ;
- après validation structurée, les indices sont reconvertis vers les
  `source_key` canoniques ;
- le validateur de grounding downstream existant reste actif.

Les versions Professor v1-v4 et spécialistes v1-v3 restent immuables et
adressables.

## MOCK et tests

Le convertisseur déterministe MOCK devient générique pour tout schéma indexé :

- production spécialistes v4 ;
- Professor FINALIZE v5 ;
- spécialistes historiques v3 via l'ancien
  `allowed_evidence_source_keys`.

La conversion MOCK n'accepte un `source_key` canonique que s'il correspond
exactement à une entrée du catalogue de la requête. LIVE_EVAL ne bénéficie
d'aucune réparation ou normalisation de sortie.

Les clients scriptés des tests utilisent le même principe. Un chemin invalide
reste volontairement non converti afin que le schéma provider échoue
fail-closed.

## Non-changements

Aucun changement sur :

- Scanner et cadence 1h ;
- Feature Engine / calcul MTF ;
- sémantique des candles closes ;
- Compute Gate ;
- Palermo ;
- Rio/Denver data providers ;
- Risk Engine ;
- PaperBroker ;
- sizing ;
- règles de trading ;
- hard budget.

## Critères de validation

Les tests doivent démontrer :

1. catalogues spécialistes et FINALIZE triés et indexés 0..N-1 ;
2. aucun conteneur dans les catalogues v4/v5 ;
3. chemins feuilles MTF/structure exacts présents ;
4. schémas provider sans `source_key` libre ;
5. borne `source_index` appliquée localement et au strict JSON Schema ;
6. conversion déterministe index -> source_key canonique ;
7. conteneur spécialiste rejeté en v4 ;
8. chemin FINALIZE invalide rejeté au schéma provider ;
9. MOCK spécialistes + FINALIZE compatible ;
10. suite complète verte.

## Validation LIVE_EVAL suivante

Après commit, refaire d'abord un test court puis, si le catalogue est propre,
un 1 mois LIVE_EVAL comparable. Le critère principal est que les preuves
spécialistes ne puissent plus se réfugier sur un conteneur générique et que
FINALIZE ne puisse plus produire de chemin texte libre.
## Hotfix compatibilité ProfessorDecision

Le test strict v5 initial utilisait par erreur `ProfessorDecision`, le contrat
core historique, qui ne possède pas de champ `evidence`. Le contrat réellement
utilisé par le pipeline Batch 08 est `ProfessorFinalDecision`.

Le hotfix :
- teste le schéma indexé v5 avec `ProfessorFinalDecision` ;
- n'applique le modèle provider indexé que lorsque le modèle de sortie expose
  réellement un champ `evidence` ;
- conserve `TheProfessor.finalize()` / `ProfessorDecision` compatible avec son
  contrat historique, tout en continuant d'exposer le catalogue atomique dans
  le payload FINALIZE.
