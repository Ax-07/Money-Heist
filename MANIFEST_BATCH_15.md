# Manifeste — Batch 15 — Activation LIVE 100 €

## Baseline obligatoire

`10622f0da59cbb5ba03a66dcdf2bfeba919baf53` — `feat(live): complete Batch 14 secure Live Broker`

## Fichiers modifiés

- `.env.example`
- `app/config/settings.py`
- `app/storage/models.py`
- `app/trading/live/__init__.py`
- `app/trading/live/activation.py`
- `app/trading/live/store.py`

## Fichiers ajoutés

- `app/trading/live/preflight.py`
- `app/trading/live/preflight_cli.py`
- `app/trading/live/readonly.py`
- `app/trading/live/reconciliation.py`
- `app/trading/live/execution.py`
- `app/trading/live/safety.py`
- `app/trading/live/safety_cli.py`
- `migrations/versions/0002_live_activation_state.py`
- `tests/trading/live/test_batch15_preflight.py`
- `tests/trading/live/test_batch15_persistence.py`
- `tests/trading/live/test_batch15_reconciliation.py`
- `tests/trading/live/test_batch15_safety.py`
- `tests/unit/test_settings_batch15.py`
- `scripts/live_preflight.ps1`
- `config/live_balanced_profile.template.json`
- `CHANGELOG_BATCH.md`
- `MANIFEST_BATCH_15.md`
- `INTEGRATION_BATCH_15.md`
- `LIVE_PREFLIGHT.md`
- `LIVE_ACTIVATION_CHECKLIST.md`
- `LIVE_RUNBOOKS.md`

## Fichiers volontairement non modifiés

- Risk Engine et ses règles ;
- valeurs des profils de risque ;
- agents / prompts / orchestration IA ;
- Exchange Adapter public Batch 13 ;
- authentification/signature Kraken Batch 14 ;
- allowlist privée Kraken Batch 14 ;
- Dashboard (aucune commande d'exécution n'est ajoutée) ;
- dépendances `pyproject.toml` / `uv.lock`.

## Données sensibles

Aucune clé, secret, token, txid réel, balance réelle ou donnée de compte réelle n'est incluse dans le lot.
