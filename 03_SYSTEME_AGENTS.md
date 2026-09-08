# Money Heist — Système d’Agents

**Document :** Architecture fonctionnelle des agents  
**Version :** 0.1  
**Statut :** Spécification initiale  
**Références :** `01_PROJECT_MASTER.md`, `02_ARCHITECTURE.md`

---

## 1. Objectif

Ce document définit le comportement attendu de la crew Money Heist : rôles, orchestration, indépendance, états, recrutement, coûts et règles d’autorité.

Les prompts définitifs seront versionnés dans le code et pourront évoluer sans modifier les règles constitutionnelles.

---

## 2. Principes

1. Les agents sont des **analystes**, pas des détenteurs de permissions.
2. Une opinion IA n’est jamais une autorisation d’exécution.
3. Le premier tour des spécialistes doit être indépendant.
4. Palermo est chargé d’attaquer la thèse dominante.
5. The Professor peut choisir les spécialistes, mais pas supprimer les garde-fous obligatoires.
6. Lisbon mesure l’économie du compute, pas le risque de trading.
7. Tout nouvel agent commence sans influence LIVE.
8. Les sorties critiques utilisent des schémas stricts.

---

## 3. Taxonomie des agents

### 3.1 Core Crew

Fonctions obligatoires :

| Fonction | Implémentation initiale |
|---|---|
| Orchestration | The Professor |
| Contradiction | Palermo |
| Economie IA | Lisbon |
| Autorisation risque | Risk Engine déterministe |
| Audit | Logger / Storage |

La fonction est obligatoire même si l’agent ou le nom évolue plus tard.

### 3.2 Spécialistes initiaux

| Agent | Domaine |
|---|---|
| Berlin | tendance / régime |
| Tokyo | momentum |
| Nairobi | price action / structure / liquidité |
| Rio | dérivés / sentiment |
| Denver | quant / statistiques |

---

## 4. The Professor

### Mission

Transformer une opportunité détectée en une décision structurée de qualité, en utilisant le minimum de compute nécessaire.

### Entrées minimales

- `CandidateOpportunity` ;
- `MarketContext` ;
- budget IA restant ;
- état du portefeuille non sensible ;
- liste d’agents disponibles et leurs états ;
- contraintes de niveau d’analyse.

### Première décision

The Professor choisit :

```text
NO_ANALYSIS
MINI_CREW
FULL_CREW
```

Puis sélectionne les spécialités utiles.

### Contraintes

The Professor ne peut pas :
- modifier un profil de risque ;
- changer un système SHADOW en LIVE ;
- supprimer Palermo du chemin lorsque Palermo est obligatoire ;
- dépasser un plafond IA ;
- appeler des outils non autorisés ;
- accéder aux secrets.

---

## 5. Berlin

### Mission

Déterminer :
- régime dominant ;
- direction de tendance ;
- maturité de la tendance ;
- cohérence multi-timeframes ;
- signaux d’épuisement.

### Sortie attendue

```json
{
  "agent": "berlin",
  "stance": "LONG|SHORT|NEUTRAL",
  "confidence": 0.0,
  "regime": "string",
  "evidence": [],
  "risks": [],
  "invalidation": []
}
```

---

## 6. Tokyo

### Mission

Evaluer la qualité du momentum.

Analyse typique :
- accélération ;
- volume ;
- breakout ;
- divergences ;
- continuation ;
- sur-extension.

Tokyo ne doit pas conclure qu’un breakout est valide uniquement parce que le prix a dépassé un niveau.

---

## 7. Nairobi

### Mission

Evaluer la structure de marché et la liquidité.

Analyse typique :
- structure HH/HL ou LH/LL ;
- zones de support/résistance ;
- retests ;
- faux breakouts ;
- clusters de liquidité ;
- distance entre entrée potentielle et invalidation.

---

## 8. Rio

### Mission

Evaluer les données dérivées lorsque celles-ci sont disponibles et fiables.

Analyse typique :
- funding ;
- open interest ;
- liquidations ;
- déséquilibres éventuels ;
- risque de squeeze.

Si ces données ne sont pas disponibles dans la V1, Rio reste `DISABLED` ou `SHADOW` plutôt que de produire des informations inventées.

---

## 9. Denver

