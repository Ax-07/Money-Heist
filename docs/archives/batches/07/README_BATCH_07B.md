# Money Heist — Batch 07b — Intégration

## Pré-requis

Ce lot est préparé pour :

```text
main @ 6ab77a32b0b47b5691a184333bed3114c9ef3eed
feat(agents): complete Batch 07a Core Agents
```

Avant extraction, il est recommandé que `git status --short` soit vide.

## Installation

Depuis `E:\0 money heist`, extraire le ZIP directement à la racine du dépôt en autorisant le remplacement des quatre fichiers `app/agents` déjà présents et de `CHANGELOG_BATCH.md`.

Puis lancer :

```powershell
uv sync
uv run pytest -q
```

Aucune migration, variable d'environnement ou dépendance supplémentaire n'est requise.

## Résultat attendu

Le Batch ajoute Berlin, Tokyo et Nairobi sans activer d'orchestration complète : le Batch 08 restera responsable du pipeline Professor → spécialistes → Palermo → Professor.

Si le dépôt contient toujours les 125 tests validés avant ce lot, la suite doit désormais afficher **135 tests passés**.

## Vérification rapide du diff

Après extraction :

```powershell
git status --short
git diff -- app/agents tests/agents CHANGELOG_BATCH.md README_BATCH_07B.md MANIFEST_BATCH_07B.txt
```

Les seuls changements attendus sont ceux listés dans `MANIFEST_BATCH_07B.txt`.
