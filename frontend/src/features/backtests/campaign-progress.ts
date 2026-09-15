export const TERMINAL_CAMPAIGN_STATUSES = new Set(["COMPLETED", "FAILED", "CANCELLED"]);

export function isTerminalCampaignStatus(status: string | null | undefined): boolean {
  return status ? TERMINAL_CAMPAIGN_STATUSES.has(status.toUpperCase()) : false;
}

export function shouldPollCampaignProgress(progress: {
  status?: string | null;
  result_available?: boolean;
} | null | undefined): boolean {
  if (!progress) return true;
  if (progress.result_available) return false;
  return !isTerminalCampaignStatus(progress.status);
}
