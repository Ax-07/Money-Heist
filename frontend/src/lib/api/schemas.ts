import { z } from "zod";

const decimal = z.union([z.string(), z.number()]).transform(String);
const periodRole = z.enum(["DESIGN", "VALIDATION", "OOS"]);
export const reasoningEffortSchema = z.enum(["none", "low", "medium", "high", "xhigh", "max"]);

export const openAiModelSchema = z.object({
  model_id: z.string(), display_name: z.string(), input_per_million_usd: decimal, cached_input_per_million_usd: decimal, output_per_million_usd: decimal,
  reasoning_efforts: z.array(reasoningEffortSchema), default_reasoning_effort: reasoningEffortSchema, recommended: z.boolean(),
  pricing_currency: z.literal("USD"), pricing_tier: z.literal("STANDARD"), pricing_source: z.literal("OPENAI_OFFICIAL"), pricing_snapshot_at: z.string(),
  pricing_valid_until: z.string().nullable(), standard_context_max_tokens: z.number().int().positive(), source_url: z.string(), notes: z.array(z.string()).default([])
});
export const openAiModelCatalogSchema = z.object({
  schema_version: z.string(), provider: z.literal("openai"), pricing_currency: z.literal("USD"), pricing_snapshot_at: z.string(), models: z.array(openAiModelSchema)
});

export const metricSchema = z.object({
  name: z.string(), value: decimal.nullable().optional(), availability: z.string(), unit: z.string().nullable().optional(),
  reason: z.string().nullable().optional(), provenance: z.string().optional()
});

export const opportunitySchema = z.object({
  system_id: z.string(), opportunity_id: z.string(), root_opportunity_id: z.string().nullable().optional(), source_snapshot_id: z.string(),
  symbol: z.string(), timeframe: z.string(), priority_score: z.number().nullable().optional(), triggers: z.array(z.string()).default([]),
  created_at: z.string().nullable().optional(), expires_at: z.string().nullable().optional(), provenance: z.string().optional()
});

export const professorDecisionSchema = z.object({
  direction: z.string(), confidence: z.number(), thesis: z.array(z.string()).default([]), counter_evidence: z.array(z.string()).default([]),
  invalidation: z.array(z.string()).default([])
});

export const tradeProposalSchema = z.object({
  proposal_id: z.string(), opportunity_id: z.string(), source_snapshot_id: z.string(), system_id: z.string(), symbol: z.string(), timeframe: z.string(),
  side: z.string(), confidence: z.number(), entry_price: decimal, stop_price: decimal, targets: z.array(decimal), expected_rr: decimal,
  market_regime: z.string(), expires_at: z.string(), provenance: z.string().optional()
});

export const riskDecisionSchema = z.object({
  risk_decision_id: z.string(), proposal_id: z.string(), status: z.string(), reason_codes: z.array(z.string()).default([]), approved_quantity: decimal,
  approved_risk_amount: decimal, approved_notional: decimal, created_at: z.string()
});

export const decisionSchema = z.object({
  system_id: z.string(), opportunity_id: z.string(), source_snapshot_id: z.string(), pipeline_status: z.string(), branch_status: z.string(),
  professor: professorDecisionSchema.nullable().optional(), proposal: tradeProposalSchema.nullable().optional(), risk: riskDecisionSchema.nullable().optional(),
  failure_code: z.string().nullable().optional(), failure_stage: z.string().nullable().optional(), failure_message: z.string().nullable().optional(), provenance: z.string().optional()
});

export const orderSchema = z.object({
  broker_order_id: z.string(), client_order_id: z.string(), system_id: z.string(), symbol: z.string(), side: z.string(), order_type: z.string(),
  requested_quantity: decimal, filled_quantity: decimal, status: z.string(), limit_price: decimal.nullable().optional(), average_fill_price: decimal.nullable().optional(),
  reject_reason: z.string().nullable().optional(), trigger: z.string().nullable().optional(), created_at: z.string(), updated_at: z.string(), provenance: z.string().optional()
});

export const fillSchema = z.object({
  fill_id: z.string(), broker_order_id: z.string(), price: decimal, quantity: decimal, fee: decimal, liquidity: z.string(), filled_at: z.string(), provenance: z.string().optional()
});

export const positionSchema = z.object({
  system_id: z.string(), symbol: z.string(), side: z.string().nullable().optional(), quantity: decimal, average_entry: decimal, realized_pnl: decimal, provenance: z.string().optional()
});

export const dashboardEventSchema = z.object({
  event_id: z.string(), kind: z.string(), severity: z.string(), system_id: z.string().nullable().optional(), opportunity_id: z.string().nullable().optional(),
  source: z.string(), stage: z.string().nullable().optional(), status: z.string().nullable().optional(), code: z.string().nullable().optional(),
  message: z.string().nullable().optional(), created_at: z.string(), details: z.record(z.unknown()).default({})
});

