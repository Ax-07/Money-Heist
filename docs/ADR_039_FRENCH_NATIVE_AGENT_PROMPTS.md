# ADR-039 — French Native Agent Prompts

**Date :** 2026-09-17  
**Statut :** ACCEPTED  
**Batch :** 24-FR.2 — French Native Agent Prompts  
**Baseline d'entrée :** `54e184a70e3d6cd5fea9148ba9aadb02c7e10dfd`

## Décision

Les nouvelles versions actives des prompts sont écrites nativement en français : Professor v7,
Palermo v4, Lisbon v2 et Berlin/Tokyo/Nairobi/Rio/Denver v6. Les anciennes versions anglaises restent
inchangées et adressables pour préserver la reproductibilité des backtests et replays.

Les instructions génériques Task Force et Master Professor SHADOW passent également en français.
Le transport de prompt passe à `money-heist.prompt-transport.v4` afin de distinguer explicitement les
nouveaux runs et les nouveaux préfixes de cache.

## Invariants

Aucune clé JSON, valeur d'enum, identité d'agent, chemin de source, symbole de marché, hash, identifiant
ou token contractuel n'est traduit. `LONG`, `SHORT`, `NO_TRADE`, `NO_ANALYSIS`, `NEUTRAL`, `UNKNOWN`,
`CAUTION`, `REJECT`, `SHADOW` et `LIVE` restent canoniques. Aucune autorité supplémentaire n'est accordée
aux agents et les protections Risk Engine, budget et PAPER/SHADOW/LIVE restent inchangées.
