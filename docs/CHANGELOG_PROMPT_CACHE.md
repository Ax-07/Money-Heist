# OpenAI Prompt Cache & AI Cost Optimization — Changelog

Baseline ciblée : `4c59ba8f6f2a4808ce388267977c61ccf978473d` (`main`, 2026-09-13).

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