const agentMetricSchema = z.object({
  agent_id: z.string(), call_count: z.number(), attempt_count: z.number(), total_cost_eur: decimal,
  average_cost_eur: metricSchema, average_latency_ms: metricSchema, participation_frequency: metricSchema,
  disagreement_frequency: metricSchema, average_confidence: metricSchema
});

export const dashboardSystemSchema = z.object({
  system_id: z.string(), family: z.string(), display_name: z.string(), aliases: z.array(z.string()), mode: z.string(), execution_mode: z.string(), live_execution: z.boolean(),
  account: z.object({
    availability: z.string(), reason: z.string().nullable().optional(), initial_balance: decimal.nullable().optional(), cash_balance: decimal.nullable().optional(),
    equity: decimal.nullable().optional(), realized_pnl: decimal.nullable().optional(), unrealized_pnl: decimal.nullable().optional(), fees_paid: decimal.nullable().optional(),
    gross_exposure: decimal.nullable().optional(), open_positions: z.number().nullable().optional()
  }),
  positions_availability: z.string().optional(), positions_reason: z.string().nullable().optional(), positions: z.array(positionSchema).default([]),
  orders_availability: z.string().optional(), orders_reason: z.string().nullable().optional(), orders: z.array(orderSchema).default([]),
  fills_availability: z.string().optional(), fills_reason: z.string().nullable().optional(), fills: z.array(fillSchema).default([]), latest_decision: decisionSchema.nullable().optional(),
  ai_usage: z.object({
    availability: z.string(), reason: z.string().nullable().optional(), record_count: z.number(), total_cost_eur: decimal.nullable().optional(),
    by_agent_eur: z.record(decimal).default({}), by_model_eur: z.record(decimal).default({})
  }),
  batch10: z.object({
    status: z.string(), metrics: z.record(metricSchema).default({}), agents: z.array(agentMetricSchema).default([]),
    counterfactuals: z.array(z.unknown()).default([]), failure: z.string().nullable().optional()
  })
});

export const dashboardSnapshotSchema = z.object({
  schema_version: z.string(), generated_at: z.string(), read_only: z.boolean(), live_execution: z.boolean(), execution_scope: z.string(), system_state: z.string(),
  root_correlation_id: z.string().nullable().optional(), root_opportunity_id: z.string().nullable().optional(), root_snapshot_id: z.string().nullable().optional(),
  systems: z.array(dashboardSystemSchema), opportunities: z.array(opportunitySchema).default([]), decisions: z.array(decisionSchema).default([]),
  comparison: z.unknown(), events: z.array(dashboardEventSchema).default([])
});

export const frontendCapabilitiesSchema = z.object({
  schema_version: z.string(), runtime_mode: z.string(), app_env: z.string(), default_system_id: z.string(), market_symbols: z.array(z.string()), market_timeframes: z.array(z.string()),
  realtime_transport: z.literal("POLLING"), live_environment: z.string(), live_system_id: z.string().nullable(), live_timeframes: z.array(z.string()).nullable(),
  live_operational_state: z.literal("UNAVAILABLE"), live_controls_exposed: z.boolean(), chart_provider: z.literal("LIGHTWEIGHT_CHARTS"),
  chart_data_source: z.literal("BACKEND"), backtest_paper_only: z.boolean()
});

export const candleSchema = z.object({
  time: z.number(), open_time: z.string(), close_time: z.string(), open: decimal, high: decimal, low: decimal, close: decimal, volume: decimal, is_closed: z.boolean()
});
export const marketCandlesSchema = z.object({symbol: z.string(), timeframe: z.string(), source: z.string(), candles: z.array(candleSchema)});
export const marketConstraintsSchema = z.object({symbol:z.string(),source:z.string(),tick_size:decimal,qty_step:decimal,min_qty:decimal,min_notional:decimal,max_leverage:decimal,price_precision:z.number(),quantity_precision:z.number(),status:z.string()});

export const agentTraceSchema = z.object({
  sequence: z.number(), observed_at: z.string(), role: periodRole, opportunity_id: z.string(), agent: z.string(), phase: z.string(), title: z.string(),
  details: z.record(z.unknown()).default({}), targets: z.array(z.string()).default([])
});

export const replayTradeSchema = z.object({
  trade_id: z.string(), system_id: z.string(), symbol: z.string(), side: z.string(), quantity: decimal, entry_price: decimal, exit_price: decimal,
  opened_at: z.string(), closed_at: z.string(), net_pnl: decimal, fees: decimal, slippage_cost: decimal.nullable().optional()
});
export const replayEventSchema = z.object({
  event_id: z.string(), observed_at: z.string(), event_type: z.string(), label: z.string(), opportunity_id: z.string().nullable().optional(), agent: z.string().nullable().optional(),
  phase: z.string().nullable().optional(), price: decimal.nullable().optional(), details: z.record(z.unknown()).default({})
});
export const replaySchema = z.object({
  campaign_id: z.string(), role: periodRole, symbol: z.string(), timeframe: z.string(), candles: z.array(candleSchema), events: z.array(replayEventSchema),
  traces: z.array(agentTraceSchema), trades: z.array(replayTradeSchema), equity: z.array(z.object({observed_at: z.string(), equity: decimal, data_kind: z.string()}))
});

