# Money Heist — Batch 11 — Systèmes SHADOW

Ce lot ajoute trois systèmes SHADOW PAPER isolés — Conservative/Vault, Balanced et Aggressive/Tokyo — qui peuvent traiter le même événement de marché avec leurs propres décisions, contextes de risque, brokers, portefeuilles logiques, journaux, coûts IA et évaluations.

Le module central est `app/services/shadow/`.

Principes garantis :

- aucune valeur de risque Conservative/Balanced/Aggressive n'est inventée ;
- un profil non configuré reste incomplet et échoue fermé ;
- chaque système reçoit une opportunité dérivée stable mais conserve la même corrélation racine ;
- l'idempotence PAPER est indépendante par système ;
- les objets stateful ne sont pas partagés ;
- les données de marché immuables peuvent être partagées ;
- le `RiskEngine`, le `PaperBroker` et le pipeline PAPER existants sont réutilisés ;
- les erreurs d'une branche n'arrêtent pas les autres ;
- Evaluation et comparaison sont read-only ;
- aucune promotion ou modification automatique du risque n'existe dans ce batch.

Voir `INTEGRATION_BATCH_11.md` pour l'installation et `CHANGELOG_BATCH.md` pour le détail.
