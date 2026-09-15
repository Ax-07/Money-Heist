import { z } from "zod";
import { api } from "./client";
import {
  backtestCapabilitiesSchema,
  campaignConfigurationSchema,
  campaignProgressSchema,
  campaignRequestSchema,
  campaignSummarySchema,
  dashboardSnapshotSchema,
  datasetCatalogSchema,
  datasetInputSchema,
  datasetPreviewSchema,
  frontendCapabilitiesSchema,
  marketCandlesSchema,
  marketConstraintsSchema,
  openAiModelCatalogSchema,
  replaySchema,
  storedCampaignRequestSchema,
  type CampaignRequest,
  type StoredCampaignRequest
} from "./schemas";

export const dashboardQuery = () => api.get("/api/dashboard/overview", dashboardSnapshotSchema);
export const frontendCapabilitiesQuery = () => api.get("/api/frontend/v2/capabilities", frontendCapabilitiesSchema);
export const openAiModelsQuery = () => api.get("/api/frontend/v2/ai/openai/models", openAiModelCatalogSchema);
export const backtestCapabilitiesQuery = () => api.get("/api/dashboard/backtest/capabilities", backtestCapabilitiesSchema);
export const campaignsQuery = () => api.get("/api/frontend/v2/backtests/runs", z.array(campaignSummarySchema));
export const campaignQuery = (id: string) => api.get(`/api/frontend/v2/backtests/runs/${encodeURIComponent(id)}`, campaignSummarySchema);
export const campaignProgressQuery = (id: string) => api.get(`/api/frontend/v2/backtests/runs/${encodeURIComponent(id)}/progress`, campaignProgressSchema);
export const campaignConfigurationQuery = (id: string) => api.get(`/api/frontend/v2/backtests/runs/${encodeURIComponent(id)}/configuration`, campaignConfigurationSchema);
export const replayQuery = (id: string, role: "DESIGN" | "VALIDATION" | "OOS") => api.get(`/api/frontend/v2/backtests/runs/${encodeURIComponent(id)}/replay?role=${role}`, replaySchema);
export const marketCandlesQuery = (symbol: string, timeframe: string) => api.get(`/api/frontend/v2/market/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}&limit=500`, marketCandlesSchema);
export const marketConstraintsQuery = (symbol:string) => api.get(`/api/frontend/v2/market/constraints?symbol=${encodeURIComponent(symbol)}`, marketConstraintsSchema);
export const previewDataset = (payload: z.input<typeof datasetInputSchema>) => api.post("/api/dashboard/backtest/dataset/preview", datasetPreviewSchema, datasetInputSchema.parse(payload));
export const saveDataset = (payload: z.input<typeof datasetInputSchema>) => api.post("/api/frontend/v2/backtests/datasets", datasetPreviewSchema, datasetInputSchema.parse(payload));
export const saveDatasetFile = (file: File, metadata: {symbol:string;timeframe:string;source:string}) => {
  const params = new URLSearchParams({symbol:metadata.symbol,timeframe:metadata.timeframe,source:metadata.source});
  return api.postRaw(`/api/frontend/v2/backtests/datasets/upload?${params.toString()}`, datasetPreviewSchema, file, "text/csv");
};
export const datasetsQuery = () => api.get("/api/frontend/v2/backtests/datasets", z.array(datasetCatalogSchema));
export const datasetPreviewQuery = (datasetId: string) => api.get(`/api/frontend/v2/backtests/dataset?dataset_id=${encodeURIComponent(datasetId)}`, datasetPreviewSchema);
export const startBacktest = (payload: CampaignRequest) => api.post("/api/frontend/v2/backtests/runs", campaignProgressSchema, campaignRequestSchema.parse(payload));
export const startBacktestFromDataset = (payload: StoredCampaignRequest) => api.post("/api/frontend/v2/backtests/runs/from-dataset", campaignProgressSchema, storedCampaignRequestSchema.parse(payload));
