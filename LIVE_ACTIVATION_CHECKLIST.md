# Batch 15 — Checklist d'activation LIVE 100 €

Cocher uniquement après preuve locale. Un élément `UNKNOWN` signifie **STOP**.

## Dépôt et logiciel

- [ ] `git status --short` est vide avant intégration.
- [ ] baseline post-Batch 14 = `10622f0da59cbb5ba03a66dcdf2bfeba919baf53`.
- [ ] ZIP Batch 15 extrait à la racine du dépôt.
- [ ] `uv sync` réussi.
- [ ] `uv run alembic upgrade head` réussi ; révision `0002` active.
- [ ] `uv run pytest -q` entièrement vert hors tests explicitement opt-in.
- [ ] aucun secret détecté dans le diff Git.

## Configuration

- [ ] `APP_ENV=production` explicite.
- [ ] `RUNTIME_MODE=LIVE` explicite.
- [ ] `LIVE_ENVIRONMENT=kraken_spot_eur` explicite.
- [ ] `LIVE_SYSTEM_ID=balanced_v1` explicite.
- [ ] aucun agent ne reçoit le contrôleur d'activation.
- [ ] aucun endpoint Dashboard/API ne permet de soumettre directement un ordre ou d'armer le LIVE.

## Risk / système

- [ ] profil `balanced` uniquement.
- [ ] toutes les limites constitutionnelles Balanced sont déjà résolues et validées hors Batch 15.
- [ ] aucune valeur de risque n'a été créée à partir des 100 €.
- [ ] Risk Engine inchangé et tests verts.
- [ ] kill switch testé et compatible avec `STOP_NEW_TRADES`.
- [ ] système cible non-SHADOW.
- [ ] SHORT d'entrée impossible sur Spot LIVE.
- [ ] aucune marge / dérivé / leverage parameter dans le broker LIVE.

## Capital

- [ ] capital prototype confirmé par l'opérateur : **100 €**.
- [ ] ce montant n'est pas utilisé par Batch 15 pour inventer sizing, drawdown, stop, fréquence ou risque.

## Kraken / secrets

- [ ] clé dédiée au trading.
- [ ] clé/secret hors Git, hors logs, hors prompts, hors ZIP.
- [ ] `GetApiKeyInfo` passe.
- [ ] permissions exactes : `query-funds`, `query-open-trades`, `query-closed-trades`, `modify-trades`, `close-trades`.
- [ ] `withdraw-funds` absent.
- [ ] `add-withdraw-address` absent.
- [ ] `update-withdraw-address` absent.
- [ ] aucune autre permission inutile détectée.
- [ ] les recommandations Kraken de protection de clé ont été appliquées selon l'environnement opérateur.

## Market Data / contraintes

- [ ] paramètres de fraîcheur Batch 13 explicitement configurés, non inventés par Batch 15.
- [ ] timeframes configurés explicitement.
- [ ] BTC/EUR `online`, metadata fraîche, constraints valides.
- [ ] ETH/EUR `online`, metadata fraîche, constraints valides.
- [ ] SOL/EUR `online`, metadata fraîche, constraints valides.
- [ ] source = Kraken Spot.
- [ ] quote = EUR.

## Persistance / audit / reprise

- [ ] tables `live_orders`, `live_fills`, `live_audit_events`, `live_reconciliation_state`, `live_safety_state` présentes.
- [ ] écriture/lecture SQLite opérationnelle.
- [ ] audit durable opérationnel.
- [ ] `live_safety_state` initialisé explicitement par l’opérateur ; absence = `UNKNOWN/BLOCKED`.
- [ ] aucune ambiguïté `UNKNOWN` / `RECONCILIATION_REQUIRED` restante.
- [ ] aucun ordre Kraken ouvert inattendu.
- [ ] fills connus persistés.
- [ ] réconciliation de démarrage réussie après le dernier démarrage/perte de connexion.
- [ ] test de reprise après crash/état `NEW` effectué hors réseau réel.

## Preflight final

- [ ] `uv run python -m app.trading.live.preflight_cli` exécuté par l'opérateur.
- [ ] sortie archivée/transmise sans secrets.
- [ ] `status = READY`.
- [ ] `reason_codes = []`.
- [ ] fingerprint du preflight enregistré dans l'audit.
- [ ] aucun ordre n'a été soumis par la commande.

## Avant le premier ordre réel

- [ ] résultat local suite complète transmis et validé.
- [ ] résultat preflight transmis et validé.
- [ ] autorisation humaine explicite donnée après ces validations.
- [ ] runtime redémarré/repréflighté si un redémarrage est intervenu entre-temps.

Si une case critique n'est pas cochée : **aucune nouvelle position**.