export const splitSchema = z.object({
  design_start: z.string(), design_end: z.string(), validation_start: z.string(), validation_end: z.string(), oos_start: z.string(), oos_end: z.string()
});
export const splitIndexSchema = z.object({
  design_start: z.number().int().nonnegative(), design_end: z.number().int().nonnegative(), validation_start: z.number().int().nonnegative(),
  validation_end: z.number().int().nonnegative(), oos_start: z.number().int().nonnegative(), oos_end: z.number().int().nonnegative()
});
export const datasetPreviewSchema = z.object({
  dataset_id: z.string(), version: z.string(), content_sha256: z.string(), symbol: z.string(), timeframe: z.string(), source: z.string(), candle_count: z.number(),
  start_at: z.string(), end_at: z.string(), is_valid: z.boolean(), gap_count: z.number(), has_duplicates: z.boolean(), missing_fields: z.array(z.string()),
  suggested_split: splitSchema.nullable().optional(), candle_close_ms: z.array(z.number()).default([]), suggested_split_indices: splitIndexSchema.nullable().optional()
});
export const datasetCatalogSchema = z.object({
  dataset_id: z.string(), content_sha256: z.string(), symbol: z.string(), timeframe: z.string(), source: z.string(), candle_count: z.number(),
  start_at: z.string(), end_at: z.string(), is_valid: z.boolean(), gap_count: z.number()
});

const backtestMetricSchema = z.object({value: z.string().nullable(), status: z.string(), reason: z.string().nullable().optional()});
export const periodSummarySchema = z.object({
  role: periodRole, run_id: z.string(), processed_candles: z.number(), opportunities: z.number(), executed_orders: z.number(), closed_trades: z.number(),
  trading_net: backtestMetricSchema, economic_net: backtestMetricSchema, max_drawdown_pct: backtestMetricSchema, win_rate: backtestMetricSchema,
  profit_factor: backtestMetricSchema, expectancy: backtestMetricSchema, ai_cost_eur: z.string(), self_funding_ratio: z.string().nullable(), self_funding_status: z.string(), business_sha256: z.string()
});
export const campaignSummarySchema = z.object({
  campaign_id: z.string(), created_at: z.string(), status: z.string(), ai_mode: z.string(), dataset: datasetPreviewSchema,
  design: periodSummarySchema, validation: periodSummarySchema, oos: periodSummarySchema,
  oos_equity: z.array(z.object({observed_at: z.string(), equity: z.string()})).default([]), walk_forward_plan_id: z.string().nullable().optional(),
  walk_forward_oos: z.array(z.unknown()).default([]), exports: z.array(z.string()).default([])
});

export const campaignProgressSchema = z.object({
  campaign_id: z.string(), created_at: z.string(), status: z.string(), phase: z.string(), current_role: periodRole.nullable().optional(), percent: z.number(),
  work_done: z.number(), total_work: z.number(), current_observed_at: z.string().nullable().optional(), opportunity_count: z.number(), executed_order_count: z.number(),
  agent_traces: z.array(agentTraceSchema).default([]), active_agents: z.array(z.string()).default([]), error: z.string().nullable().optional(), message: z.string(),
  can_cancel: z.boolean(), result_available: z.boolean()
});

export const agentDescriptorSchema = z.object({agent: z.string(), role: z.string(), state: z.string(), core: z.boolean()});
export const backtestCapabilitiesSchema = z.object({
  modes: z.array(z.string()), live_eval_available: z.boolean(), cache_entries: z.number(), supported_timeframes: z.array(z.string()), agents: z.array(agentDescriptorSchema),
  paper_only: z.boolean(), live_trading: z.boolean(), campaign_cancel: z.boolean(), campaign_progress: z.boolean(), agent_traces: z.boolean(), agent_activity: z.boolean()
});

