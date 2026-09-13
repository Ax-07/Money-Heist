import { describe, expect, it } from "vitest";
import { buildCampaignConfig, defaultBacktestForm, percentToDecimal, splitIndicesToDates } from "./backtest-config";
import type { DatasetPreview } from "@/lib/api/schemas";

const preview: DatasetPreview = {
  dataset_id:"d",version:"v1",content_sha256:"abc",symbol:"BTC/EUR",timeframe:"1h",source:"test",candle_count:6,
  start_at:"2026-01-01T01:00:00Z",end_at:"2026-01-01T06:00:00Z",is_valid:true,gap_count:0,has_duplicates:false,missing_fields:[],
  candle_close_ms:[1,2,3,4,5,6].map(hour=>Date.UTC(2026,0,1,hour)),suggested_split:null,suggested_split_indices:null
};

describe("backtest config",()=>{
  it("converts UI percentages to risk fractions",()=>expect(percentToDecimal("1")).toBe("0.01"));
  it("enforces ordered non-overlapping split indices",()=>{
    expect(()=>splitIndicesToDates(preview,{design_start:0,design_end:2,validation_start:2,validation_end:3,oos_start:4,oos_end:5})).toThrow();
  });
  it("builds explicit campaign config",()=>{
    const form=defaultBacktestForm("balanced_v1");
    form.codeVersion="deadbeef"; form.qtyStep="0.0001"; form.minQty="0.0001"; form.minNotional="5";
    const config=buildCampaignConfig(preview,{design_start:0,design_end:1,validation_start:2,validation_end:3,oos_start:4,oos_end:5},form);
    expect(config.risk.max_risk_per_trade_pct).toBe("0.01");
    expect(config.execution.code_version).toBe("deadbeef");
    expect(config.walk_forward.enabled).toBe(false);
  });
});
