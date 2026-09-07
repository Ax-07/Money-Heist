# Money Heist — Batch 07b — Spécialistes V1

## Base d'intégration

- Dépôt : `Ax-07/Money-Heist`
- Branche : `main`
- Commit de référence : `6ab77a32b0b47b5691a184333bed3114c9ef3eed`
- Batch précédent : `07a — Core Agents`

## Ajouts

### Berlin — tendance / régime

- analyse indépendante de premier tour ;
- contrat `BerlinAnalysis` strict ;
- classification du régime, maturité de tendance et alignement multi-timeframes ;
- preuves obligatoirement rattachées à des champs réellement fournis.

### Tokyo — momentum

- analyse indépendante de premier tour ;
- contrat `TokyoAnalysis` strict ;
- momentum, qualité du momentum et qualité de breakout ;
- absence de données représentée explicitement par `UNKNOWN` / `data_gaps`.

### Nairobi — price action / structure / liquidité

- analyse indépendante de premier tour ;
- contrat `NairobiAnalysis` strict ;
- structure de marché, état de liquidité et état de breakout ;
- aucune donnée order-book/liquidation n'est supposée lorsqu'elle est absente.

### Infrastructure réutilisée

- `CoreAgent` et protocole `StructuredGateway` du Batch 07a ;
- `AIGatewayRequest` / `AIGatewayResult` du Batch 06 ;
- registre d'agents ;
- prompts versionnés `v1` ;
- route modèle existante `core_reasoning` ;
- budget IA existant, sans chemin alternatif.

## Garde-fous ajoutés

- premier tour marqué `INDEPENDENT_1` ;
- rejet déterministe d'un payload contenant des conclusions d'autres agents ;
- validation déterministe des `source_key` de chaque preuve contre l'entrée réellement fournie ;
- sorties Pydantic `extra="forbid"` ;
- spécialistes limités à `LONG`, `SHORT` ou `NEUTRAL` : ils ne produisent pas de décision `NO_TRADE` ni d'ordre ;
- `allowed_tools=()` pour Berlin, Tokyo et Nairobi ;
- spécialistes marqués `core=False` ;
- `CORE_AGENT_REGISTRY` inchangé ; ajout de `SPECIALIST_AGENT_REGISTRY` et `V1_AGENT_REGISTRY`.

## Tests ajoutés

`tests/agents/test_specialists_v1.py` couvre notamment :

- Berlin / Tokyo / Nairobi via le gateway structuré ;
- version de prompt et modèle de sortie attendus ;
- indépendance du premier tour ;
- rejet de contamination inter-agents avant appel IA ;
- rejet d'une preuve non rattachée aux données fournies ;
- comportement explicite en cas de données manquantes ;
- rejet des champs de sortie supplémentaires ;
- impossibilité pour un spécialiste d'émettre `NO_TRADE` ;
- registre combiné V1 et absence d'outils privilégiés.

## Validation effectuée sur le lot

Dans un miroir local des modules agents du commit de référence :

```text
15 passed
```

Cela inclut les 5 tests agents existants du Batch 07a et les 10 cas de test supplémentaires du Batch 07b (paramétrage inclus).

La suite complète du dépôt doit être confirmée après extraction avec :

```powershell
uv sync
uv run pytest -q
```

Avec une base locale à 125 tests et sans autre changement, le total attendu est de 135 tests.

## Hors périmètre respecté

- Rio non implémenté ;
- Denver non implémenté ;
- aucune modification du broker ;
- aucune modification de l'exchange ;
- aucune modification du Risk Engine ;
- aucune modification du plafond ou ledger IA ;
- aucune nouvelle dépendance ;
- aucun secret.
