# Money Heist — Batch 24D.1 delivery

Baseline attendue : `a010155337a446bcbd06ded32667ea667b1512d7` ou descendant validé.

Le ZIP est un overlay sans dossier wrapper. Depuis la racine du dépôt :

```powershell
git status --short
git rev-parse HEAD
git merge-base --is-ancestor a010155337a446bcbd06ded32667ea667b1512d7 HEAD

Expand-Archive `
  -Path "...\batch_24d1_decision_quality_research_foundation.zip" `
  -DestinationPath "." `
  -Force

.\verify_batch_24d1.ps1
```

Aucun commit, push, reset ou rebase n'est exécuté par le batch.

Le batch ajoute uniquement la fondation read-only 24D.1. Il ne modifie aucun composant Scanner,
agentique, Risk, PAPER, LIVE, Forward Outcome, Analytics ou frontend.