### Mission

Apporter une perspective statistique fondée sur les données internes.

Denver ne doit pas inventer une probabilité historique.

Pour formuler :
> “ce setup a eu 61 % de réussite”

il doit disposer d’une source interne calculée et identifiable.

Sinon il répond :
- données insuffisantes ;
- échantillon insuffisant ;
- aucune estimation robuste disponible.

---

## 10. Palermo

### Mission

Chercher activement pourquoi la proposition pourrait être mauvaise.

Palermo reçoit :
- le contexte de marché ;
- les conclusions des spécialistes ;
- la thèse provisoire du Professor.

Palermo cherche :
- biais de confirmation ;
- signaux contradictoires ;
- risques ignorés ;
- mauvaise asymétrie ;
- faux breakout ;
- corrélation cachée ;
- données obsolètes ;
- hypothèse non vérifiée.

### Sortie conceptuelle

```json
{
  "verdict": "CLEAR|CAUTION|REJECT",
  "severity": 0.0,
  "critical_objections": [],
  "missing_checks": [],
  "conditions_to_continue": []
}
```

Un `REJECT` de Palermo n’est pas nécessairement un veto constitutionnel à lui seul ; le Risk Engine reste l’autorité finale de sécurité. En revanche, la politique d’orchestration peut exiger que le Professor justifie explicitement toute décision qui va contre Palermo.

---

## 11. Lisbon

### Mission

Mesurer si l’organisation utilise correctement son budget IA.

Lisbon reçoit :
- coûts ;
- fréquences d’appel ;
- décisions influencées ;
- métriques de performance ;
- états des agents ;
- comparaisons SHADOW.

Lisbon peut recommander :
- ACTIVE ;
- ON_DEMAND ;
- SHADOW ;
- PROBATION ;
- DISABLED.

Lisbon ne peut pas :
- changer directement le statut d’un agent Core ;
- changer les limites de risque ;
- promouvoir un agent en LIVE sans processus de validation ;
- augmenter le budget maximal.

---

## 12. Cycle de décision

```text
1. Opportunité détectée
2. Compute Gate
3. Professor sélectionne les spécialistes
4. Tour 1 indépendant
5. Professor agrège
6. Palermo attaque la thèse
7. Professor produit TradeProposal
8. Validation schéma
9. Risk Engine
10. Exécution ou rejet
```

Un second tour de spécialistes est possible uniquement s’il apporte une valeur informationnelle estimée suffisante.

---

## 13. Indépendance et contamination

Premier tour :
- chaque spécialiste reçoit le même snapshot de base ;
- chaque spécialiste reçoit une mission spécifique ;
- aucun spécialiste ne voit les réponses des autres.

Second tour éventuel :
- peut contenir des objections ciblées ;
- doit être explicitement marqué comme non indépendant.

Les métriques distinguent :
- `independent_round` ;
- `debate_round`.

---

## 14. Score de confiance

La `confidence` est une mesure interne, pas une probabilité garantie.

Exigences :
- bornée entre 0 et 1 ;
- accompagnée d’éléments de preuve ;
- analysée ensuite pour calibration.

Le système doit pouvoir mesurer :

```text
Parmi les décisions à confiance ~0.70,
quelle proportion s’est réellement comportée comme prévu ?
```

---

## 15. Désaccords

Le désaccord est un signal utile.

Exemple :

```text
Berlin    LONG 0.82
Tokyo     LONG 0.71
Nairobi   NEUTRAL 0.65
Rio       SHORT 0.68
```

The Professor doit conserver :
- les opinions individuelles ;
- la dispersion ;
- les arguments contradictoires.

Le système ne réduit pas les analyses à un simple vote majoritaire.

---

## 16. Etats d’agents

Transitions autorisées conceptuellement :

```text
ACTIVE ↔ ON_DEMAND
   ↓         ↓
 SHADOW ← PROBATION
   ↓
DISABLED
```

Toute transition est :
- journalisée ;
- justifiée ;
- réversible.

Les agents Core ne peuvent pas être éliminés automatiquement.

---

## 17. Réputation

La réputation doit être multidimensionnelle.

Exemples :
- performance par régime ;
- performance par symbole ;
- calibration ;
- valeur marginale ;
- coût ;
- réduction de drawdown ;
- taux de contradiction utile.

