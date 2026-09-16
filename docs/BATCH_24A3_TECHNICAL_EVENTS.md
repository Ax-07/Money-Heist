# Batch 24A.3 — Technical Events

## Statut et autorité

Cette couche appartient exclusivement à l’Analytics Lab :

```text
READ-ONLY
OBSERVATION-ONLY
DETERMINISTIC
CAUSAL
REPLAY-SAFE
ZERO TRADING AUTHORITY
```

Un `TechnicalEventObservation` est une observation descriptive. Ce n’est ni un
`Scanner Trigger`, ni une `CandidateOpportunity`, ni une instruction LONG/SHORT,
ni une `TradeProposal`, ni une `RiskDecision`.

Le chemin reste séparé :

```text
Canonical closed candles
→ AnalyticsIndicatorEngine
→ AnalyticsIndicatorSnapshot T-1 / T
→ TechnicalEventEngine
→ TechnicalEventObservation
→ AnalyticsSnapshot / future Decision Intelligence
```

Le Scanner et le Feature Engine métier restent inchangés.

## Registry

Version : `money-heist.analytics-technical-events.v1`.

Le registry est fingerprinté et son identité complète est injectée dans
`AnalyticsComponentVersions.event_registry_version`. Modifier une définition matérielle
(seuil, condition, required indicator, direction descriptive, version de définition)
modifie donc l’identité Analytics. Cela ne modifie pas le `BacktestRun.run_id` ni le
business fingerprint historique.

Les seuils sont centralisés dans le registry : RSI 30/50/70, ADX 25, MFI 20/80 et
`volume_ratio_20 >= 1.5`.

## Sémantique causale

Le moteur est stateless :

```python
engine.detect(previous_indicator_snapshot, current_indicator_snapshot, analytics_run_id=...)
```

Il ne relit aucune candle, ne recalcule aucun indicateur, ne resample aucun timeframe et
ne consulte aucun Forward Outcome. Les deux snapshots doivent appartenir au même symbole
et au même timeframe.

- `current.candle_count == previous.candle_count` : aucun nouveau close du timeframe,
  donc aucun événement ;
- `current.candle_count == previous.candle_count + 1` : transition admissible ;
- saut supérieur à une candle : rejet, afin de ne pas transformer un changement observé
  sur plusieurs candles en faux crossover instantané.

Pour les événements standards de 24A.3 :

```text
event_at = current_indicator_snapshot.as_of
available_at = current_indicator_snapshot.as_of
```

L’intégration refuse tout `available_at > AnalyticsSnapshot.as_of`.

## Conventions d’égalité

Cross de deux séries à la hausse :

```text
previous A <= previous B
current  A >  current B
```

Cross à la baisse :

```text
previous A >= previous B
current  A <  current B
```

Une égalité répétée n’émet rien. L’événement est émis une seule fois lorsque la relation
quitte finalement l’égalité.

États de seuil :

```text
ENTER_BELOW: previous >= threshold and current < threshold
EXIT_BELOW:  previous <  threshold and current >= threshold
ENTER_ABOVE: previous <= threshold and current > threshold
EXIT_ABOVE:  previous >  threshold and current <= threshold
```

`VOLUME_SPIKE_20` utilise une entrée inclusive dans l’état spike :

```text
previous volume_ratio_20 < 1.5
current  volume_ratio_20 >= 1.5
```

Il n’est pas répété sur les candles suivantes tant que le ratio reste au-dessus du seuil.

## Catalogue 24A.3

