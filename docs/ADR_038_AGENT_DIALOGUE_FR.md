# ADR-038 — Dialogue IA en français, contrats machine inchangés

**Date :** 2026-09-17
**Statut :** ACCEPTED
**Chantier :** Batch 24-FR — French Agent Dialogue & Observability
**Baseline visée :** `6d67e3f25a6c95f23552a5f4f025bd1b4d29a26c`

## Décision

Tous les appels IA traversant le AI Gateway reçoivent un contrat linguistique stable :

- langue des explications humaines : `fr-FR` ;
- identifiant : `money-heist.agent-dialogue.fr.v1` ;
- transport : `money-heist.prompt-transport.v3`.

Le français s'applique au texte libre destiné à un humain ou à un autre agent. Les éléments machine restent inchangés : clés JSON, noms de champs, enums, identifiants, `source_key`, `source_index`, symboles, nombres, hashes et valeurs imposées par les schémas.

## Portée

La règle est transversale et couvre la crew principale, les spécialistes, Palermo, Lisbon, les Task Force et les autres agents utilisant `AIGatewayRequest`.

Les anciennes définitions de prompts restent présentes et adressables. Le changement linguistique est porté par `prompt_render_version`, ce qui maintient une identité de replay explicite avant/après changement.

## Invariants

- aucune modification du Risk Engine ;
- aucune autorité broker/LIVE supplémentaire ;
- aucune traduction des enums ;
- Structured Outputs stricts inchangés ;
- comptabilité tokens/coûts inchangée ;
- hausse de tokens acceptée pour améliorer l'observabilité humaine.
