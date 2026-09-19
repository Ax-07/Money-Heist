import { describe, expect, it } from "vitest";
import { chartColorFromHslToken, markerFor } from "./trading-chart-adapter";

describe("chart CSS colors", () => {
  it("converts Tailwind HSL tokens to lightweight-charts compatible RGB", () => {
    expect(chartColorFromHslToken("217 16% 58%", "#94a3b8")).toBe("rgb(131, 144, 165)");
    expect(chartColorFromHslToken("222 26% 7%", "#070b13")).toBe("rgb(13, 16, 22)");
    expect(chartColorFromHslToken("218 20% 18%", "#121a29")).toBe("rgb(37, 43, 55)");
    expect(chartColorFromHslToken("268 83% 67%", "#a78bfa")).toBe("rgb(166, 101, 241)");
  });

  it("supports hue wrapping and explicit degree units", () => {
    expect(chartColorFromHslToken("360 100% 50%", "#000000")).toBe("rgb(255, 0, 0)");
    expect(chartColorFromHslToken("-120deg 100% 50%", "#000000")).toBe("rgb(0, 0, 255)");
  });

  it("falls back for invalid or unsupported tokens", () => {
    expect(chartColorFromHslToken("", "#94a3b8")).toBe("#94a3b8");
    expect(chartColorFromHslToken("garbage", "#94a3b8")).toBe("#94a3b8");
    expect(chartColorFromHslToken("217 120% 58%", "#94a3b8")).toBe("#94a3b8");
    expect(chartColorFromHslToken("217 16% 120%", "#94a3b8")).toBe("#94a3b8");
    expect(chartColorFromHslToken("rgb(148, 163, 184)", "#94a3b8")).toBe("#94a3b8");
  });
});

describe("chart event mapping", () => {
  it("renders Risk as a distinct square marker", () => {
    const marker = markerFor({
      event_id: "1",
      observed_at: "2026-09-12T12:00:00Z",
      event_type: "RISK",
      label: "RESIZED",
      opportunity_id: null,
      agent: "risk_engine",
      phase: "RISK",
      price: null,
      details: {},
    });
    expect(marker.shape).toBe("square");
    expect(marker.text).toBe("RISK");
  });

  it("renders entries below the candle", () => {
    const marker = markerFor({
      event_id: "2",
      observed_at: "2026-09-12T12:00:00Z",
      event_type: "ENTRY",
      label: "Entry",
      opportunity_id: null,
      agent: null,
      phase: null,
      price: "100",
      details: {},
    });
    expect(marker.position).toBe("belowBar");
    expect(marker.shape).toBe("arrowUp");
  });
});
