import { describe, expect, it } from "vitest";
import { isTerminalCampaignStatus, shouldPollCampaignProgress } from "./campaign-progress";

describe("campaign progress polling", () => {
  it.each(["COMPLETED", "FAILED", "CANCELLED"])("treats %s as terminal", status => {
    expect(isTerminalCampaignStatus(status)).toBe(true);
    expect(shouldPollCampaignProgress({ status, result_available: false })).toBe(false);
  });

  it("continues polling while a campaign is queued or running", () => {
    expect(shouldPollCampaignProgress({ status: "QUEUED", result_available: false })).toBe(true);
    expect(shouldPollCampaignProgress({ status: "RUNNING", result_available: false })).toBe(true);
  });

  it("stops polling as soon as a result is available", () => {
    expect(shouldPollCampaignProgress({ status: "COMPLETED", result_available: true })).toBe(false);
  });
});
