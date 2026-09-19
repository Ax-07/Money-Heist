import type { CampaignConfig, DatasetPreview, SplitIndices } from "@/lib/api/schemas";

export type AiMode = "MOCK" | "CACHED" | "LIVE_EVAL";
export type ReasoningEffort = "none" | "low" | "medium" | "high" | "xhigh" | "max";
export type PositioningMode = "SPOT_LONG_ONLY" | "LONG_SHORT";

export const HISTORICAL_DATASET_TIMEFRAMES = [
  "1m",
  "5m",
  "15m",
  "30m",
  "1h",
  "4h",
  "1d",
] as const;


export const HISTORICAL_DATASET_SYMBOLS = [
  "BTC/USDC",
  "ETH/USDC",
  "SOL/USDC",
  "BTC/EUR",
  "ETH/EUR",
  "SOL/EUR",
] as const;

export type HistoricalMarketPreset = {
  label: string;
  qtyStep: string;
  minQty: string;
  minNotional: string;
  maxQty: string;
  maxLeverage: string;
  positioningMode: PositioningMode;
};

const HISTORICAL_MARKET_PRESETS: Record<string, HistoricalMarketPreset> = {
  "BTC/USDC": {
    label: "Binance Spot BTC/USDC · 2026-09-11",
    qtyStep: "0.00001",
    minQty: "0.00001",
    minNotional: "5",
    maxQty: "9000",
    maxLeverage: "1",
    positioningMode: "SPOT_LONG_ONLY",
  },
};

export function historicalMarketPreset(symbol: string): HistoricalMarketPreset | null {
  return HISTORICAL_MARKET_PRESETS[symbol.trim().toUpperCase()] ?? null;
}

export function detectHistoricalDatasetIdentity(filename: string): {
  symbol: string | null;
  timeframe: string | null;
} {
  const normalized = String(filename || "")
    .toUpperCase()
    .replace(/\.[^.]+$/, "")
    .replace(/[^A-Z0-9]+/g, "_");
  let symbol: string | null = null;
  let timeframe: string | null = null;

  for (const candidate of HISTORICAL_DATASET_SYMBOLS) {
    const compact = candidate.replace("/", "");
    const underscored = candidate.replace("/", "_");
    if (normalized.includes(compact) || normalized.includes(underscored)) {
      symbol = candidate;
      break;
    }
  }

  if (/(^|_)1M($|_)/.test(normalized)) timeframe = "1m";
  else if (/(^|_)5M($|_)/.test(normalized)) timeframe = "5m";
  else if (/(^|_)15M($|_)/.test(normalized)) timeframe = "15m";
  else if (/(^|_)30M($|_)/.test(normalized)) timeframe = "30m";
  else if (/(^|_)(1H|H1|60M)($|_)/.test(normalized)) timeframe = "1h";
  else if (/(^|_)(4H|H4)($|_)/.test(normalized)) timeframe = "4h";
  else if (/(^|_)(1D|D1)($|_)/.test(normalized)) timeframe = "1d";

  return {symbol, timeframe};
}

export function canonicalDerivativesIdentity(csvText: string): {symbol: string; instrument: string} | null {
  const lines = csvText.split(/\r?\n/).filter(line => line.trim());
  if (lines.length < 2) return null;
  const headers = lines[0]!.split(",").map(value => value.trim().replace(/^\uFEFF/, ""));
  const values = lines[1]!.split(",").map(value => value.trim());
  const symbolIndex = headers.indexOf("symbol");
  const instrumentIndex = headers.indexOf("instrument");
  if (symbolIndex < 0 || instrumentIndex < 0) return null;
  const symbol = values[symbolIndex]?.toUpperCase() ?? "";
  const instrument = values[instrumentIndex]?.toUpperCase() ?? "";
  if (!symbol || !instrument) return null;
  return {symbol, instrument};
}