| Event type | Famille | Direction descriptive | Required indicators | Règle |
|---|---|---|---|---|
| `EMA_9_CROSS_ABOVE_EMA_20` | trend | bullish | `ema_9`, `ema_20` | pair cross above |
| `EMA_9_CROSS_BELOW_EMA_20` | trend | bearish | `ema_9`, `ema_20` | pair cross below |
| `EMA_20_CROSS_ABOVE_EMA_50` | trend | bullish | `ema_20`, `ema_50` | pair cross above |
| `EMA_20_CROSS_BELOW_EMA_50` | trend | bearish | `ema_20`, `ema_50` | pair cross below |
| `EMA_50_CROSS_ABOVE_EMA_200` | trend | bullish | `ema_50`, `ema_200` | pair cross above |
| `EMA_50_CROSS_BELOW_EMA_200` | trend | bearish | `ema_50`, `ema_200` | pair cross below |
| `PRICE_CROSS_ABOVE_EMA_200` | trend | bullish | `ema_200_distance_pct` | cross above 0 |
| `PRICE_CROSS_BELOW_EMA_200` | trend | bearish | `ema_200_distance_pct` | cross below 0 |
| `RSI_14_ENTER_OVERSOLD` | momentum | bearish | `rsi_14` | enter below 30 |
| `RSI_14_EXIT_OVERSOLD` | momentum | bullish | `rsi_14` | exit below 30 |
| `RSI_14_CROSS_ABOVE_50` | momentum | bullish | `rsi_14` | cross above 50 |
| `RSI_14_CROSS_BELOW_50` | momentum | bearish | `rsi_14` | cross below 50 |
| `RSI_14_ENTER_OVERBOUGHT` | momentum | bullish | `rsi_14` | enter above 70 |
| `RSI_14_EXIT_OVERBOUGHT` | momentum | bearish | `rsi_14` | exit above 70 |
| `MACD_CROSS_ABOVE_SIGNAL` | momentum | bullish | MACD, signal | pair cross above |
| `MACD_CROSS_BELOW_SIGNAL` | momentum | bearish | MACD, signal | pair cross below |
| `MACD_HISTOGRAM_CROSS_ABOVE_ZERO` | momentum | bullish | MACD histogram | cross above 0 |
| `MACD_HISTOGRAM_CROSS_BELOW_ZERO` | momentum | bearish | MACD histogram | cross below 0 |
| `ROC_12_CROSS_ABOVE_ZERO` | momentum | bullish | `roc_12` | cross above 0 |
| `ROC_12_CROSS_BELOW_ZERO` | momentum | bearish | `roc_12` | cross below 0 |
| `ADX_14_CROSS_ABOVE_25` | trend_strength | neutral | `adx_14` | cross above 25 |
| `ADX_14_CROSS_BELOW_25` | trend_strength | neutral | `adx_14` | cross below 25 |
| `PLUS_DI_CROSS_ABOVE_MINUS_DI` | trend_strength | bullish | `plus_di_14`, `minus_di_14` | pair cross above |
| `PLUS_DI_CROSS_BELOW_MINUS_DI` | trend_strength | bearish | `plus_di_14`, `minus_di_14` | pair cross below |
| `PRICE_BREAK_ABOVE_BOLLINGER_UPPER` | volatility | bullish | `bb_position_20_2` | enter above 1 |
| `PRICE_RETURN_INSIDE_FROM_ABOVE_BOLLINGER` | volatility | bearish | `bb_position_20_2` | exit above 1 |
| `PRICE_BREAK_BELOW_BOLLINGER_LOWER` | volatility | bearish | `bb_position_20_2` | enter below 0 |
| `PRICE_RETURN_INSIDE_FROM_BELOW_BOLLINGER` | volatility | bullish | `bb_position_20_2` | exit below 0 |
| `PRICE_BREAK_ABOVE_DONCHIAN_20` | structure | bullish | `distance_to_high_20_pct` | cross above 0 |
| `PRICE_BREAK_BELOW_DONCHIAN_20` | structure | bearish | `distance_to_low_20_pct` | cross below 0 |
| `VOLUME_SPIKE_20` | volume | neutral | `volume_ratio_20` | enter `>= 1.5` |
| `MFI_14_ENTER_OVERSOLD` | volume | bearish | `mfi_14` | enter below 20 |
| `MFI_14_EXIT_OVERSOLD` | volume | bullish | `mfi_14` | exit below 20 |
| `MFI_14_ENTER_OVERBOUGHT` | volume | bullish | `mfi_14` | enter above 80 |
| `MFI_14_EXIT_OVERBOUGHT` | volume | bearish | `mfi_14` | exit above 80 |

