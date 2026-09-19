# OpenAI Prompt Cache & AI Cost Optimization — Changelog

Baseline d’intégration : `8373fe1` ; état documentaire courant : `9f42d3e` (`main`, 2026-09-15).

## AI Gateway
- ajout d'une policy `DISABLED | OPENAI_EXPLICIT` déclarée par route ;
- ajout du breakpoint explicite à la fin du préfixe `developer` stable ;
- `prompt_cache_key` facultatif ;
- `store=False` conservé ;
- parsing de `cached_tokens`, `cache_write_tokens` et diagnostics optionnels ;
- comptabilité input normal / cache read / cache write / output ;
- réservation hard-budget au pire tarif d'entrée configuré ;
- version de transport `money-heist.prompt-transport.v2`.

## Agents
- schémas fournisseur stables pour `source_index` ;
- validation exacte du catalogue conservée après réponse ;
- Professor `v6` ; spécialistes `v5` ;
- Task Force et Master Professor : valeurs dynamiques sorties des instructions stables.

## Backtest / Evaluation
- cache local V2 inchangé ;
- policy/cache pricing/version de rendu inclus dans les hypothèses versionnées ;
- métriques cache par campagne/agent/modèle/route ;
- coût réel, coût sans cache et économie nette exposés ;
- Dashboard backend/frontend complétés avec tarif cache-write et policy explicite.

## Sécurité
- aucune modification du Risk Engine, du broker, du LIVE, du kill switch ou des autorisations ;
- aucun test automatisé ne nécessite de clé OpenAI ;
- smoke payant séparé et manuel uniquement.

<!-- DOC_REALIGN_PROMPT_CACHE_VALIDATION_START -->

## Validation consolidée

- backend : suite complète `pytest -q` verte, 3 tests skipped ;
- frontend : lint, typecheck, 26 tests Vitest et build Next.js verts ;
- Prompt Cache conservé après nettoyage documentaire/historique du dépôt.

<!-- DOC_REALIGN_PROMPT_CACHE_VALIDATION_END -->
