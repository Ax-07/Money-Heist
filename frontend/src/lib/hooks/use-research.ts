"use client";

import { useQuery } from "@tanstack/react-query";

import {
  decisionQualityResearchQuery,
  researchEvidenceQuery,
} from "../api/queries";
import type { BacktestPeriodRole } from "../api/decision-intelligence-schemas";
import type { ResearchCohortSelector } from "../research-state";

export function useDecisionQualityResearch(
  campaignId: string | null,
  role: BacktestPeriodRole,
  enabled = true,
) {
  return useQuery({
    queryKey: ["decision-quality-research", campaignId, role],
    queryFn: () => decisionQualityResearchQuery(campaignId!, role),
    enabled: enabled && campaignId !== null,
    retry: false,
  });
}

export function useResearchEvidence(
  campaignId: string | null,
  role: BacktestPeriodRole,
  selector: ResearchCohortSelector | null,
  page: number,
  enabled = true,
) {
  return useQuery({
    queryKey: [
      "decision-quality-research-evidence",
      campaignId,
      role,
      selector?.reportType ?? null,
      selector?.stage ?? null,
      selector?.dimension ?? null,
      selector?.key ?? null,
      page,
    ],
    queryFn: () => researchEvidenceQuery(campaignId!, role, selector!, page),
    enabled: enabled && campaignId !== null && selector !== null,
    retry: false,
  });
}