export const datasetInputSchema = z.object({
  csv_text: z.string().min(1), symbol: z.string().min(1), timeframe: z.string().min(1), source: z.string().min(1), candle_interval_seconds: z.number().int().positive().nullable().optional()
});
export const riskInputSchema = z.object({
  risk_profile_id: z.string(), risk_version: z.string(), max_risk_per_trade_pct: z.string(), max_daily_loss_pct: z.string(), max_drawdown_pct: z.string(),
  max_portfolio_risk_pct: z.string(), max_positions: z.number().int().positive(), max_leverage: z.string(), max_correlated_exposure_pct: z.string(), min_expected_rr: z.string().nullable()
});
export const marketInputSchema = z.object({qty_step: z.string(), min_qty: z.string(), min_notional: z.string(), max_qty: z.string().nullable(), max_leverage: z.string().nullable()});
export const legacyAiInputSchema = z.object({
  mode: z.enum(["MOCK", "CACHED", "LIVE_EVAL"]), hard_budget_eur: z.string(), model_id: z.string(), reasoning_effort: reasoningEffortSchema,
  input_per_million_eur: z.string(), output_per_million_eur: z.string(), cached_input_per_million_eur: z.string().nullable(), mock_agent_coverage: z.boolean()
});
export const frontendAiInputSchema = z.object({
  mode: z.enum(["MOCK", "CACHED", "LIVE_EVAL"]), hard_budget_usd: z.string(), model_id: z.string(), reasoning_effort: reasoningEffortSchema, mock_agent_coverage: z.boolean()
});
export const campaignAiConfigurationSchema = z.object({
  mode: z.string(), hard_budget: z.string(), model_id: z.string(), reasoning_effort: z.string(), input_per_million: z.string(),
  cached_input_per_million: z.string().nullable(), output_per_million: z.string(), currency: z.enum(["USD", "EUR"]), pricing_source: z.string(),
  pricing_snapshot_at: z.string().nullable().optional(), pricing_tier: z.string().nullable().optional(), mock_agent_coverage: z.boolean()
});
export const executionInputSchema = z.object({
  initial_balance: z.string(), maker_fee_bps: z.string(), taker_fee_bps: z.string(), market_slippage_bps: z.string(), code_version: z.string(), execution_model_version: z.string(), random_seed: z.number().int().nonnegative()
});
export const walkForwardInputSchema = z.object({enabled: z.boolean(), design_bars: z.number().int().positive(), validation_bars: z.number().int().positive(), oos_bars: z.number().int().positive(), step_bars: z.number().int().positive()});
export const historicalDerivativesInputSchema = z.object({csv_text:z.string().min(1),max_age_seconds:z.number().int().positive()});
export const frozenDenverPriorInputSchema = z.object({json_text:z.string().min(1),activation_mode:z.enum(["OOS_ONLY","ALL_PERIODS"])});
const campaignConfigFields = {
  split: splitSchema, risk: riskInputSchema, market: marketInputSchema, execution: executionInputSchema, walk_forward: walkForwardInputSchema,
  derivatives: historicalDerivativesInputSchema.nullable(), denver_prior: frozenDenverPriorInputSchema.nullable(), system_id: z.string().min(1)
};
export const campaignConfigSchema = z.object({...campaignConfigFields, ai: frontendAiInputSchema});
export const campaignRequestSchema = z.object({...campaignConfigFields, ai: legacyAiInputSchema, dataset: datasetInputSchema});
export const storedCampaignRequestSchema = campaignConfigSchema.extend({dataset_id: z.string().min(1)});
export const campaignConfigurationSchema = z.object({
  ...campaignConfigFields, ai: campaignAiConfigurationSchema, campaign_id: z.string(), dataset_id: z.string(), dataset: datasetPreviewSchema
});

export type DashboardSnapshot = z.infer<typeof dashboardSnapshotSchema>;
export type DashboardSystem = z.infer<typeof dashboardSystemSchema>;
export type DashboardDecision = z.infer<typeof decisionSchema>;
export type FrontendCapabilities = z.infer<typeof frontendCapabilitiesSchema>;
export type OpenAiModel = z.infer<typeof openAiModelSchema>;
export type OpenAiModelCatalog = z.infer<typeof openAiModelCatalogSchema>;
export type MarketCandles = z.infer<typeof marketCandlesSchema>;
export type MarketConstraints = z.infer<typeof marketConstraintsSchema>;
export type BacktestReplay = z.infer<typeof replaySchema>;
export type CampaignSummary = z.infer<typeof campaignSummarySchema>;
export type CampaignProgress = z.infer<typeof campaignProgressSchema>;
export type DatasetPreview = z.infer<typeof datasetPreviewSchema>;
export type DatasetCatalogItem = z.infer<typeof datasetCatalogSchema>;
export type SplitIndices = z.infer<typeof splitIndexSchema>;
export type CampaignConfig = z.infer<typeof campaignConfigSchema>;
export type CampaignRequest = z.infer<typeof campaignRequestSchema>;
export type StoredCampaignRequest = z.infer<typeof storedCampaignRequestSchema>;
export type CampaignConfiguration = z.infer<typeof campaignConfigurationSchema>;
export type BacktestCapabilities = z.infer<typeof backtestCapabilitiesSchema>;
export type AgentTrace = z.infer<typeof agentTraceSchema>;
