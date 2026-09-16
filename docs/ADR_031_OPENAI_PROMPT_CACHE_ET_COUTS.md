# ADR-031 — OpenAI Prompt Cache explicite et comptabilité des coûts IA

**Date :** 2026-09-15  
**Statut :** ACCEPTED  
**Baseline d'implémentation :** `8373fe1` — intégration Frontend cockpit + OpenAI Prompt Cache  
**Prompt transport :** `money-heist.prompt-transport.v2`

## Décision

Money Heist sépare désormais explicitement le rendu fournisseur des requêtes IA en deux zones :

```text
STABLE DEVELOPER PREFIX
- version de transport
- agent_id stable
- prompt_version
- instructions constitutionnelles / rôle / grounding stable
- nom + fingerprint du Structured Output schema
        ↓
OPENAI EXPLICIT PROMPT CACHE BREAKPOINT
        ↓
DYNAMIC USER CONTENT
- opportunity / market_context / specialist_context
- evidence_source_catalog
- analyses d'autres agents lorsque la phase le permet
- portfolio courant
- IDs / timestamps / fingerprints / valeurs du run
```

La politique est portée par `ModelRoute` / AI Gateway, pas par les agents métier. Elle est désactivée par défaut et une route doit déclarer explicitement la capacité `OPENAI_EXPLICIT` avant de pouvoir activer la policy correspondante. Le modèle n'est jamais deviné à partir de son nom.

Pour l'API Responses OpenAI actuelle, le préfixe stable est rendu comme un message `developer` contenant un bloc `input_text` terminé par `prompt_cache_breakpoint={"mode":"explicit"}`. Le suffixe dynamique est rendu ensuite comme message `user`. Le top-level `instructions` n'est donc pas utilisé en mode cache explicite, car un breakpoint explicite ne peut pas y être attaché. `store=False` reste inchangé.

`prompt_cache_key` est facultatif. Money Heist ne génère pas automatiquement une clé par run, opportunity, snapshot ou timestamp afin de ne pas fragmenter le cache. Une clé opérateur peut être configurée lorsqu'une isolation explicite est nécessaire.

## Comptabilité

Le contrat de consommation distingue :

- `input_tokens` : total d'entrée fournisseur ;
- `cached_input_tokens` : cache reads ;
- `cache_write_tokens` : cache writes ;
- `output_tokens` : sortie.

Le nombre de tokens d'entrée normaux est :

```text
normal_input_tokens = input_tokens - cached_input_tokens - cache_write_tokens
```

La combinaison est rejetée fail-closed lorsque `cached_input_tokens + cache_write_tokens > input_tokens`.

`ModelPricing` reste entièrement configuré en EUR par million de tokens et comprend quatre tarifs : input normal, cache read, cache write et output. Aucun tarif OpenAI n'est codé en dur dans le domaine. La réservation préalable du hard budget utilise le tarif d'entrée le plus défavorable parmi les trois catégories afin qu'un cache write plus cher que l'input normal ne puisse pas sous-réserver le budget.

Evaluation/Lisbon conserve à la fois le coût réel et une estimation contrefactuelle « sans cache ». Les économies nettes sont calculées comme différence entre ces deux coûts. La présence de `cached_input_tokens > 0` ne suffit jamais à déclarer une économie positive : les cache writes initiaux peuvent rendre le bilan temporairement négatif.

## Stabilité des Structured Outputs

Les schémas fournisseur des spécialistes et du Professor FINALIZE ne contiennent plus une borne supérieure dérivée de `len(evidence_source_catalog)`. Le champ fournisseur `source_index` reste un entier `>= 0` avec un schéma stable par agent/version/phase.

La sécurité de grounding n'est pas affaiblie : après validation du JSON fournisseur, Money Heist conserve la validation déterministe exacte :

```text
0 <= source_index < len(allowed_source_keys)
```

Un index hors plage, un catalogue invalide ou une référence non groundée reste une erreur fail-closed. La canonicalisation vers `source_key` reste locale et déterministe.

Ce changement de sémantique est versionné : Professor `v6`, spécialistes `v5`, transport `money-heist.prompt-transport.v2`.

## Task Force et Master Professor

Les IDs de Task Force (`task_force_id`, `execution_run_id`, `member_id`, `agent_id`) et les identités/fingerprints du Master Professor restent dans le payload dynamique. Les instructions stables demandent uniquement de recopier les valeurs depuis ce payload. Les contrôles déterministes d'identité restent inchangés.

## Backtest et reproductibilité

Le cache OpenAI ne remplace pas `money-heist.backtest-ai-cache.v2` :

```text
LIVE_EVAL + Prompt Cache OpenAI
= nouvel appel fournisseur, préfixe éventuellement réutilisé, réponse recalculée

CACHED Money Heist
= aucune délégation fournisseur, réponse complète rejouée, cache miss fail-closed
```

Les deux mécanismes restent indépendants. La policy cache et `prompt_render_version` sont enregistrés dans les `execution_assumptions` des campagnes Dashboard / Batch 16 et participent donc à l'identité du run. Aucun mélange silencieux avant/après n'est autorisé.

## Sécurité et frontières

Cette ADR ne modifie aucune autorité de trading. Risk Engine, kill switch, hard AI budget, grounding, indépendance du premier tour, Palermo, séparation PAPER/SHADOW/LIVE, cache-only `CACHED` et isolation historique anti-LIVE restent inchangés.

Le smoke OpenAI fourni n'importe aucun broker LIVE et ne soumet aucun ordre. Il sert uniquement à observer `cache_write_tokens` puis `cached_input_tokens` sur deux appels IA proches lorsque le préfixe naturel est éligible. Aucun padding artificiel n'est ajouté.

<!-- DOC_REALIGN_ADR31_START -->

## Statut d’intégration

Intégré sur `main` par `8373fe1`, puis conservé à travers les commits de rangement/nettoyage jusqu’à `9f42d3e`. La suite backend complète et la validation Frontend ont été repassées avec succès avant le réalignement documentaire du 2026-09-15.

<!-- DOC_REALIGN_ADR31_END -->
