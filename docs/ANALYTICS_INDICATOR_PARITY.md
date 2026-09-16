# Money Heist — Analytics Indicator Parity Catalogue

**Batch:** 24A.2 — Rich Indicators & Parity Catalogue
**Money Heist baseline:** `0c4549663bf43418ff2d337c63343112f314dceb`
**btc_analytics_v1 audited commit:** `07e9af22d8f5cc509d9a8dd50a2e7451249295c1`
**btc_analytics_v1 registry actually audited:** `p4.v1`

## 1. Purpose

This catalogue records semantic relationships between the production Money Heist Feature Engine, the observation-only Analytics Lab implementation, and `btc_analytics_v1`. A shared indicator name is not treated as proof of identical semantics.

Statuses:

- `SAME_SEMANTICS`: verified formulas, initialization and current-candle policy match.
- `COMPATIBLE_SEMANTICS`: values are intentionally equivalent for the compared field, but naming/purpose differs.
- `INTENTIONAL_DIVERGENCE`: a verified, documented semantic difference is preserved.
- `ANALYTICS_ONLY`: no production FeatureSnapshot equivalent exists.
- `NOT_COMPARABLE`: there is no safe semantic equivalence claim.

The machine-readable source of the statuses is `app/analytics/indicators/parity.py`.

## 2. Verified catalogue

| Indicator | Feature Engine | Analytics 24A.2 | btc_analytics_v1 | Status | Verified semantics / note |
|---|---:|---:|---:|---|---|
| EMA 20/50/100/200 | yes | yes | yes | SAME_SEMANTICS | `alpha=2/(N+1)`, first EMA value seeded by the first N-candle SMA. |
| RSI 14 | yes | yes | yes | SAME_SEMANTICS | Wilder smoothing over close transitions; initial average gain/loss uses 14 transitions; flat seed returns 50. |
| MACD 12/26/9 | yes | yes | yes | SAME_SEMANTICS | SMA-seeded EMA12/EMA26; signal is a SMA-seeded EMA9 of the MACD line. |
| ATR 14 | yes | yes | yes | SAME_SEMANTICS | First TR is first candle `high-low`; later TR uses previous close; Wilder smoothing. |
| Bollinger 20/2 | yes | yes | yes | SAME_SEMANTICS | Population variance / standard deviation (`ddof=0`). |
| ADX 14 | yes | yes | yes | INTENTIONAL_DIVERGENCE | Production seeds TR with candle 1 and DM with zeros. Analytics/btc_analytics_v1 initialize previous H/L/C first, then begin TR/DM on the first transition. Feature Engine is unchanged. |
| +DI / -DI 14 | not exposed | yes | yes | ANALYTICS_ONLY | Uses the Analytics first-transition DMI initialization. |
| Volume SMA 20 | yes | yes | yes | INTENTIONAL_DIVERGENCE | Production uses the previous 20 volumes (current excluded). Analytics/btc_analytics_v1 use the current 20-candle window (current included). |
| Volume Ratio 20 | yes | yes | yes | INTENTIONAL_DIVERGENCE | Production: `current / SMA(previous 20)`. Analytics: `current / SMA(current 20)`. |
| Previous high/low 20 | yes (`prior_range`) | yes | yes | COMPATIBLE_SEMANTICS | Previous 20 highs/lows; current candle excluded. |
| Donchian upper/lower 20 | equivalent prior range | yes | yes | COMPATIBLE_SEMANTICS | Same numeric previous-20 extrema policy; Analytics exposes Donchian naming separately. |
| Donchian position 20 | no direct output | yes | yes | ANALYTICS_ONLY | `(close-lower)/(upper-lower)` over previous-20 channel. |
| SMA 20/50/100/200 | helper only / not all exposed | yes | yes | COMPATIBLE_SEMANTICS | Standard current-inclusive SMA; production contract does not expose the same complete family. |
| Stochastic RSI 14/14/3/3 | no | yes | yes | ANALYTICS_ONLY | Wilder RSI -> rolling RSI min/max -> SMA3 K -> SMA3 D. |
| ROC 12 | no | yes | yes | ANALYTICS_ONLY | `(close / close[-12] - 1) * 100`. |
| OBV | no | yes | yes | ANALYTICS_ONLY | Starts at zero; adds/subtracts later candle volume by close direction. |
| MFI 14 | no | yes | yes | ANALYTICS_ONLY | Typical-price money flow over 14 transitions. |
| CMF 20 | no | yes | yes | ANALYTICS_ONLY | 20-candle money-flow-volume / volume sum, current included. |
| Rolling VWAP 20 | no | yes | yes | ANALYTICS_ONLY | Typical price * base volume / base volume over 20 candles, current included. |
| EMA distance / slope | no equivalent output | yes | yes | ANALYTICS_ONLY | Distance `(close/EMA-1)*100`; slope is one-candle EMA percentage change. |

## 3. ADX decision

24A.2 deliberately follows the `btc_analytics_v1` DMI/ADX initialization:

1. candle 1 only initializes previous high/low/close;
2. TR, +DM and -DM begin on the transition to candle 2;
3. the first smoothed DMI state requires 14 transitions;
4. ADX uses a 14-value DX seed and then Wilder recurrence.

The production `app/market/features/indicators.py` implementation is **not modified**. The difference is an observation-space semantic choice, not a production bug fix.

## 4. Volume Ratio decision

24A.2 follows `btc_analytics_v1`:

```text
volume_sma_20 = SMA(latest 20 volumes, current included)
volume_ratio_20 = current volume / volume_sma_20
```

The production Feature Engine remains:

```text
volume_sma_20 = SMA(previous 20 volumes, current excluded)
volume_ratio_20 = current volume / production volume_sma_20
```

Tests intentionally demonstrate that these values differ on a non-constant volume series.

## 5. Donchian / prior-range decision

Analytics Donchian 20 and rolling high/low 20 inspect the **previous** 20 fully closed candles before the current candle is inserted into the extrema state. This matches `btc_analytics_v1` and is numerically compatible with Money Heist's production `prior_range_high_20` / `prior_range_low_20` policy.

## 6. Numeric determinism

Indicator calculations use Python `float` internally, matching the existing deterministic indicator style. Snapshot fingerprints use Money Heist canonical hashing: floats are canonicalized through `Decimal(str(value))`, mappings are sorted, datetimes are normalized to UTC, and non-finite values are rejected. No silent zero-fill is used for unavailable indicators.
