import { z } from "zod";

export const backtestPeriodRoleSchema = z.enum(["DESIGN", "VALIDATION", "OOS"]);

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
  analytics_as_of: z.string().datetime({ offset: true }).nullable().optional(),
  source_cursor_fingerprint: z.string().nullable().optional(),
  analytics_snapshot_source_cursor_fingerprint: z.string().nullable().optional(),
  diagnostics: z.array(z.string()).default([]),
});

const analyticsRunSchema = z.object({
  analytics_run_id: z.string(),
  identity_sha256: z.string(),
  source_backtest_run_id: z.string(),
  dataset_id: z.string(),
  dataset_version: z.string(),
  dataset_content_sha256: z.string(),
  dataset_source: z.string(),
  system_id: z.string(),
  symbol: z.string(),
  source_timeframe: z.string(),
  decision_timeframe: z.string(),
  period_start: z.string().datetime({ offset: true }),
  period_end: z.string().datetime({ offset: true }),
  period_role: backtestPeriodRoleSchema,
  mtf_policy_version: z.string(),
  analytics_bundle_version: z.string(),
  component_versions: z.record(z.string()),
  analytics_sha256: z.string(),
  snapshot_count: z.number().int().nonnegative(),
});

const analyticsSnapshotSchema = z.object({
  snapshot_id: z.string(),
  analytics_run_id: z.string(),
  as_of: z.string().datetime({ offset: true }),
  symbol: z.string(),
  decision_timeframe: z.string(),
  snapshot_fingerprint: z.string(),
  source_cursor_fingerprint: z.string(),
  component_names: z.array(z.string()),
});

export const frontendAnalyticsProjectionSchema = z.object({
  schema_version: z.literal("money-heist.frontend-analytics-projection.v1"),
  campaign_id: z.string(),
  role: backtestPeriodRoleSchema,
  analytics_available: z.boolean(),
  unavailable_reason: z.string().nullable().optional(),
  run: analyticsRunSchema.nullable().optional(),
  snapshots: z.array(analyticsSnapshotSchema),
  opportunity_count: z.number().int().nonnegative(),
  scanner_evaluation_count: z.number().int().nonnegative(),
  decision_record_count: z.number().int().nonnegative(),
  funnel_stage_count: z.number().int().nonnegative(),
});

