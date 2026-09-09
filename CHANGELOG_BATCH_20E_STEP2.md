# Changelog — Batch 20e Step 2

- ajout d'un plan déterministe de replay Task Force baseline/treatment ;
- ajout de clés `execution_assumptions` réservées et collision-safe ;
- ajout d'un runtime contract `PAPER` isolé par variante ;
- ajout d'un executor historique avec validation du run rejoué ;
- baseline interdite de produire des artefacts Task Force ;
- treatment limité à un report/exécution pour l'opportunité ciblée ;
- garde-fous système, période et anti-look-ahead ;
- validation des twins sur dataset/role/période/candles/opportunités ;
- production automatique de `TaskForceOutcomeComparison` et `TaskForceEvaluationReport` ;
- fingerprint SHA-256 déterministe de campagne exécutée ;
- aucune autorité Trade/Risk/Registry/LIVE.
