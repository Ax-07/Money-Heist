import { z } from "zod";

import { backtestPeriodRoleSchema } from "./decision-intelligence-schemas";

const decimalSchema = z.string().nullable();

const scannerHorizonSchema = z.object({
  horizon_bars: z.number().int().positive(),
  scanner_count: z.number().int().nonnegative(),
  outcome_available_count: z.number().int().nonnegative(),
  outcome_missing_count: z.number().int().nonnegative(),
  complete_count: z.number().int().nonnegative(),
  incomplete_count: z.number().int().nonnegative(),
  raw_return_mean_pct: decimalSchema,
  raw_return_median_pct: decimalSchema,
  positive_rate: decimalSchema,
  max_upside_median_pct: decimalSchema,
  max_downside_median_pct: decimalSchema,
  max_absolute_excursion_median_pct: decimalSchema,
  first_hit_upside_rate: decimalSchema,
  first_hit_downside_rate: decimalSchema,
}).passthrough();

const scannerCohortSchema = z.object({
  schema_version: z.string(),
  dimension: z.string(),
  key: z.string(),
  numeric_value: z.number().int().nullable(),
  multi_valued: z.boolean(),
  scanner_count: z.number().int().nonnegative(),
  horizons: z.array(scannerHorizonSchema),
  cohort_fingerprint: z.string(),
}).passthrough();

const scannerContrastSchema = z.object({
  schema_version: z.string(),
  kind: z.string(),
  left_classification: z.string(),
  right_classification: z.string(),
  horizons: z.array(z.object({
    horizon_bars: z.number().int().positive(),
    left_scanner_count: z.number().int().nonnegative(),
    right_scanner_count: z.number().int().nonnegative(),
    left_complete_count: z.number().int().nonnegative(),
    right_complete_count: z.number().int().nonnegative(),
    median_raw_return_delta_pct: decimalSchema,
    median_max_absolute_excursion_delta_pct: decimalSchema,
  }).passthrough()),
}).passthrough();

const scannerFilteringReportSchema = z.object({
  schema_version: z.string(),
  policy_version: z.string(),
  report_id: z.string(),
  research_run_id: z.string(),
  source_backtest_run_id: z.string(),
  analytics_run_id: z.string(),
  period_role: backtestPeriodRoleSchema,
  source_bundle_fingerprint: z.string(),
  scanner_count: z.number().int().nonnegative(),
  classification_summary: z.object({
    scanner_count: z.number().int().nonnegative(),
    no_trigger_count: z.number().int().nonnegative(),
    below_threshold_count: z.number().int().nonnegative(),
    candidate_count: z.number().int().nonnegative(),
    triggered_count: z.number().int().nonnegative(),
  }).passthrough(),
  coverage: z.object({
    scanner_records: z.number().int().nonnegative(),
    with_future_outcome: z.number().int().nonnegative(),
    without_future_outcome: z.number().int().nonnegative(),
    with_analytics: z.number().int().nonnegative(),
    without_analytics: z.number().int().nonnegative(),
    horizons: z.array(z.object({
      horizon_bars: z.number().int().positive(),
      scanner_records: z.number().int().nonnegative(),
      with_future_outcome: z.number().int().nonnegative(),
      without_future_outcome: z.number().int().nonnegative(),
      complete_count: z.number().int().nonnegative(),
      incomplete_count: z.number().int().nonnegative(),
    }).passthrough()),
  }).passthrough(),
  cohorts: z.array(scannerCohortSchema),
  contrasts: z.array(scannerContrastSchema),
  report_fingerprint: z.string(),
}).passthrough();

const directionlessHorizonSchema = z.object({
  horizon_bars: z.number().int().positive(),
  observation_count: z.number().int().nonnegative(),
  outcome_available_count: z.number().int().nonnegative(),
  outcome_missing_count: z.number().int().nonnegative(),
  complete_count: z.number().int().nonnegative(),
  incomplete_count: z.number().int().nonnegative(),
  raw_return_mean_pct: decimalSchema,
  raw_return_median_pct: decimalSchema,
  max_absolute_excursion_median_pct: decimalSchema,
}).passthrough();

const directionalHorizonSchema = z.object({
  horizon_bars: z.number().int().positive(),
  direction_available_count: z.number().int().nonnegative(),
  direction_unavailable_count: z.number().int().nonnegative(),
  directional_complete_count: z.number().int().nonnegative(),
  directional_return_mean_pct: decimalSchema,
  directional_return_median_pct: decimalSchema,
  favorable_excursion_median_pct: decimalSchema,
  adverse_excursion_median_pct: decimalSchema,
}).passthrough();

const funnelCohortSchema = z.object({
  schema_version: z.string(),
  stage: z.string(),
  dimension: z.string(),
  key: z.string(),
  multi_valued: z.boolean(),
  candidate_count: z.number().int().nonnegative(),
  observation_count: z.number().int().nonnegative(),
  direction_available_count: z.number().int().nonnegative(),
  direction_unavailable_count: z.number().int().nonnegative(),
  horizons: z.array(directionlessHorizonSchema),
  directional_horizons: z.array(directionalHorizonSchema),
  member_refs: z.array(z.string()),
  cohort_fingerprint: z.string(),
}).passthrough();