const scannerEvaluationSchema = z.object({
  record_id: z.string(),
  scanner_evaluation_id: z.string(),
  observed_at: z.string().datetime({ offset: true }),
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

export const frontendScannerAnalyticsProjectionSchema = z.object({
  schema_version: z.literal("money-heist.frontend-scanner-analytics.v1"),
  campaign_id: z.string(),
  role: backtestPeriodRoleSchema,
  analytics_available: z.boolean(),
  unavailable_reason: z.string().nullable().optional(),
  source_backtest_run_id: z.string().nullable().optional(),
  analytics_run_id: z.string().nullable().optional(),
  total_scanner_evaluations: z.number().int().nonnegative(),
  matched_analytics: z.number().int().nonnegative(),
  unmatched_analytics: z.number().int().nonnegative(),
  no_trigger_count: z.number().int().nonnegative(),
  below_threshold_count: z.number().int().nonnegative(),
  candidate_count: z.number().int().nonnegative(),
  records: z.array(scannerEvaluationSchema),
});

const opportunityLinkSchema = z.object({
  link_id: z.string(),
  link_fingerprint: z.string(),
  status: z.string(),
  opportunity_id: z.string(),
  opportunity_fingerprint: z.string(),
  observed_at: z.string().datetime({ offset: true }),
  decision_timeframe: z.string(),
  analytics_snapshot_id: z.string().nullable().optional(),
  analytics_snapshot_fingerprint: z.string().nullable().optional(),
  analytics_as_of: z.string().datetime({ offset: true }).nullable().optional(),
  diagnostics: z.array(z.string()),
});

export const frontendFunnelStageSchema = z.object({
  record_id: z.string(),
  record_fingerprint: z.string(),
  decision_intelligence_record_id: z.string(),
  opportunity_id: z.string(),
  stage: z.string(),
  stage_order: z.number().int().nonnegative(),
  stage_instance_id: z.string().nullable().optional(),
  stage_instance_order: z.number().int().nonnegative().nullable().optional(),
  agent_id: z.string().nullable().optional(),
  agent_request_id: z.string().nullable().optional(),
  agent_prompt_version: z.string().nullable().optional(),
  agent_route_id: z.string().nullable().optional(),
  agent_model_id: z.string().nullable().optional(),
  reached: z.boolean(),
  stage_status: z.string().nullable().optional(),
  stage_result: z.string().nullable().optional(),
  reason_codes: z.array(z.string()),
  selected_agents: z.array(z.string()),
  confidence: z.number().min(0).max(1).nullable().optional(),
  severity: z.number().min(0).max(1).nullable().optional(),
  failure_code: z.string().nullable().optional(),
  failure_stage: z.string().nullable().optional(),
  failure_agent_id: z.string().nullable().optional(),
  market_as_of: z.string().datetime({ offset: true }),
  operational_at: z.string().datetime({ offset: true }).nullable().optional(),
  source_artifact_ref: z.string().nullable().optional(),
  source_artifact_fingerprint: z.string().nullable().optional(),
  source_projection_fingerprint: z.string(),
  analytics: analyticsRefSchema,
});

const decisionContextSchema = z.object({
  present: z.boolean(),
  context_id: z.string().nullable().optional(),
  context_fingerprint: z.string().nullable().optional(),
  schema_version: z.string().nullable().optional(),
  context_version: z.string().nullable().optional(),
  system_id: z.string().nullable().optional(),
  symbol: z.string().nullable().optional(),
  as_of: z.string().datetime({ offset: true }).nullable().optional(),
  primary_timeframe: z.string().nullable().optional(),
  timeframe_policy_version: z.string().nullable().optional(),
  source_cursor_fingerprint: z.string().nullable().optional(),
});

const jsonPrimitiveSchema = z.union([z.string(), z.number(), z.boolean(), z.null()]);
type JsonValue = z.infer<typeof jsonPrimitiveSchema> | JsonValue[] | { [key: string]: JsonValue };
const jsonValueSchema: z.ZodType<JsonValue> = z.lazy(() =>
  z.union([jsonPrimitiveSchema, z.array(jsonValueSchema), z.record(jsonValueSchema)]),
);

const decisionRecordSchema = z.object({
  record_id: z.string(),
  record_fingerprint: z.string(),
  source_backtest_run_id: z.string(),
  analytics_run_id: z.string(),
  opportunity_id: z.string(),
  opportunity_fingerprint: z.string(),
  system_id: z.string(),
  symbol: z.string(),
  decision_timeframe: z.string(),
  observed_at: z.string().datetime({ offset: true }),
  scanner: scannerEvaluationSchema,
  decision_context: decisionContextSchema,
  decision: jsonValueSchema,
  analytics: analyticsRefSchema,
});

export const frontendDecisionIntelligenceDetailSchema = z.object({
  schema_version: z.literal("money-heist.frontend-decision-intelligence-detail.v1"),
  campaign_id: z.string(),
  role: backtestPeriodRoleSchema,
  opportunity_id: z.string(),
  decision_intelligence_available: z.boolean(),
  unavailable_reason: z.string().nullable().optional(),
  opportunity_link: opportunityLinkSchema.nullable().optional(),
  record: decisionRecordSchema.nullable().optional(),
  funnel_stages: z.array(frontendFunnelStageSchema),
});

export type BacktestPeriodRole = z.infer<typeof backtestPeriodRoleSchema>;
export type FrontendAnalyticsProjection = z.infer<typeof frontendAnalyticsProjectionSchema>;
export type FrontendScannerAnalyticsProjection = z.infer<
  typeof frontendScannerAnalyticsProjectionSchema
>;
export type FrontendDecisionIntelligenceDetail = z.infer<
  typeof frontendDecisionIntelligenceDetailSchema
>;
