import { z } from "zod";
import { backtestPeriodRoleSchema, frontendFunnelStageSchema } from "./decision-intelligence-schemas";

const iso = z.string().datetime({ offset: true });
const jsonPrimitiveSchema = z.union([z.string(), z.number(), z.boolean(), z.null()]);
type JsonValue = z.infer<typeof jsonPrimitiveSchema> | JsonValue[] | { [key: string]: JsonValue };
const jsonValueSchema: z.ZodType<JsonValue> = z.lazy(() =>
  z.union([jsonPrimitiveSchema, z.array(jsonValueSchema), z.record(jsonValueSchema)]),
);

const analyticsRefSchema = z.object({
  status: z.string(),
  analytics_run_id: z.string(),
  analytics_link_id: z.string().nullable().optional(),
  analytics_link_fingerprint: z.string().nullable().optional(),
  analytics_link_policy_version: z.string().nullable().optional(),
  opportunity_analytics_link_id: z.string().nullable().optional(),
  decision_intelligence_record_id: z.string().nullable().optional(),
  analytics_snapshot_id: z.string().nullable().optional(),
  analytics_snapshot_fingerprint: z.string().nullable().optional(),
  analytics_as_of: iso.nullable().optional(),
  source_cursor_fingerprint: z.string().nullable().optional(),
  analytics_snapshot_source_cursor_fingerprint: z.string().nullable().optional(),
  diagnostics: z.array(z.string()).default([]),
});

const scannerOverlaySchema = z.object({
  record_id: z.string(),
  scanner_evaluation_id: z.string(),
  observed_at: iso,
  symbol: z.string(),
  decision_timeframe: z.string(),
  classification: z.string(),
  score: z.number().int().min(0).max(100),
  priority_score: z.number().int().min(0).max(100),
  candidate_threshold: z.number().int().min(0).max(100),
  score_margin: z.number().int().min(-100).max(100),
  triggers: z.array(z.string()),
  market_regime: z.string().nullable().optional(),
  candidate_opportunity_id: z.string().nullable().optional(),
  analytics: analyticsRefSchema,
});

const technicalEventOverlaySchema = z.object({
  event_id: z.string(),
  event_type: z.string(),
  family: z.string(),
  direction: z.string(),
  symbol: z.string(),
  timeframe: z.string(),
  event_at: iso,
  available_at: iso,
  event_fingerprint: z.string(),
  evidence: jsonValueSchema,
});

const swingPointOverlaySchema = z.object({
  kind: z.enum(["HIGH", "LOW"]),
  price: z.string(),
  close_time: iso,
});

const structureTimeframeOverlaySchema = z.object({
  timeframe: z.string(),
  observed_at: iso,
  close: z.string(),
  prior_range_high: z.string().nullable().optional(),
  prior_range_low: z.string().nullable().optional(),
  range_location: z.string(),
  breakout_state: z.string(),
  swing_structure: z.string(),
  previous_swing_high: swingPointOverlaySchema.nullable().optional(),
  latest_swing_high: swingPointOverlaySchema.nullable().optional(),
  previous_swing_low: swingPointOverlaySchema.nullable().optional(),
  latest_swing_low: swingPointOverlaySchema.nullable().optional(),
  missing_fields: z.array(z.string()).default([]),
});

const structureOverlaySchema = z.object({
  structure_id: z.string(),
  symbol: z.string(),
  as_of: iso,
  source_cursor_fingerprint: z.string(),
  timeframes: z.array(structureTimeframeOverlaySchema),
});

const zigZagPivotOverlaySchema = z.object({
  pivot_id: z.string(),
  kind: z.enum(["HIGH", "LOW"]),
  symbol: z.string(),
  timeframe: z.string(),
  pivot_at: iso,
  confirmed_at: iso,
  price: z.string(),
  atr_at_pivot: z.string(),
  reversal_multiple: z.string(),
  reversal_threshold: z.string(),
  amplitude_pct: z.string().nullable().optional(),
  amplitude_atr: z.string().nullable().optional(),
  bars_from_previous: z.number().int().positive().nullable().optional(),
  pivot_fingerprint: z.string(),
});

const patternPointOverlaySchema = z.object({
  role: z.string(),
  pivot_id: z.string(),
  kind: z.enum(["HIGH", "LOW"]),
  price: z.string(),
  pivot_at: iso,
  confirmed_at: iso,
});

const patternSegmentOverlaySchema = z.object({
  role: z.string(),
  start_at: iso,
  start_price: z.string(),
  end_at: iso,
  end_price: z.string(),
  slope_per_bar: z.string(),
});

const patternTransitionOverlaySchema = z.object({
  status: z.enum(["FORMING", "CONFIRMED", "FAILED", "INVALIDATED"]),
  occurred_at: iso,
  available_at: iso,
  reason: z.string(),
  evidence: jsonValueSchema,
  fingerprint: z.string(),
});

const patternOverlaySchema = z.object({
  pattern_id: z.string(),
  pattern_type: z.string(),
  family: z.string(),
  direction: z.string(),
  symbol: z.string(),
  timeframe: z.string(),
  start_at: iso,
  detected_at: iso,
  end_at: iso,
  confirmed_at: iso.nullable().optional(),
  failed_at: iso.nullable().optional(),
  invalidated_at: iso.nullable().optional(),
  current_status: z.enum(["FORMING", "CONFIRMED", "FAILED", "INVALIDATED"]),
  pivot_source: z.string(),
  points: z.array(patternPointOverlaySchema),
  segments: z.array(patternSegmentOverlaySchema),
  breakout_level: z.string().nullable().optional(),
  metrics: jsonValueSchema,
  diagnostic_flags: z.array(z.string()),
  transitions: z.array(patternTransitionOverlaySchema),
  pattern_fingerprint: z.string(),
});

export const frontendAnalyticsOverlaysSchema = z.object({
  schema_version: z.literal("money-heist.frontend-analytics-overlays.v1"),
  campaign_id: z.string(),
  role: backtestPeriodRoleSchema,
  analytics_available: z.boolean(),
  unavailable_reason: z.string().nullable().optional(),
  source_backtest_run_id: z.string().nullable().optional(),
  analytics_run_id: z.string().nullable().optional(),
  scanner: z.array(scannerOverlaySchema),
  funnel_stages: z.array(frontendFunnelStageSchema),
  technical_events: z.array(technicalEventOverlaySchema),
  structure: z.array(structureOverlaySchema),
  zigzag_pivots: z.array(zigZagPivotOverlaySchema),
  patterns: z.array(patternOverlaySchema),
});

export type FrontendAnalyticsOverlays = z.infer<typeof frontendAnalyticsOverlaysSchema>;
export type ScannerOverlay = FrontendAnalyticsOverlays["scanner"][number];
export type TechnicalEventOverlay = FrontendAnalyticsOverlays["technical_events"][number];
export type StructureOverlay = FrontendAnalyticsOverlays["structure"][number];
export type ZigZagPivotOverlay = FrontendAnalyticsOverlays["zigzag_pivots"][number];
export type PatternOverlay = FrontendAnalyticsOverlays["patterns"][number];
