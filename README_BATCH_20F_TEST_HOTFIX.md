# Batch 20f — Test Hotfix post-Batch 20

Ce hotfix met à jour deux tests documentaires du Batch 19 devenus temporellement obsolètes après la clôture Batch 20.

Aucun code applicatif et aucun document projet n'est modifié.

Les invariants Recruitment restent testés :
- layout documentaire racine/docs ;
- candidat hors AgentRegistry avant promotion ;
- campagnes BASELINE / WITH_CANDIDATE ;
- coûts directs et marginaux séparés ;
- API Recruitment read-only ;
- absence de mutation automatique du registre ;
- OOS / PAPER / audit STALE ;
- séparation LIVE.

Les assertions de progression vérifient désormais :
- état courant post-Batch 20 ;
- Batch 20 — Task Force dynamique livré ;
- Batch 21 — Master Portfolio Layer comme étape suivante.
