# Money Heist — Sécurité et Opérations

**Document :** Sécurité, exploitation et résilience  
**Version :** 0.1  
**Statut :** Spécification initiale

---

## 1. Objectif

Empêcher qu’une erreur :
- IA ;
- code ;
- donnée ;
- configuration ;
- exchange ;
- opérateur ;

ne transforme un incident limité en perte incontrôlée.

---

## 2. Modèle de confiance

### Non fiables par défaut
- sorties LLM ;
- news externes ;
- texte non structuré ;
- données stale ;
- réponses API partielles ;
- inputs utilisateur non validés.

### Autoritatifs
- configuration sécurité validée ;
- Risk Engine ;
- état exchange réconcilié ;
- contrôles d’accès ;
- kill switch.

---

## 3. Secrets

Règles :
- jamais dans Git ;
- jamais dans prompts ;
- jamais dans logs ;
- jamais dans ZIP de livraison ;
- variables d’environnement ou gestionnaire de secrets.

Un `.env.example` ne contient que des noms de variables fictifs.

---

## 4. Exchange API

Permissions minimales.

Pour le trading :
- lecture ;
- trading si nécessaire ;
- **aucun retrait**.

Si l’exchange permet :
- IP allowlist ;
- sous-compte dédié ;
- limites d’API ;

ces options devront être évaluées avant LIVE.

---

## 5. Autorité des agents

Les agents n’accèdent jamais :
- aux clés ;
- au filesystem arbitraire en production ;
- aux commandes shell de production ;
- aux paramètres constitutionnels ;
- aux fonctions de retrait.

Ils reçoivent uniquement des outils explicitement autorisés.

---

## 6. Validation des tool calls

Chaque appel :
- schéma strict ;
- types ;
- bornes ;
- allowlist ;
- journalisation.

Une demande hors schéma est rejetée.

---

## 7. Kill Switch

Doit être :
- indépendant des LLM ;
- immédiat ;
- testable ;
- observable.

Modes possibles :
- `STOP_NEW_TRADES` ;
- `STOP_AI` ;
- `EMERGENCY_MODE`.

La politique des positions ouvertes sera définie avant LIVE.

---

## 8. Fail-safe

Règle centrale :

> En cas de doute sur l’autorisation d’une nouvelle position, ne pas l’ouvrir.

---

## 9. Panne IA

Si modèle indisponible :
- aucune nouvelle décision nécessitant l’IA ;
- pas de remplacement improvisé par un modèle non configuré ;
- gestion déterministe des positions existantes.

---

## 10. Prompt injection / données externes

Si des news ou textes externes sont ajoutés plus tard :
- les traiter comme données, pas comme instructions ;
- séparer contenu et directives système ;
- filtrer les URLs/outils ;
- aucun texte externe ne peut modifier les permissions.

---

## 11. Données incohérentes

Si plusieurs sources divergent :
- marquer l’incertitude ;
- éventuellement suspendre le symbole ;
- ne pas laisser un agent “choisir” arbitrairement la source qui confirme sa thèse.

---

## 12. Base de données

Exigences :
- migrations versionnées ;
- transactions ;
- sauvegarde ;
- journalisation d’erreurs ;
- contraintes d’intégrité.

Pour LIVE, une impossibilité d’audit peut déclencher le blocage des nouvelles positions.

---

## 13. Logs

Ne jamais logger :
- secrets ;
- tokens API ;
- headers d’auth ;
- contenu sensible inutile.

Logger :
- ids ;
- décisions ;
- erreurs ;
- coûts ;
- raisons de rejet ;
- transitions d’état.

---

## 14. Audit

Une chaîne complète doit être reconstructible :

```text
snapshot
→ opportunité
→ appels agents
→ proposition
→ risk decision
→ ordre
→ fills
→ position
→ sortie
```

---

## 15. Horloge

Utiliser des timestamps cohérents, idéalement UTC en stockage.

Eviter les ambiguïtés locales dans :
- ordres ;
- candles ;
- journaux ;
- périodes de performance.

---

## 16. Idempotence

Toute opération critique possède un identifiant stable.

Un retry ne doit pas créer un second trade.

---

## 17. Rate limits

Le système doit :
- connaître les limites API ;
- utiliser backoff ;
- éviter les boucles agressives ;
- prioriser les opérations critiques.

---

## 18. Budget IA

Le plafond IA est contrôlé par code.

Une fois atteint :
- pas de nouvelle dépense ;
- pas d’exception accordée par Lisbon ou Professor.

---

## 19. Recrutement d’agent

Un nouvel agent :
- n’a aucun accès LIVE ;
- n’a aucun secret ;
- a un budget ;
- a une date/condition d’expiration si temporaire ;
- passe en SHADOW.

---

## 20. Déploiement

Avant LIVE :
- environnement reproductible ;
- configuration séparée dev/paper/live ;
- contrôle des secrets ;
- health checks ;
- démarrage/arrêt propres ;
- logs persistants.

---

## 21. Sauvegardes

A minima sauvegarder :
- configuration non secrète ;
- historique trading ;
- décisions agents ;
- coûts IA ;
- migrations.

---

## 22. Monitoring

Alertes souhaitées :
- daily loss atteint ;
- drawdown critique ;
- perte de connexion exchange ;
- données stale ;
- incohérence position ;
- budget IA proche du plafond ;
- erreur répétée d’agent ;
- kill switch actif.

---

## 23. Runbooks

Avant LIVE, documenter :
- perte de connexion ;
- ordre inconnu ;
- position inattendue ;
- clé compromise ;
- base inaccessible ;
- budget IA épuisé ;
- modèle indisponible.

Ces runbooks pourront être ajoutés dans ce document plutôt que créer de nombreux fichiers.

---

## 24. Tests sécurité

Au minimum :
- agent tente outil non autorisé ;
- secret absent ;
- double ordre ;
- données stale ;
- budget IA dépassé ;
- Risk Engine inaccessible ;
- DB inaccessible ;
- exchange timeout ;
- kill switch ;
- SHADOW tente LIVE.

---

## 25. Critères d’acceptation

Aucun passage LIVE si :
- droit de retrait actif ;
- kill switch non testé ;
- double exécution possible ;
- logs secrets ;
- absence de réconciliation ;
- Risk Engine contournable ;
- agent capable d’obtenir des permissions arbitraires.


---

## 22. Addendum Batch 16 — sécurité du replay historique

Le backtest est une frontière PAPER-only.

Le package `app/services/backtest` ne doit importer ni appeler :
- `app.trading.live` ;
- le broker LIVE Kraken ;
- le service d’activation/exécution LIVE ;
- les endpoints privés d’ordre exchange.

Des tests statiques de frontière empêchent l’introduction accidentelle de ces dépendances.

`LIVE_EVAL` est un mode d’évaluation IA et non un mode d’exécution. Il peut consommer une API modèle réelle dans le respect du budget AI Gateway, mais ne change pas le broker PAPER du replay.

La gate Batch 15 reste indépendante et fail-closed. Aucun résultat de backtest ne peut armer automatiquement le LIVE.
