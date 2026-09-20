# Money Heist — Shadow Attention Semantic v1

**Statut :** CANDIDATE figée / SHADOW observation-only  
**Autorité :** aucune autorité Scanner, Agents, Risk, PAPER ou LIVE  
**Source :** Shadow Attention v0, elle-même issue des jointures Analytics exactes 24A/24B/24C

## 1. But

Semantic v1 réduit la densité de Shadow Attention v0 sans introduire de score de
trading, de direction ou de setup prédéfini. La candidate est figée après la
campagne exploratoire 3 mois et doit désormais être testée telle quelle sur une
période fraîche.

Elle ne remplace pas Scanner v1.

## 2. Policy figée

Une évaluation déjà couverte par Analytics exact peut produire
`shadow_wake=true` uniquement si au moins une clause same-bar est vraie :

1. au moins deux familles de `TECHNICAL_EVENT` distinctes sont disponibles à T ;
2. au moins un `TECHNICAL_EVENT` et une confirmation ZigZag sont disponibles à T ;
3. une transition de pattern est `CONFIRMED`, `FAILED` ou `INVALIDATED` à T.

Les clauses sont combinées par OR. Plusieurs clauses au même T restent un seul
wake.

## 3. Exclusions contractuelles

Semantic v1 n'utilise pas :

- la direction `BULLISH` / `BEARISH` comme condition de wake ;
- `PatternStatus.FORMING` ;
- les états/changements de structure comme déclencheur ;
- le score ou le threshold Scanner ;
- les Forward Outcomes ;
- le PnL, les trades ou les décisions MOCK ;
- un cooldown ou un état d'épisode persistant ;
- une interprétation LONG/SHORT ou un type de setup.

Les informations de direction et de contexte peuvent rester dans les raisons
brutes à des fins d'audit, mais elles ne participent pas au booléen de wake.

## 4. Causalité et fail-closed

Semantic v1 consomme uniquement un `ShadowAttentionReport` v0 déjà construit par
jointure causale exacte. Une attribution Analytics `UNAVAILABLE` reste
`UNAVAILABLE` et ne peut pas être transformée en wake.

Aucun nearest-neighbor temporel n'est ajouté.

## 5. Pourquoi cette forme

Les audits exploratoires ont montré :

- un biais Scanner v1 important vers `RANGE_BREAK` ;
- une densité Analytics brute trop élevée pour réveiller l'IA sur tout événement ;
- des cooldowns globaux qui détruisent rapidement la couverture ;
- des épisodes persistants qui atteignent environ 95–99 % de duty cycle et sont
  donc trop peu discriminants ;
- des impulsions same-bar sémantiques capables de ramener la charge dans une zone
  nettement plus basse sans maintenir artificiellement l'attention ouverte.

La candidate retenue correspond à la variante exploratoire
`SEMANTIC_V1_MATURE` :

```text
>= 2 familles Technical distinctes
OR Technical + ZigZag confirmé
OR pattern CONFIRMED / FAILED / INVALIDATED
```

Les chiffres de la campagne 3 mois servent uniquement à expliquer la conception.
Ils ne constituent pas une validation de la policy.

## 6. Protocole expérimental à partir de maintenant

La policy est figée. La campagne actuelle ne doit plus servir à la modifier.

```text
candidate Semantic v1 figée
→ nouvelle période fraîche
→ VALIDATION de charge / couverture / qualité causale
→ policy inchangée
→ nouvel OOS intact
→ comparaison PAPER / SHADOW
→ batch comportemental séparé éventuel
```

Toute modification de clause après consultation de la nouvelle VALIDATION crée
une nouvelle policy/version et nécessite une nouvelle validation fraîche.

## 7. Exports

Pour chaque rôle :

```text
shadow-attention-semantic-v1-design.json
shadow-attention-semantic-v1-validation.json
shadow-attention-semantic-v1-oos.json
```

Chaque record conserve :

- l'identité de l'observation v0 source ;
- l'évaluation Scanner ;
- les raisons Analytics causales ;
- les clauses Semantic v1 activées ;
- `BOTH / SCANNER_ONLY / SHADOW_ONLY / NEITHER / UNAVAILABLE`.

Ces sidecars sont de recherche et d'audit. Ils ne déclenchent aucun agent.
