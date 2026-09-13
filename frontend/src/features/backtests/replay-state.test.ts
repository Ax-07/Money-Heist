import { describe, expect, it } from "vitest";
import { clampIndex, eventIndex } from "./replay-state";
import type { BacktestReplay } from "@/lib/api/schemas";

const replay = {
  campaign_id:"c",role:"OOS",symbol:"BTC/EUR",timeframe:"1h",
  candles:[0,1,2,3].map(i=>({time:100+i*100,open_time:"2026-01-01T00:00:00Z",close_time:"2026-01-01T01:00:00Z",open:"1",high:"1",low:"1",close:"1",volume:"1",is_closed:true})),
  events:[{event_id:"e",observed_at:"1970-01-01T00:05:00Z",event_type:"RISK",label:"Risk",opportunity_id:null,agent:null,phase:null,price:null,details:{}}],traces:[],trades:[],equity:[]
} satisfies BacktestReplay;

describe("replay state",()=>{
 it("clamps candle indices",()=>{expect(clampIndex(-4,4)).toBe(0);expect(clampIndex(9,4)).toBe(3)});
 it("jumps to the nearest next event",()=>{expect(eventIndex(replay,0,1)).toBe(2)});
});
