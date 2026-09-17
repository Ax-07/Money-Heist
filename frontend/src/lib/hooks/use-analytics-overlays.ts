"use client";

import { useQuery } from "@tanstack/react-query";
import { analyticsOverlaysQuery } from "../api/queries";
import type { BacktestPeriodRole } from "../api/decision-intelligence-schemas";

export function useAnalyticsOverlays(
  campaignId: string | null,
  role: BacktestPeriodRole,
  enabled = true,
) {
  return useQuery({
    queryKey: ["backtest-analytics-overlays", campaignId, role],
    queryFn: () => analyticsOverlaysQuery(campaignId!, role),
    enabled: enabled && campaignId !== null,
    retry: false,
  });
}
