import { describe, expect, it } from "vitest";
import {
  buildCampaignConfig,
  canonicalDerivativesIdentity,
  defaultBacktestForm,
  detectHistoricalDatasetIdentity,
  durationPresetSplit,
  fullDatasetSplit,
  HISTORICAL_DATASET_SYMBOLS,
  HISTORICAL_DATASET_TIMEFRAMES,
  historicalMarketPreset,
  percentToDecimal,
  quickTestSplit,
  splitIndicesToDates
} from "./backtest-config";
import type { DatasetPreview } from "@/lib/api/schemas";

const preview: DatasetPreview = {
  dataset_id:"d",version:"v1",content_sha256:"abc",symbol:"BTC/EUR",timeframe:"1h",source:"test",candle_count:6,
  start_at:"2026-01-01T01:00:00Z",end_at:"2026-01-01T06:00:00Z",is_valid:true,gap_count:0,has_duplicates:false,missing_fields:[],
  candle_close_ms:[1,2,3,4,5,6].map(hour=>Date.UTC(2026,0,1,hour)),suggested_split:null,suggested_split_indices:null
};

describe("backtest config",()=>{
  it("offers every historical source timeframe including 1m",()=>{
    expect(HISTORICAL_DATASET_TIMEFRAMES).toEqual(["1m","5m","15m","30m","1h","4h","1d"]);
  });
  it("uses BTC/USDC as a first-class historical symbol",()=>{
    expect(HISTORICAL_DATASET_SYMBOLS[0]).toBe("BTC/USDC");
    expect(historicalMarketPreset("BTC/USDC")?.minNotional).toBe("5");
  });
  it("detects BTC/USDC and 1m from historical dataset filenames",()=>{
    expect(detectHistoricalDatasetIdentity("btc_usdc_1m_2025-09-11_2026-09-11.csv")).toEqual({symbol:"BTC/USDC",timeframe:"1m"});
  });
  it("reads the canonical Rio archive identity",()=>{
    const csv="symbol,instrument,observed_at,available_at,funding_rate,open_interest,open_interest_change_pct,long_short_ratio\nBTC/USDC,PF_XBTUSD,2026-01-01T00:00:00Z,2026-01-01T01:00:00Z,,1000,1,1.1\n";
    expect(canonicalDerivativesIdentity(csv)).toEqual({symbol:"BTC/USDC",instrument:"PF_XBTUSD"});
  });
  it("converts UI percentages to risk fractions",()=>expect(percentToDecimal("1")).toBe("0.01"));
  it("enforces ordered non-overlapping split indices",()=>{
    expect(()=>splitIndicesToDates(preview,{design_start:0,design_end:2,validation_start:2,validation_end:3,oos_start:4,oos_end:5})).toThrow();
  });
  it("restores the legacy quick-test preset after 35 warm-up bars",()=>{
    const closes=Array.from({length:200},(_,index)=>Date.UTC(2026,0,1,index));
    const large={...preview,candle_count:closes.length,candle_close_ms:closes};
    expect(quickTestSplit(large)).toEqual({design_start:35,design_end:94,validation_start:95,validation_end:114,oos_start:115,oos_end:134});
  });
  it("uses the timestamp axis for calendar duration presets",()=>{
    const closes=Array.from({length:300},(_,index)=>Date.UTC(2026,0,1,index*4));
    const large={...preview,timeframe:"4h",candle_count:closes.length,candle_close_ms:closes};
    const split=durationPresetSplit(large,30);
    expect(split.design_start).toBe(35);
    expect(split.oos_end).toBe(215);
    expect(split.design_end-split.design_start+1).toBe(108);
    expect(split.validation_end-split.validation_start+1).toBe(36);
    expect(split.oos_end-split.oos_start+1).toBe(37);
  });
  it("splits the full dataset 60 / 20 / 20",()=>{
    const closes=Array.from({length:100},(_,index)=>Date.UTC(2026,0,1,index));
    const large={...preview,candle_count:closes.length,candle_close_ms:closes};
    expect(fullDatasetSplit(large)).toEqual({design_start:0,design_end:59,validation_start:60,validation_end:79,oos_start:80,oos_end:99});
  });
  it("blocks a Rio archive whose symbol differs from the dataset",()=>{
    const form=defaultBacktestForm("balanced_v1");
    form.codeVersion="deadbeef"; form.qtyStep="0.0001"; form.minQty="0.0001"; form.minNotional="5";
    form.derivativesEnabled=true;
    form.derivativesCsvText="symbol,instrument,observed_at,available_at,funding_rate,open_interest,open_interest_change_pct,long_short_ratio\nBTC/USDC,PF_XBTUSD,2026-01-01T00:00:00Z,2026-01-01T01:00:00Z,,1000,1,1.1\n";
    const oneMinute={...preview,symbol:"BTC/EUR",timeframe:"1m"};
    expect(()=>buildCampaignConfig(oneMinute,{design_start:0,design_end:1,validation_start:2,validation_end:3,oos_start:4,oos_end:5},form)).toThrow("Rio: archive BTC/USDC incompatible avec le dataset BTC/EUR.");
  });
  it("builds explicit campaign config",()=>{
    const form=defaultBacktestForm("balanced_v1");
    form.codeVersion="deadbeef"; form.qtyStep="0.0001"; form.minQty="0.0001"; form.minNotional="5";
    const config=buildCampaignConfig(preview,{design_start:0,design_end:1,validation_start:2,validation_end:3,oos_start:4,oos_end:5},form);
    expect(config.risk.max_risk_per_trade_pct).toBe("0.01");
    expect(config.execution.code_version).toBe("deadbeef");
    expect(config.walk_forward.enabled).toBe(false);
    expect(config.ai.hard_budget_usd).toBe("1");
    expect("input_per_million_eur" in config.ai).toBe(false);
  });
});