Les directions sont descriptives, jamais des ordres. ADX et volume sont volontairement
`neutral` car ils décrivent force/activité sans imposer de direction de prix.

## Réutilisation stricte des Indicators 24A.2

Le moteur n’utilise pas la candle brute :

- Price/EMA200 : `ema_200_distance_pct` ;
- Bollinger : `bb_position_20_2` ;
- Donchian : `distance_to_high_20_pct` / `distance_to_low_20_pct` ;
- volume spike : `volume_ratio_20`.

Cette règle garantit que les sémantiques 24A.2 restent la source unique. En particulier,
ADX et `volume_ratio_20` suivent les définitions Analytics, pas celles du Feature Engine.

## Warmup

Un événement n’est évalué que si tous ses required indicators sont simultanément :

```text
available == True
warmup_complete == True
value is not None
```

`None`, `NaN` et zéro ne sont jamais interchangeables.

## Evidence et identité

Chaque observation contient les valeurs T-1/T effectivement utilisées, les paramètres du
registry et la condition. `event_id` et `event_fingerprint` sont déterministes.

L’ID dépend notamment de :

```text
analytics_run_id
symbol
timeframe
event_type
event_at
definition_version
source indicator snapshot fingerprint
```

Le fingerprint ajoute famille, direction, disponibilité, evidence, cursor fingerprint et
source snapshot identity.

L’`AnalyticsIndicatorSnapshot` 24A.2 n’expose pas de champ `snapshot_id`; 24A.3 dérive donc
un `source_indicator_snapshot_id` UUID5 stable de son `snapshot_fingerprint`, sans modifier
le contrat 24A.2.

## Technical Event != Scanner Trigger

| Analytics event | Scanner trigger proche | Même objet ? |
|---|---|---|
| `VOLUME_SPIKE_20` | `VOLUME_EXPANSION` | Non |
| `ADX_14_CROSS_ABOVE_25` | `TREND_STRENGTH` | Non |
| `PRICE_BREAK_ABOVE_DONCHIAN_20` | `RANGE_BREAK` | Non |
| `RSI_14_ENTER_OVERBOUGHT` | `MOMENTUM_EXTREME` | Non |

Les seuils, timings, sémantiques et finalités peuvent diverger. Le Scanner reste dans son
pipeline métier et n’importe pas `app.analytics.events`.

## Audit de `Ax-07/btc_analytics_v1`

Référence auditée : commit `07e9af22d8f5cc509d9a8dd50a2e7451249295c1`, registry `p4.v1`.

Éléments conservés conceptuellement :

- crosses EMA 9/20, 20/50, 50/200 ;
- Price/EMA200 ;
- RSI 30/50/70 ;
- MACD line/signal et histogram zero ;
- ROC zero ;
- ADX 25 ;
- DMI ;
- Bollinger breaks ;
- Donchian ;
- volume ratio 1.5 ;
- MFI 20/80.

Divergences volontaires :

1. Money Heist ne consomme aucune candle brute dans l’Event Engine.
2. Bollinger ajoute les événements de retour à l’intérieur du canal.
3. Le Donchian de la référence teste `high > previous upper` / `low < previous lower` à
   chaque candle ; Money Heist utilise un changement d’état de clôture via les métriques
   Donchian 24A.2 afin d’éviter les répétitions et de respecter la source unique Indicators.
4. Le volume spike est explicitement une entrée d’état `<1.5 → >=1.5`.
5. Aucune hypothèse DB/PostgreSQL/Binance/BTC/API n’est portée.

Il s’agit d’une parité conceptuelle partielle, pas d’une promesse de parité bit-à-bit.

## Hors périmètre

24A.3 n’implémente pas : ZigZag/pivots, structure causale enrichie, patterns, contexts,
sequences, Forward Outcomes, calibration/tuning de seuils, intégration au Scanner ou au
pipeline de trading.
