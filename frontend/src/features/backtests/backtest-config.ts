import type { CampaignConfig, DatasetPreview, SplitIndices } from "@/lib/api/schemas";

export type AiMode = "MOCK" | "CACHED" | "LIVE_EVAL";
export type ReasoningEffort = "none" | "low" | "medium" | "high" | "xhigh" | "max";

export type BacktestFormState = {
  systemId: string;
  codeVersion: string;
  aiMode: AiMode;
  modelId: string;
  reasoningEffort: ReasoningEffort;
  hardBudgetEur: string;
  inputPrice: string;
  outputPrice: string;
  cachedInputPrice: string;
  mockAgentCoverage: boolean;
  initialBalance: string;
  makerFeeBps: string;
  takerFeeBps: string;
  slippageBps: string;
  executionModelVersion: string;
  randomSeed: string;
  riskProfileId: string;
  riskVersion: string;
  maxRiskPerTradePct: string;
  maxDailyLossPct: string;
  maxDrawdownPct: string;
  maxPortfolioRiskPct: string;
  maxPositions: string;
  riskMaxLeverage: string;
  maxCorrelatedExposurePct: string;
  minExpectedRr: string;
  qtyStep: string;
  minQty: string;
  minNotional: string;
  maxQty: string;
  marketMaxLeverage: string;
  derivativesEnabled: boolean;
  derivativesCsvText: string;
  derivativesMaxAgeSeconds: string;
  denverPriorEnabled: boolean;
  denverPriorJsonText: string;
  denverActivationMode: "OOS_ONLY" | "ALL_PERIODS";
  walkForwardEnabled: boolean;
  walkForwardDesignBars: string;
  walkForwardValidationBars: string;
  walkForwardOosBars: string;
  walkForwardStepBars: string;
};

export const defaultBacktestForm = (systemId = "balanced_v1"): BacktestFormState => ({
  systemId,
  codeVersion: "",
  aiMode: "MOCK",
  modelId: "mock-backtest-v1",
  reasoningEffort: "low",
  hardBudgetEur: "1",
  inputPrice: "0",
  outputPrice: "0",
  cachedInputPrice: "",
  mockAgentCoverage: true,
  initialBalance: "100",
  makerFeeBps: "10",
  takerFeeBps: "20",
  slippageBps: "5",
  executionModelVersion: "historical-ohlc-v1",
  randomSeed: "0",
  riskProfileId: "dashboard_balanced_dev",
  riskVersion: "dashboard-balanced-dev-v1",
  maxRiskPerTradePct: "1",
  maxDailyLossPct: "3",
  maxDrawdownPct: "10",
  maxPortfolioRiskPct: "3",
  maxPositions: "3",
  riskMaxLeverage: "1",
  maxCorrelatedExposurePct: "2",
  minExpectedRr: "1.5",
  qtyStep: "",
  minQty: "",
  minNotional: "",
  maxQty: "",
  marketMaxLeverage: "1",
  derivativesEnabled: false,
  derivativesCsvText: "",
  derivativesMaxAgeSeconds: "7200",
  denverPriorEnabled: false,
  denverPriorJsonText: "",
  denverActivationMode: "OOS_ONLY",
  walkForwardEnabled: false,
  walkForwardDesignBars: "300",
  walkForwardValidationBars: "100",
  walkForwardOosBars: "100",
  walkForwardStepBars: "100"
});

export function percentToDecimal(value: string): string {
  const normalized = value.trim().replace(",", ".");
  if (!normalized) return "0";
  const numeric = Number(normalized);
  if (!Number.isFinite(numeric)) throw new Error(`Pourcentage invalide: ${value}`);
  return String(numeric / 100);
}

export function initialSplitIndices(preview: DatasetPreview): SplitIndices | null {
  if (preview.suggested_split_indices) return preview.suggested_split_indices;
  if (preview.candle_close_ms.length < 6) return null;
  const last = preview.candle_close_ms.length - 1;
  const designEnd = Math.max(0, Math.floor(last * 0.6));
  const validationEnd = Math.max(designEnd + 1, Math.floor(last * 0.8));
  if (validationEnd >= last) return null;
  return {
    design_start: 0,
    design_end: designEnd,
    validation_start: designEnd + 1,
    validation_end: validationEnd,
    oos_start: validationEnd + 1,
    oos_end: last
  };
}

export function splitIndicesToDates(preview: DatasetPreview, indices: SplitIndices) {
  const closes = preview.candle_close_ms;
  const names = ["design_start", "design_end", "validation_start", "validation_end", "oos_start", "oos_end"] as const;
  if (!closes.length) {
    if (preview.suggested_split) return preview.suggested_split;
    throw new Error("Le backend n'a pas fourni les close_time nécessaires à la configuration manuelle des périodes.");
  }
  for (const name of names) {
    const value = indices[name];
    if (!Number.isInteger(value) || value < 0 || value >= closes.length) throw new Error(`${name} est hors du dataset.`);
  }
  if (!(indices.design_start <= indices.design_end && indices.design_end < indices.validation_start && indices.validation_start <= indices.validation_end && indices.validation_end < indices.oos_start && indices.oos_start <= indices.oos_end)) {
    throw new Error("Les périodes doivent respecter DESIGN < VALIDATION < OOS sans chevauchement.");
  }
  const iso = (index: number) => new Date(closes[index]!).toISOString();
  return {
    design_start: iso(indices.design_start),
    design_end: iso(indices.design_end),
    validation_start: iso(indices.validation_start),
    validation_end: iso(indices.validation_end),
    oos_start: iso(indices.oos_start),
    oos_end: iso(indices.oos_end)
  };
}

