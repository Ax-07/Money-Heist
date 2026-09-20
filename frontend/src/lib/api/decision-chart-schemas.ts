import { z } from "zod";
import { backtestPeriodRoleSchema } from "./decision-intelligence-schemas";
import { candleSchema } from "./schemas";

const nullableNumber = z.number().nullable();

export const decisionIndicatorPointSchema = z.object({
  time: z.number(),
  observed_at: z.string().datetime({ offset: true }),
  snapshot_id: z.string(),
  candle_count: z.number().int().positive(),
  warmup_complete: z.boolean(),
  ema_fast: nullableNumber,
  ema_slow: nullableNumber,
  ema_spread_pct: nullableNumber,
  rsi_14: nullableNumber,
  macd_line: nullableNumber,
  macd_signal: nullableNumber,
  macd_histogram: nullableNumber,
  atr_14: nullableNumber,
  atr_pct: nullableNumber,
  atr_expansion_ratio: nullableNumber,
  adx_14: nullableNumber,
  bollinger_mid: nullableNumber,
  bollinger_upper: nullableNumber,
  bollinger_lower: nullableNumber,
  bollinger_width_pct: nullableNumber,
  bollinger_position: nullableNumber,
  volume_sma_20: nullableNumber,
  volume_ratio: nullableNumber,
  realized_volatility_20_pct: nullableNumber,
  prior_range_high_20: nullableNumber,
  prior_range_low_20: nullableNumber,
  distance_to_range_high_pct: nullableNumber,
  distance_to_range_low_pct: nullableNumber,
  regime: z.string(),
});

export const scannerThresholdsSchema = z.object({
  candidate_score: z.number().int().min(0).max(100),
  range_break_buffer_pct: z.number(),
  volume_expansion_ratio: z.number(),
  volatility_expansion_ratio: z.number(),
  trend_adx_threshold: z.number(),
  trend_ema_spread_pct: z.number(),
  momentum_high_rsi: z.number(),
  momentum_low_rsi: z.number(),
});

export const frontendDecisionChartSchema = z.object({
  schema_version: z.literal("money-heist.frontend-decision-chart.v1"),
  campaign_id: z.string(),
  role: backtestPeriodRoleSchema,
  symbol: z.string(),
  source_timeframe: z.string(),
  decision_timeframe: z.string(),
  feature_version: z.string(),
  projection_source: z.literal("RECONSTRUCTED_CANONICAL_FEATURE_ENGINE"),
  snapshot_identity_verified: z.boolean(),
  direct_scanner_features: z.array(z.string()),
  scanner_thresholds: scannerThresholdsSchema,
  candles: z.array(candleSchema),
  indicators: z.array(decisionIndicatorPointSchema),
});

export type FrontendDecisionChart = z.infer<typeof frontendDecisionChartSchema>;
export type DecisionIndicatorPoint = z.infer<typeof decisionIndicatorPointSchema>;
export type ScannerThresholds = z.infer<typeof scannerThresholdsSchema>;
