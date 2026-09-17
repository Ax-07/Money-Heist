"use client";

import { useQuery } from "@tanstack/react-query";

import {
  analyticsQuery,
  decisionIntelligenceQuery,
  scannerAnalyticsQuery,
} from "../api/queries";
import type { BacktestPeriodRole } from "../api/decision-intelligence-schemas";

export function useAnalyticsRun(campaignId: string | null, role: BacktestPeriodRole) {
  return useQuery({
    queryKey: ["backtest-analytics", campaignId, role],
    queryFn: () => analyticsQuery(campaignId!, role),
    enabled: Boolean(campaignId),
  });
}

export function useScannerAnalytics(campaignId: string | null, role: BacktestPeriodRole) {
  return useQuery({
    queryKey: ["backtest-scanner-analytics", campaignId, role],
    queryFn: () => scannerAnalyticsQuery(campaignId!, role),
    enabled: Boolean(campaignId),
  });
}

export function useDecisionIntelligence(
  campaignId: string | null,
  opportunityId: string | null,
  role: BacktestPeriodRole,
) {
  return useQuery({
    queryKey: ["backtest-decision-intelligence", campaignId, opportunityId, role],
    queryFn: () => decisionIntelligenceQuery(campaignId!, opportunityId!, role),
    enabled: Boolean(campaignId && opportunityId),
  });
}