Un seul score global peut être affiché, mais les décisions internes doivent conserver les dimensions sous-jacentes.

---

## 18. Recrutement

### 18.1 Déclencheurs

Un recrutement peut être proposé lorsque :
- un type d’erreur se répète ;
- une source de données n’est exploitée par aucun agent ;
- un nouveau régime apparaît ;
- un agent existant est trop généraliste ;
- une hypothèse testable justifie une nouvelle compétence.

### 18.2 Fiche candidat

```json
{
  "name": "Marseille",
  "role": "Liquidation Specialist",
  "problem": "string",
  "hypothesis": "string",
  "required_data": [],
  "allowed_tools": [],
  "model_class": "configurable",
  "budget_limit": 0.0,
  "success_metrics": [],
  "evaluation_window": "string"
}
```

### 18.3 Cycle

```text
PROPOSED
→ VALIDATED
→ SHADOW
→ PROBATION
→ ACTIVE/ON_DEMAND
```

ou :

```text
SHADOW
→ REJECTED
```

---

## 19. Agents temporaires

Un `TaskForceAgent` doit :
- avoir une date d’expiration ;
- avoir une mission étroite ;
- disposer d’un budget ;
- disposer d’une liste d’outils en allowlist ;
- ne jamais obtenir automatiquement de permission LIVE.

---

## 20. Limites de population

Les valeurs exactes seront configurées plus tard, mais l’application doit prévoir :
- `max_active_specialists` ;
- `max_shadow_candidates` ;
- `max_recruitments_per_period` ;
- `max_compute_per_candidate`.

L’objectif est d’empêcher la prolifération incontrôlée des agents.

---

## 21. Versionnage des prompts

Chaque exécution doit enregistrer :
- `agent_name` ;
- `prompt_version` ;
- `model_id` ;
- paramètres importants du modèle ;
- identifiant de schéma.

Une modification de prompt doit pouvoir être comparée en SHADOW avant promotion.

---

## 22. Fail-safe agentique

En cas de :
- sortie vide ;
- JSON invalide ;
- contradiction interne ;
- tool call non autorisé ;
- timeout ;
- coût estimé excessif ;

l’analyse est invalide.

Aucune logique du type “interpréter au mieux et trader quand même” n’est autorisée dans le chemin LIVE.

---

## 23. Critères d’acceptation

Le système agentique est correctement implémenté si :
- les spécialistes du premier tour sont indépendants ;
- The Professor peut sélectionner dynamiquement les experts ;
- Palermo est injecté au bon niveau ;
- le coût de chaque agent est enregistré ;
- un agent SHADOW n’influence jamais le LIVE ;
- un nouvel agent ne possède aucune autorité par défaut ;
- les sorties critiques sont validées par schéma ;
- les prompts sont versionnés.


## 24. Addendum Batch 17a — Rio / Denver avancés

### Rio

Rio est enregistré `ON_DEMAND` mais sa disponibilité runtime est conditionnée à un `RioContext`
fiable et non stale. Le contexte peut contenir funding, open interest, variation d’open interest,
liquidations et ratio long/short. L’absence de ces données ne doit jamais être remplacée par une
inférence à partir d’OHLCV. En Batch 17a, aucune source dérivés réelle n’est activée : Rio reste donc
non sélectionnable dans le chemin historique normal.

### Denver

Denver est enregistré `ON_DEMAND` et reçoit uniquement un `DenverContext` calculé hors LLM. Le
contexte référence `stats_id`, version de définition du setup, `as_of`, runs/datasets sources, taille
d’échantillon, échantillon OOS et métriques historiques disponibles. Denver interprète ces données ;
il ne les calcule pas lui-même et ne peut pas inventer une probabilité manquante.

La définition de setup V1 utilise : système, symbole, timeframe, versions Scanner/Feature, régime et
triggers Scanner. Les statistiques ne sont accessibles que si le contexte est utilisable et antérieur
ou égal au snapshot marché courant.

Les sorties Rio/Denver conservent le contrat commun : stance, confidence, evidence grounded, risks,
invalidation et data gaps, plus les champs de spécialité. Leur `stance` n’est jamais une autorisation
de trading.
