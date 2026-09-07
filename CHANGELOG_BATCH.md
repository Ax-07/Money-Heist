# CHANGELOG — Batch 14 — LIVE Broker sécurisé

## Ajouté

- décision initiale LIVE : Kraken Spot / EUR ;
- résolution de `OPEN-005` sans valeur numérique de risque ;
- port `LiveBroker` et modèles LIVE séparés du broker PAPER ;
- `KrakenSpotLiveBroker` avec allowlists système/symboles/opérations ;
- authentification Kraken privée isolée ;
- génération `API-Sign` conforme au vecteur officiel ;
- nonce monotone ;
- credentials via frontière dédiée/environnement, représentations redacted ;
- `DenyAllLiveAuthorization` fail-closed ;
- absence de switch environnemental d'activation LIVE ;
- `client_order_id`/`cl_ord_id` stable ;
- blocage local des soumissions ambiguës ;
- réconciliation OpenOrders + ClosedOrders ;
- lectures balance/fills ;
- cancellation derrière permission explicite indépendante ;
- séparation erreurs transport/API/rejet/reconciliation ;
- retries bornés uniquement pour lectures ;
- aucun retry automatique des écritures ambiguës ;
- backoff et pacing local ;
- événements d'audit structurés ;
- contrôle préflight de permissions avec rejet de droits de retrait ;
- tests hors réseau et test privé read-only opt-in.

## Non modifié

- Risk Engine ;
- profils Conservative/Balanced/Aggressive ;
- SelfFundingRatio ;
- agents ;
- Dashboard ;
- pipeline PAPER/SHADOW ;
- connecteur public Batch 13.

## Sécurité

Batch 14 ne compose aucune route d'exécution LIVE dans l'application et ne lève pas le verrou `Settings` historique. Même avec des variables Kraken présentes, une soumission est refusée tant qu'une autorisation externe explicite n'est pas injectée. Le mécanisme opérationnel d'activation appartient au Batch 15.

## Correctif de compatibilité Pytest

- `tests/trading/live/__init__.py` rend le sous-répertoire LIVE importable comme package et évite le conflit de nom avec les tests historiques `test_security_boundaries.py` ;
- les tests async du Batch 14 utilisent `asyncio.run(...)` et ne nécessitent pas `pytest-asyncio` ;
- aucune dépendance supplémentaire n'est ajoutée à `pyproject.toml`.
