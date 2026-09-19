# Archives documentaires Money Heist

Ce répertoire conserve les documents historiques produits pendant le développement du projet.

## Autorité

Ces fichiers sont des **archives historiques**. Ils ne décrivent pas nécessairement l’état courant et
peuvent contenir des mentions `CURRENT`, `NEXT`, `PLANNED`, des anciennes baselines, des noms de
fichiers disparus ou des procédures devenues obsolètes.

Pour l’état courant, l’ordre d’autorité reste :

1. code intégré sur GitHub `main` ;
2. `docs/00_ETAT_ACTUEL_POST_BATCH_15.md` ;
3. `docs/10_DECISIONS_ET_CHANGELOG.md` ;
4. `docs/09_ROADMAP_DEVELOPPEMENT.md` ;
5. documents actifs `docs/01_...` à `docs/12_...` et ADR spécialisés.

## Provenance

- les documents historiques Batch 02 à 21 restaurés ici proviennent du snapshot Git
  `db6c3e7d1beb15ef47fed1f86eb87f471d44a258`, immédiatement antérieur au grand nettoyage des
  artefacts de livraison du 15 septembre 2026 ;
- les documents Batch 23/24 sont déplacés depuis leur emplacement actuel sous `docs/` sans réécriture ;
- `prompt-cache/CHANGELOG_PROMPT_CACHE.md` est conservé comme historique du chantier Prompt Cache ;
- `legacy/10_DECISIONS_ET_CHANGELOG_v0.1.md` est une ancienne copie documentaire, non canonique.

Les manifests, sommes de contrôle, scripts `apply_batch_*`, scripts de vérification et changelogs de
micro-étapes non nécessaires ne sont pas restaurés dans le working tree. Ils restent récupérables dans
l’historique Git.

## Index

Voir `HISTORIQUE_BATCHS.md` pour la chronologie Batch 01 → 24D.4 et l’inventaire exact des fichiers
archivés.