export type BacktestFormState = {
  systemId: string;
  codeVersion: string;
  aiMode: AiMode;
  modelId: string;
  reasoningEffort: ReasoningEffort;
  hardBudgetUsd: string;
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
  positioningMode: PositioningMode;
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
  hardBudgetUsd: "1",
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
  positioningMode: "SPOT_LONG_ONLY",
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

const PRESET_WARMUP_BARS = 35;
const PRESET_MIN_TEST_BARS = 6;

function splitWindow60_20_20(start: number, end: number): SplitIndices {
  const testBars = end - start + 1;
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || testBars < PRESET_MIN_TEST_BARS) {
    throw new Error(`La fenêtre de backtest doit contenir au moins ${PRESET_MIN_TEST_BARS} bougies.`);
  }
  const designBars = Math.max(1, Math.floor(testBars * 0.60));
  const validationBoundaryBars = Math.max(designBars + 1, Math.floor(testBars * 0.80));
  return {
    design_start: start,
    design_end: start + designBars - 1,
    validation_start: start + designBars,
    validation_end: start + validationBoundaryBars - 1,
    oos_start: start + validationBoundaryBars,
    oos_end: end
  };
}

export function quickTestSplit(preview: DatasetPreview): SplitIndices {
  const available = preview.candle_count;
  const targetTestBars = 100;
  if (available < PRESET_WARMUP_BARS + PRESET_MIN_TEST_BARS) {
    throw new Error(
      `Test rapide nécessite au moins ${PRESET_WARMUP_BARS + PRESET_MIN_TEST_BARS} bougies ` +
      `(${PRESET_WARMUP_BARS} warm-up + ${PRESET_MIN_TEST_BARS} test).`
    );
  }
  const start = PRESET_WARMUP_BARS;
  const testBars = Math.min(targetTestBars, available - start);
  return splitWindow60_20_20(start, start + testBars - 1);
}

export function durationPresetSplit(preview: DatasetPreview, durationDays: number): SplitIndices {
  const available = preview.candle_count;
  const axis = preview.candle_close_ms;
  if (!Number.isFinite(durationDays) || durationDays <= 0) throw new Error("Durée de preset invalide.");
  if (axis.length !== available || available < PRESET_WARMUP_BARS + PRESET_MIN_TEST_BARS) {
    throw new Error(
      `Le preset nécessite les timestamps du dataset et au moins ${PRESET_WARMUP_BARS + PRESET_MIN_TEST_BARS} bougies.`
    );
  }
  const start = PRESET_WARMUP_BARS;
  const durationMs = durationDays * 24 * 60 * 60 * 1000;
  const targetEndMs = Number(axis[start]) + durationMs;
  let end = start;
  while (end + 1 < available && Number(axis[end + 1]) <= targetEndMs) end += 1;
  if (end - start + 1 < PRESET_MIN_TEST_BARS) {
    throw new Error(`Le preset ne contient pas assez de bougies après les ${PRESET_WARMUP_BARS} bougies de warm-up.`);
  }
  return splitWindow60_20_20(start, end);
}

export function fullDatasetSplit(preview: DatasetPreview): SplitIndices {
  if (preview.candle_count < PRESET_MIN_TEST_BARS) {
    throw new Error(`Le dataset doit contenir au moins ${PRESET_MIN_TEST_BARS} bougies.`);
  }
  return splitWindow60_20_20(0, preview.candle_count - 1);
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
  if (form.derivativesEnabled) {
    const identity = canonicalDerivativesIdentity(form.derivativesCsvText);
    if (!identity) throw new Error("Le CSV Rio ne contient pas une identité symbol / instrument canonique lisible.");
    if (identity.symbol !== preview.symbol.trim().toUpperCase()) {
      throw new Error(`Rio: archive ${identity.symbol} incompatible avec le dataset ${preview.symbol}.`);
    }
  }
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
      max_leverage: requirePositive(form.marketMaxLeverage, "market max leverage"),
      positioning_mode: form.positioningMode
    },
    ai: {
      mode: form.aiMode,
      hard_budget_usd: requireNonNegative(form.hardBudgetUsd, "Budget IA"),
      model_id: form.modelId.trim(),
      reasoning_effort: form.reasoningEffort,
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
