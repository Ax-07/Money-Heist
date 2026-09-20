import { describe, expect, it } from "vitest";
import type { DatasetPreview } from "@/lib/api/schemas";
import {
  addCalendarMonthsDate,
  calendarWindowBounds,
  calendarWindowPlan,
} from "./backtest-calendar-window";

function dailyPreview(days: number): DatasetPreview {
  // Une candle 1d qui ouvre le 2025-09-11 clôture le 2025-09-12.
  // Le preview expose candle_close_ms, pas les open_time.
  const firstClose = Date.UTC(2025, 8, 12, 0, 0);
  const candleCloseMs = Array.from(
    { length: days },
    (_, index) => firstClose + index * 24 * 60 * 60 * 1000,
  );
  return {
    dataset_id: "calendar-window",
    version: "v1",
    content_sha256: "abc",
    symbol: "BTC/USDC",
    timeframe: "1d",
    source: "test",
    candle_count: candleCloseMs.length,
    start_at: new Date(candleCloseMs[0]!).toISOString(),
    end_at: new Date(candleCloseMs[candleCloseMs.length - 1]!).toISOString(),
    is_valid: true,
    gap_count: 0,
    has_duplicates: false,
    missing_fields: [],
    candle_close_ms: candleCloseMs,
    suggested_split: null,
    suggested_split_indices: null,
  };
}

describe("calendar backtest window", () => {
  it("adds real calendar months with end-of-month clamping", () => {
    expect(addCalendarMonthsDate("2026-01-31", 1)).toBe("2026-02-28");
    expect(addCalendarMonthsDate("2024-01-31", 1)).toBe("2024-02-29");
    expect(addCalendarMonthsDate("2026-03-31", -1)).toBe("2026-02-28");
  });

  it("creates an exact three-calendar-month window and a 60/20/20 split", () => {
    const preview = dailyPreview(365);
    const plan = calendarWindowPlan(preview, "2025-12-11", 3);

    expect(plan.endExclusiveDate).toBe("2026-03-11");
    expect(plan.warmupBars).toBeGreaterThan(0);
    expect(plan.windowBars).toBe(90);
    expect(plan.effectiveStartAt).toBe("2025-12-12T00:00:00.000Z");
    expect(plan.effectiveEndAt).toBe("2026-03-11T00:00:00.000Z");
    expect(plan.split.design_start).toBe(plan.startIndex);
    expect(plan.split.oos_end).toBe(plan.endIndex);

    const design = plan.split.design_end - plan.split.design_start + 1;
    const validation =
      plan.split.validation_end - plan.split.validation_start + 1;
    const oos = plan.split.oos_end - plan.split.oos_start + 1;
    expect(design + validation + oos).toBe(plan.windowBars);
  });

  it("computes the latest valid start while keeping the selected duration", () => {
    const preview = dailyPreview(365);
    const bounds = calendarWindowBounds(preview, 3);

    expect(bounds.minStartDate).toBe("2025-09-11");
    expect(bounds.maxStartDate).toBe("2026-06-11");
    expect(bounds.coverageEndExclusiveDate).toBe("2026-09-11");
  });

  it("fails closed when the requested window exceeds dataset coverage", () => {
    const preview = dailyPreview(365);
    expect(() => calendarWindowPlan(preview, "2026-07-01", 3)).toThrow(
      "Début hors couverture",
    );
  });
});
