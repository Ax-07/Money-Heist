# Batch 24A.4 — Causal Structure & ZigZag

## Statut
Implémentation proposée sur baseline `e7d98d9dd0db1166dda9e62f2a2bd5461e98742d`.

## Sources structurelles

Deux sources restent explicitement distinctes :

- `MONEY_HEIST_STRUCTURE` : projection read-only du `MarketStructureContextV1`
  existant, sans réimplémentation.
- `CAUSAL_ZIGZAG` : pivots ATR-confirmés de l'Analytics Lab.

Le ZigZag ne remplace jamais `app/market/structure.py`.

## Définition ZigZag V1

- version : `money-heist.analytics-causal-zigzag.v1`
- source ATR : Analytics Indicators `atr_14`
- période ATR : 14
- multiplicateur : 2.0
- seuil : `reversal >= 2.0 * ATR_at_candidate`
- ATR et seuil verrouillés au candidat
- candles closes uniquement
- timestamp géométrique Money Heist : `pivot_at = candle.close_time`
- timestamp de connaissance : `confirmed_at = confirmation_candle.close_time`
- exposition : uniquement si `confirmed_at <= as_of`
- ordering : `confirmed_at`, puis `pivot_at`, puis `kind`, puis ID

## Initialisation

Dès le premier ATR disponible, le moteur initialise simultanément un candidat HIGH et
un candidat LOW sur cette bougie. Il reste sans direction tant qu'une seule direction
n'est pas confirmable de manière non ambiguë.

Si une même bougie OHLC permet à la fois le retournement haussier et baissier, aucune
première direction n'est créée.

## Ambiguïté OHLC

Aucun ordre intrabar n'est inventé.

Si une nouvelle bougie crée un extrême plus haut/bas, ce nouvel extrême remplace le
candidat et ne peut pas être confirmé sur cette même bougie. La confirmation attend
donc au minimum une bougie close ultérieure.

## Amplitudes

La parité avec `btc_analytics_v1` est conservée :

```text
delta = current_pivot.price - previous_pivot.price
amplitude_pct = 100 * delta / previous_pivot.price
amplitude_atr = delta / previous_pivot.atr_at_pivot
bars_from_previous = current_index - previous_index
```

Les amplitudes sont donc signées.

## Exemple causal

```text
T1      T2      T3      T4      T5      T6
95      99      103     101      98      96
                ↑
             pivot_at

ATR(T3)=3
threshold=6

T4 reversal=2 → not confirmed
T5 reversal=5 → not confirmed
T6 reversal=7 → confirmed

pivot_at=T3
confirmed_at=T6
```

Le pivot peut être dessiné à T3 dans une UI future, mais n'est disponible à l'analyse
qu'à T6.

## UI future

Un marqueur devra distinguer :
- position géométrique : `pivot_at`
- disponibilité causale : `confirmed_at`

Aucun overlay UI n'est implémenté dans 24A.4.
