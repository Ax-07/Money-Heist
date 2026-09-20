import { describe, expect, it } from "vitest";
import {
  formatTradeDurationLabel,
  grossMovePct,
  realizedRMultiple,
  riskReasonLabel,
} from "./trade-story";

describe("trade story helpers", () => {
  it("formats trade duration compactly", () => {
    expect(formatTradeDurationLabel("2026-01-01T00:00:00Z", "2026-01-01T03:42:00Z")).toBe("3h42");
    expect(formatTradeDurationLabel("2026-01-01T00:00:00Z", "2026-01-01T00:18:00Z")).toBe("18m");
  });

  it("computes gross move in the correct direction", () => {
    expect(grossMovePct({ side: "LONG", entryPrice: "100", exitPrice: "104" })).toBeCloseTo(4);
    expect(grossMovePct({ side: "SHORT", entryPrice: "100", exitPrice: "96" })).toBeCloseTo(4);
  });

  it("computes realized R from the planned stop", () => {
    expect(realizedRMultiple({ side: "LONG", entryPrice: "100", exitPrice: "108", stopPrice: "96" })).toBeCloseTo(2);
    expect(realizedRMultiple({ side: "SHORT", entryPrice: "100", exitPrice: "96", stopPrice: "102" })).toBeCloseTo(2);
  });

  it("renders readable risk reasons", () => {
    expect(riskReasonLabel("MIN_EXPECTED_RR")).toBe("RR insuffisant");
    expect(riskReasonLabel("MAX_POSITIONS")).toBe("Max positions");
  });
});
