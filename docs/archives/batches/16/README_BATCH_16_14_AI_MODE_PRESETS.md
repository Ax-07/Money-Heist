# Batch 16.14 — AI mode presets

## Objectif

Éviter la ressaisie manuelle du bloc `6 · IA` du dashboard tout en conservant
un démarrage sûr.

## Comportement

Le dashboard reste sur `MOCK` au chargement.

Quand l'opérateur change le mode IA, les champs sont préremplis :

| Mode | Budget € | Model ID | Input €/1M | Output €/1M | Cached €/1M |
| --- | ---: | --- | ---: | ---: | ---: |
| MOCK | 1.00 | mock-backtest-v1 | 0 | 0 | vide |
| CACHED | 0.25 | gpt-5.6-luna | 0.20 | 1.20 | 0.02 |
| LIVE_EVAL | 0.25 | gpt-5.6-luna | 0.20 | 1.20 | 0.02 |

Les champs restent éditables après application du preset.

## Sécurité

- `MOCK` reste sélectionné par défaut ;
- aucune clé API n'est ajoutée au navigateur ;
- aucune capacité de trading LIVE n'est ajoutée ;
- le backend, le Risk Engine et le PaperBroker ne sont pas modifiés ;
- `Code version` reste volontairement manuel et immuable pour chaque run officiel.

Les prix sont des valeurs de référence opérateur en EUR/1M. Ils sont
volontairement configurables et doivent être revérifiés si la tarification
provider change.

## Validation

```powershell
uv run pytest -q tests/dashboard/test_backtest_defaults.py
uv run pytest -q
```
