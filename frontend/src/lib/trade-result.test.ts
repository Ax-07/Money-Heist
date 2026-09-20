import { describe, expect, it } from "vitest";
import { netTradeReturnPct, tradeResultKind } from "./trade-result";

describe("trade result helpers", () => {
  it("computes the net return against entry notional", () => {
    expect(netTradeReturnPct({ quantity: "0.01", entry_price: "60000", net_pnl: "12" })).toBeCloseTo(2);
    expect(netTradeReturnPct({ quantity: "0.01", entry_price: "60000", net_pnl: "-6" })).toBeCloseTo(-1);
  });

  it("classifies PAPER pnl without guessing from price movement", () => {
    expect(tradeResultKind("12")).toBe("WIN");
    expect(tradeResultKind("-0.01")).toBe("LOSS");
    expect(tradeResultKind("0")).toBe("FLAT");
  });
});
