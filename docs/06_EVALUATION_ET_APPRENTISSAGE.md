# Money Heist — Evaluation et Apprentissage

**Document :** Evaluation, validation et évolution  
**Version :** 0.1  
**Statut :** Spécification initiale

---

## 1. Objectif

Définir comment Money Heist détermine :
- si le trading possède un edge ;
- si l’IA apporte une valeur marginale ;
- quels agents sont utiles ;
- quelles stratégies fonctionnent ;
- quand un nouvel agent mérite une promotion ;
- si le système se rapproche de l’autofinancement.

---

## 2. Principe

Une performance positive n’est pas une preuve suffisante.

Le système cherche :
- robustesse ;
- répétabilité ;
- performance nette de frais ;
- stabilité par régime ;
- maîtrise du drawdown ;
- valeur marginale du compute.

---

## 3. Deux PnL

### Trading Net

```text
PnL brut
- frais
- slippage
- funding
= Trading Net
```

### Economic Net

```text
Trading Net
- coût IA
- infrastructure attribuable
= Economic Net
```

Ces deux valeurs restent séparées.

---

## 4. KPI d’autofinancement

```text
SelfFundingRatio =
Valeur nette générée
--------------------
Coût IA
```

Interprétation :
- `< 1` : non autofinancé ;
- `= 1` : break-even ;
- `> 1` : autofinancé.

Ce KPI ne doit jamais devenir une permission d’augmenter le risque.

---

## 5. Métriques trading

Minimum :
- rendement ;
- PnL net ;
- win rate ;
- profit factor ;
- expectancy ;
- R/R réalisé ;
- drawdown ;
- volatilité ;
- Sharpe ;
- Sortino ;
- temps en position ;
- turnover ;
- frais / PnL brut.

---

## 6. Métriques agent

Pour chaque agent :
- nombre d’appels ;
- coût total ;
- coût moyen ;
- latence ;
- position proposée ;
- confiance ;
- précision directionnelle ;
- calibration ;
- fréquence de désaccord ;
- décisions modifiées ;
- contribution estimée.

---

## 7. Calibration

Exemple :

Si un agent émet souvent `confidence = 0.80`, on vérifie empiriquement si ses prédictions correspondantes réussissent environ à la fréquence attendue selon la définition retenue.

La confiance doit être analysée par buckets.

---

## 8. Attribution

Il est difficile d’attribuer précisément un PnL à un agent.

Le système utilise plusieurs méthodes.

### 8.1 Decision-change attribution

Mesurer :
- décision avant agent ;
- décision après agent.

### 8.2 Veto attribution

Pour Palermo :
- trades bloqués ;
- résultat contrefactuel simulé ;
- pertes potentiellement évitées ;
- gains potentiellement manqués.

### 8.3 Ablation

Comparer :
- Full Crew ;
- Crew sans un agent ;
- Mini Crew ;
- modèle moins coûteux.

### 8.4 SHADOW twins

Faire tourner des variantes en parallèle sur les mêmes données.

---

## 9. Prudence contrefactuelle

Un “trade évité” n’a pas de résultat réel.

Son résultat est simulé.

Le dashboard doit clairement distinguer :
- réalisé ;
- simulé ;
- estimé.

---

## 10. Réputation

La réputation n’est pas un unique score magique.

Dimensions :
- trend regime ;
- range regime ;
- high volatility ;
- actif ;
- timeframe ;
- coût ;
- calibration ;
- drawdown contribution.

---

## 11. Changement d’état d’un agent

Un agent peut passer en :
- ON_DEMAND ;
- SHADOW ;
- PROBATION ;
- ACTIVE.

Les transitions doivent reposer sur :
- taille minimale d’échantillon ;
- métriques pré-définies ;
- absence de problème sécurité ;
- coût acceptable.

---

## 12. Recrutement

Un candidat doit battre une baseline définie avant le test.

Exemples de critères :
- amélioration du profit factor ;
- baisse du drawdown ;
- meilleure calibration ;
- amélioration de l’EV ;
- coût marginal justifié.

La métrique de succès est définie avant le test pour limiter le cherry-picking.

---

## 13. Backtest

Le moteur doit permettre :
- replay chronologique ;
- mêmes indicateurs que production ;
- mêmes règles de risque ;
- frais ;
- slippage ;
- capital évolutif.

---

## 14. Biais à prévenir

### Look-ahead bias
Aucune donnée future.

### Overfitting
Limiter les ajustements après observation.

### Survivorship bias
Pertinent lors de l’élargissement de l’univers.

### Data snooping
Documenter les essais.

### Selection bias
Ne pas promouvoir uniquement les variantes chanceuses.

---

## 15. Out-of-sample

Séparer :
- période de conception ;
- validation ;
- test final.

Ne pas réutiliser indéfiniment le même “test final” pour optimiser.

---

## 16. Walk-forward

Processus cible :

```text
Train/Design window
→ Validation
→ Forward window
→ Roll
```

Les détails dépendent des stratégies utilisées.

---

## 17. PAPER et SHADOW

Avant LIVE :
- suffisamment de décisions ;
- erreurs techniques rares ;
- métriques stables ;
- performance nette des coûts simulés ;
- aucun échec sécurité.