const funnelContrastSchema = z.object({
  schema_version: z.string(),
  kind: z.string(),
  stage: z.string(),
  left_key: z.string(),
  right_key: z.string(),
  horizons: z.array(z.object({
    horizon_bars: z.number().int().positive(),
    left_count: z.number().int().nonnegative(),
    right_count: z.number().int().nonnegative(),
    left_complete_count: z.number().int().nonnegative(),
    right_complete_count: z.number().int().nonnegative(),
    median_raw_return_delta_pct: decimalSchema,
    median_max_absolute_excursion_delta_pct: decimalSchema,
    median_directional_return_delta_pct: decimalSchema,
    median_favorable_excursion_delta_pct: decimalSchema,
    median_adverse_excursion_delta_pct: decimalSchema,
  }).passthrough()),
}).passthrough();

const funnelReportSchema = z.object({
  schema_version: z.string(),
  policy_version: z.string(),
  report_id: z.string(),
  research_run_id: z.string(),
  source_backtest_run_id: z.string(),
  analytics_run_id: z.string(),
  period_role: backtestPeriodRoleSchema,
  source_bundle_fingerprint: z.string(),
  source_funnel_stage_set_fingerprint: z.string(),
  source_decision_record_set_fingerprint: z.string(),
  candidate_count: z.number().int().nonnegative(),
  coverage: z.object({
    candidate_count: z.number().int().nonnegative(),
    candidates_with_future_outcome: z.number().int().nonnegative(),
    candidates_without_future_outcome: z.number().int().nonnegative(),
    candidates_with_analytics: z.number().int().nonnegative(),
    candidates_without_analytics: z.number().int().nonnegative(),
    stages: z.array(z.object({
      stage: z.string(),
      candidate_count: z.number().int().nonnegative(),
      record_count: z.number().int().nonnegative(),
      reached_count: z.number().int().nonnegative(),
      not_reached_count: z.number().int().nonnegative(),
      failure_count: z.number().int().nonnegative(),
    }).passthrough()),
  }).passthrough(),
  cohorts: z.array(funnelCohortSchema),
  contrasts: z.array(funnelContrastSchema),
  report_fingerprint: z.string(),
}).passthrough();

export const frontendDecisionQualityResearchSchema = z.object({
  schema_version: z.literal("money-heist.frontend-decision-quality-research.v1"),
  campaign_id: z.string(),
  role: backtestPeriodRoleSchema,
  research_available: z.boolean(),
  unavailable_reason: z.string().nullable().optional(),
  research_run_id: z.string().nullable().optional(),
  source_backtest_run_id: z.string().nullable().optional(),
  analytics_run_id: z.string().nullable().optional(),
  evidence_index_fingerprint: z.string().nullable().optional(),
  scanner_filtering: scannerFilteringReportSchema.nullable().optional(),
  funnel_decision_quality: funnelReportSchema.nullable().optional(),
});

export const researchEvidenceItemSchema = z.object({
  schema_version: z.string(),
  ref_id: z.string(),
  subject_type: z.enum(["SCANNER_OBSERVATION", "FUNNEL_STAGE"]),
  source_record_id: z.string(),
  source_record_fingerprint: z.string(),
  opportunity_id: z.string().nullable().optional(),
  scan_id: z.string().nullable().optional(),
  stage_record_id: z.string().nullable().optional(),
  stage: z.string().nullable().optional(),
  observed_at: z.string().datetime({ offset: true }),
  navigation_at: z.string().datetime({ offset: true }),
  object_type: z.string(),
  object_id: z.string(),
  label: z.string(),
  details: z.record(z.string()),
});

export const researchEvidencePageSchema = z.object({
  schema_version: z.literal("money-heist.frontend-research-evidence-page.v1"),
  campaign_id: z.string(),
  role: backtestPeriodRoleSchema,
  selector: z.object({
    report_type: z.enum(["SCANNER_FILTERING", "FUNNEL_DECISION_QUALITY"]),
    dimension: z.string(),
    key: z.string(),
    stage: z.string().nullable().optional(),
  }),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total: z.number().int().nonnegative(),
  page_count: z.number().int().nonnegative(),
  items: z.array(researchEvidenceItemSchema),
});

export type FrontendDecisionQualityResearch = z.infer<
  typeof frontendDecisionQualityResearchSchema
>;
export type ScannerFilteringReport = z.infer<typeof scannerFilteringReportSchema>;
export type FunnelDecisionQualityReport = z.infer<typeof funnelReportSchema>;
export type ResearchEvidenceItem = z.infer<typeof researchEvidenceItemSchema>;
export type ResearchEvidencePage = z.infer<typeof researchEvidencePageSchema>;