function positiveInt(value: string, label: string): number {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) throw new Error(`${label} doit être un entier > 0.`);
  return parsed;
}

function nonNegativeInt(value: string, label: string): number {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) throw new Error(`${label} doit être un entier >= 0.`);
  return parsed;
}

function requirePositive(value: string, label: string): string {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) throw new Error(`${label} doit être > 0.`);
  return value.trim();
}

function requireNonNegative(value: string, label: string): string {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) throw new Error(`${label} doit être >= 0.`);
  return value.trim();
}

export function buildCampaignConfig(preview: DatasetPreview, indices: SplitIndices, form: BacktestFormState): CampaignConfig {
  if (!form.codeVersion.trim()) throw new Error("Code version / commit est obligatoire.");
  if (!form.systemId.trim()) throw new Error("System ID est obligatoire.");
  if (!form.modelId.trim()) throw new Error("Model ID est obligatoire.");
  if (!form.qtyStep || !form.minQty || !form.minNotional || !form.marketMaxLeverage) throw new Error("Les contraintes marché sont incomplètes.");
  if (form.aiMode === "LIVE_EVAL" && Number(form.inputPrice) === 0 && Number(form.outputPrice) === 0) throw new Error("LIVE_EVAL exige une tarification modèle explicite non nulle.");
  if (form.aiMode === "LIVE_EVAL" && form.modelId.startsWith("mock-")) throw new Error("LIVE_EVAL exige un model_id réel.");

  const wfDesign = positiveInt(form.walkForwardDesignBars, "Walk-forward DESIGN bars");
  const wfValidation = positiveInt(form.walkForwardValidationBars, "Walk-forward VALIDATION bars");
  const wfOos = positiveInt(form.walkForwardOosBars, "Walk-forward OOS bars");
  const wfStep = positiveInt(form.walkForwardStepBars, "Walk-forward step bars");
  if (form.walkForwardEnabled && wfDesign + wfValidation + wfOos > preview.candle_count) {
    throw new Error("La fenêtre walk-forward dépasse la taille du dataset.");
  }

  const advancedSource = ["1m", "5m", "15m"].includes(preview.timeframe);
  if ((form.derivativesEnabled || form.denverPriorEnabled) && !advancedSource) {
    throw new Error("Les données historiques avancées / Denver prior exigent un timeframe source 1m, 5m ou 15m.");
  }
  if (form.derivativesEnabled && !form.derivativesCsvText.trim()) throw new Error("Le CSV derivatives est activé mais absent.");
  if (form.denverPriorEnabled && !form.denverPriorJsonText.trim()) throw new Error("Le Denver prior est activé mais absent.");

  return {
    split: splitIndicesToDates(preview, indices),
    risk: {
      risk_profile_id: form.riskProfileId.trim(),
      risk_version: form.riskVersion.trim(),
      max_risk_per_trade_pct: percentToDecimal(form.maxRiskPerTradePct),
      max_daily_loss_pct: percentToDecimal(form.maxDailyLossPct),
      max_drawdown_pct: percentToDecimal(form.maxDrawdownPct),
      max_portfolio_risk_pct: percentToDecimal(form.maxPortfolioRiskPct),
      max_positions: positiveInt(form.maxPositions, "Max positions"),
      max_leverage: requirePositive(form.riskMaxLeverage, "Risk max leverage"),
      max_correlated_exposure_pct: percentToDecimal(form.maxCorrelatedExposurePct),
      min_expected_rr: form.minExpectedRr.trim() ? requirePositive(form.minExpectedRr, "Min expected RR") : null
    },
    market: {
      qty_step: requirePositive(form.qtyStep, "qty_step"),
      min_qty: requirePositive(form.minQty, "min_qty"),
      min_notional: requirePositive(form.minNotional, "min_notional"),
      max_qty: form.maxQty.trim() ? requirePositive(form.maxQty, "max_qty") : null,
      max_leverage: requirePositive(form.marketMaxLeverage, "market max leverage")
    },
    ai: {
      mode: form.aiMode,
      hard_budget_eur: requireNonNegative(form.hardBudgetEur, "Budget IA"),
      model_id: form.modelId.trim(),
      reasoning_effort: form.reasoningEffort,
      input_per_million_eur: requireNonNegative(form.inputPrice, "Prix input"),
      output_per_million_eur: requireNonNegative(form.outputPrice, "Prix output"),
      cached_input_per_million_eur: form.cachedInputPrice.trim() ? requireNonNegative(form.cachedInputPrice, "Prix cached input") : null,
      mock_agent_coverage: form.aiMode === "MOCK" && form.mockAgentCoverage
    },
    execution: {
      initial_balance: requirePositive(form.initialBalance, "Capital initial"),
      maker_fee_bps: requireNonNegative(form.makerFeeBps, "Maker fee"),
      taker_fee_bps: requireNonNegative(form.takerFeeBps, "Taker fee"),
      market_slippage_bps: requireNonNegative(form.slippageBps, "Slippage"),
      code_version: form.codeVersion.trim(),
      execution_model_version: form.executionModelVersion.trim(),
      random_seed: nonNegativeInt(form.randomSeed, "Random seed")
    },
    walk_forward: {
      enabled: form.walkForwardEnabled,
      design_bars: wfDesign,
      validation_bars: wfValidation,
      oos_bars: wfOos,
      step_bars: wfStep
    },
    derivatives: form.derivativesEnabled ? {csv_text:form.derivativesCsvText,max_age_seconds:positiveInt(form.derivativesMaxAgeSeconds,"Derivatives max age")} : null,
    denver_prior: form.denverPriorEnabled ? {json_text:form.denverPriorJsonText,activation_mode:form.denverActivationMode} : null,
    system_id: form.systemId.trim()
  };
}