Le nombre exact de trades requis sera décidé plus tard.

---

## 18. Promotion LIVE

Une stratégie ou crew SHADOW n’est pas promue uniquement parce qu’elle a le meilleur rendement.

Critères possibles :
- drawdown ;
- stabilité ;
- coût IA ;
- nombre de trades ;
- sensibilité aux frais ;
- performance par régime.

---

## 19. Comparaison de prompts et modèles

Toute nouvelle version peut être testée en SHADOW.

Exemple :

```text
Professor prompt v3
vs
Professor prompt v4
```

Même marché, même période, journalisation distincte.

---

## 20. Compute ROI

Pour chaque type d’analyse :

```text
ComputeROI =
valeur marginale estimée
------------------------
coût IA
```

Une analyse coûteuse peut être conservée si elle réduit fortement le tail risk même si elle n’augmente pas directement le rendement brut.

---

## 21. Mémoire

La mémoire opérationnelle doit être structurée.

Préférer :
- tables ;
- statistiques ;
- features ;
- résultats ;
- versions.

Eviter une mémoire narrative libre utilisée comme preuve.

---

## 22. Auto-amélioration

Le système peut :
- recommander de nouveaux agents ;
- recommander des changements de fréquence ;
- recommander un nouveau prompt ;
- recommander un modèle moins cher ;
- recommander une expérimentation.

Le système ne peut pas :
- déployer automatiquement un changement LIVE critique ;
- modifier les garde-fous ;
- déclarer une hypothèse “prouvée” sans métriques.

---

## 23. Critères de qualité d’une expérimentation

Chaque expérimentation possède :
- hypothèse ;
- baseline ;
- métrique primaire ;
- métriques secondaires ;
- période ;
- budget ;
- critères d’arrêt ;
- résultat.

---

## 24. Rapports Lisbon

Rapport type :
- dépenses IA ;
- coût par agent ;
- coût par décision ;
- agents sous-utilisés ;
- agents coûteux ;
- valeur marginale ;
- self-funding ratio ;
- recommandations.

---

## 25. Critères d’acceptation

La couche Evaluation est correcte si :
- réel et simulé sont séparés ;
- coûts IA sont intégrés ;
- versions de prompts sont comparables ;
- tests d’ablation sont possibles ;
- promotion SHADOW → LIVE est contrôlée ;
- aucune métrique unique ne suffit automatiquement à contourner le risque.


---

## 26. Addendum Batch 16 — Evaluation historique, OOS et walk-forward

Le moteur Batch 16 réutilise `EvaluationService` du Batch 10. Il reconstruit une `EvaluationSource` depuis les ordres/fills PAPER, l’equity curve, les traces d’orchestration et les `AIUsageRecord` disponibles.

Les métriques incluent notamment PnL net, frais, slippage, win rate, expectancy, profit factor, drawdown, exposition, coûts IA, métriques agents, Economic Net et Self-Funding Ratio.

Les périodes sont explicitement séparées :
- `DESIGN` : conception/hypothèses ;
- `VALIDATION` : vérification avant gel ;
- `OOS` : évaluation hors échantillon.

Le rapport OOS reste distinct des métriques DESIGN/VALIDATION.

Le walk-forward V1 génère des fenêtres roulantes DESIGN → VALIDATION → OOS à configuration figée. Il n’intègre pas d’optimiseur automatique.

Les modes IA sont :
- `MOCK` : déterministe ;
- `CACHED` : cache-only fail-closed ;
- `LIVE_EVAL` : fournisseur IA réel autorisé via AI Gateway/budgets, mais trading PAPER uniquement.

Un fingerprint business compare les sorties économiques et décisions déterministes sans dépendre d’identifiants techniques volatils sans impact business.

<!-- BATCH18A_STEP4_EVALUATION_START -->

## Addendum Batch 18a — Réputation, ablation et advisory d’état

Le Batch 18a ajoute une couche d’évaluation déterministe au-dessus des métriques agents et
du moteur historique Batch 16. Une ablation compare une baseline et un run identique sans
exactement un agent ;
les runs non comparables sont rejetés.

La réputation reste multidimensionnelle : participation, accord directionnel, confiance, coût,
latence, marginal Trading Net, marginal Economic Net et contribution au drawdown. Aucun score global
opaque n’est utilisé comme autorité.

Pour une recommandation de changement d’état fondée sur l’ablation, la preuve consommée par
`ReputationAdvisoryService` doit être OOS-only. Les seuils sont injectés explicitement via
`ReputationPolicy` et `ReputationPolicyThresholds` ; les valeurs de tests ne constituent pas des
seuils de production.

Les recommandations `HOLD / PROMOTE / DEMOTE / REDUCE_FREQUENCY` sont advisory-only. Elles ne
modifient jamais `AgentRegistry`, ne peuvent pas s’auto-appliquer (`auto_apply=False`) et ne
changent ni le Risk Engine, ni le broker, ni PAPER/SHADOW/LIVE. Les fonctions Core restent
protégées.

Chaque `AgentReputationAdvisoryReport` conserve la provenance des comparaisons et un fingerprint
SHA-256 déterministe afin de rendre la recommandation reconstruisible et auditable.

<!-- BATCH18A_STEP4_EVALUATION_END -->
